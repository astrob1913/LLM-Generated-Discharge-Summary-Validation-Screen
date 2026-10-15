#!/usr/bin/env python3
"""
generate_summaries.py — Stage 2 of the validation-study data pipeline.

Generates a clinician-facing discharge summary for each episode using a LOCAL
open-weights model served by Ollama. No data leaves the machine.

IMPORTANT — WHAT THIS IS AND IS NOT
  This script CALLS an existing, pre-trained, general-purpose language model.
  It does not build, train, fine-tune or evaluate a model. The model is treated
  as a black box that produces the artefacts which the study then validates.
  In the dissertation this belongs in Data Preparation, not Implementation.

STRUCTURE
  Summaries follow the NHS England / PRSB eDischarge Summary Standard v2.1
  (Open Government Licence v3.0). The 6 mandatory sections are always requested;
  selected 'required' sections are included because they carry the clinical
  content this study is about. Using a published standard means an omitted
  section is an objectively defined error, not one this project invented.

CITATIONS
  The model is asked to tag every factual statement with the numbered note(s)
  supporting it, e.g. "[N12]". These tags are NOT ground truth — model-generated
  citations are known to be unreliable, and that unreliability is itself part of
  what the validation interface exists to surface. They are a feature under test.

DETERMINISM
  temperature=0 and a fixed seed are set so a marker can reproduce the outputs.
  The model tag, all parameters and a SHA-256 of the prompt template are written
  to out/generation_manifest.json for the appendix.

USAGE
  python scripts/generate_summaries.py --dry-run --limit 2   # inspect prompts, no model
  python scripts/generate_summaries.py --model llama3.1:8b --limit 3
  python scripts/generate_summaries.py --model llama3.1:8b   # all 50

--------------------------------------------------------------------------
ATTRIBUTION: This file was written with AI assistance (Claude, Anthropic) and
reviewed/adapted by the author. Retained per City St George's MSc Project
Guidance, Appendix C items 7 and 9.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None


OLLAMA_URL = "http://localhost:11434"

# --------------------------------------------------------------------------
# PRSB eDischarge Summary Standard v2.1 — section specification
# Mandatory sections are marked M; the required sections retained here are
# marked R. Source: https://theprsb.org/standards/edischargesummary/
# --------------------------------------------------------------------------
PRSB_SECTIONS = [
    ("Patient demographics",            "M", "Name, date of birth, NHS number, age, sex."),
    ("Admission details",               "R", "Date and time of admission, method of admission, ward/department."),
    ("Discharge details",               "R", "Date of discharge and discharge destination, if documented."),
    ("Diagnoses",                       "M", "Primary diagnosis first, then secondary diagnoses. Use the diagnosis actually recorded."),
    ("Clinical summary",                "M", "Narrative of the admission: presentation, key investigations, treatment, and progress."),
    ("Procedures",                      "R", "Any operations or procedures performed, with dates."),
    ("Investigations and results",      "R", "Key investigations and their results. Include pending results if documented."),
    ("Medications and medical devices", "R", "Discharge medications with dose, route and frequency. State changes made during admission."),
    ("Allergies and adverse reactions", "M", "State explicitly. If none are recorded, write 'None recorded'."),
    ("Plan and requested actions",      "R", "Follow-up arrangements, actions for the GP, and monitoring required."),
    ("Information provided to patient", "R", "What the patient or carer was told, if documented."),
    ("Person completing record",        "M", "Name and role of the clinician, as recorded in the notes."),
]

PROMPT_TEMPLATE = """You are a hospital doctor writing a discharge summary for the patient's GP.

You will be given the complete set of clinical notes from one hospital episode, \
in chronological order and numbered [N1], [N2], [N3] and so on.

Write a discharge summary using EXACTLY the section headings listed below, in \
this order. Use a level-2 markdown heading (##) for each section.

{section_spec}

RULES — follow all of them:
1. Use ONLY information present in the numbered notes. Do not add clinical \
knowledge of your own, and do not infer anything the notes do not state.
2. After every factual statement, cite the note or notes it came from, in \
square brackets: for example "Commenced on nimodipine 60mg four-hourly [N7]." \
A statement drawing on several notes cites all of them: "[N7][N12]".
3. If a section has no supporting information in the notes, write the heading \
followed by "Not documented." Do not omit the heading and do not invent content.
4. Write in the register of a UK hospital discharge summary: concise, factual, \
professional. Standard clinical abbreviations are acceptable.
5. Do not include any commentary, preamble or explanation outside the summary \
itself. Begin directly with the first heading.
6. Do NOT repeat the guidance text that follows each heading above. Write the \
heading, then the content. Do not use the guidance as a label.
7. The Clinical summary section must carry citations too. Every sentence in it \
needs at least one note reference.
8. Do not indent lines. Start each line at the left margin.

=== PATIENT RECORD ===
{demographics}

=== CLINICAL NOTES FOR THIS EPISODE ===
{notes_block}
=== END OF NOTES ===

Write the discharge summary now."""


def build_section_spec() -> str:
    """Render the section list.

    The guidance for each heading is placed after an arrow rather than on an
    indented line beneath it. Earlier runs showed the model echoing indented
    guidance back into the output as a label ("Name and role of the clinician,
    as recorded in the notes: Dr ..."), which is a formatting artefact of the
    prompt rather than anything about the clinical content.
    """
    lines = []
    for name, conformance, guidance in PRSB_SECTIONS:
        tag = "MANDATORY" if conformance == "M" else "required"
        lines.append(f"## {name}  ({tag})  -> {guidance}")
    return "\n".join(lines)


def build_notes_block(episode: dict) -> tuple[str, dict]:
    """Render the episode's notes as a numbered block.

    Simple integer labels (N1, N2, ...) are used rather than UUIDs because
    smaller local models cite short tokens far more reliably. The mapping back
    to real note_ids is returned and stored alongside the output.
    """
    parts, mapping = [], {}
    for note in episode["notes"]:
        label = f"N{note['seq']}"
        mapping[label] = note["note_id"]
        stamp = note["timestamp"].replace("T", " ")
        flag = "  (PRE-ADMISSION)" if note["pre_admission"] else ""
        parts.append(
            f"[{label}] {stamp} | {note['note_type']} | {note['note_subject']}{flag}\n"
            f"{note['text'].strip()}\n"
        )
    return "\n".join(parts), mapping


def build_demographics(episode: dict) -> str:
    """Structured patient and admission details.

    These come from the patient and admission tables, not the notes. Without
    them the model reports PRSB mandatory demographic fields as "Not documented"
    — an omission caused by what we withheld rather than by the model, which
    would contaminate the error key. A real deployment reads these straight
    from the patient record, so supplying them is the faithful setup.
    """
    p, a = episode["patient"], episode["admission"]
    return (
        f"Name: {p['full_name']}\n"
        f"Date of birth: {p['date_of_birth']}\n"
        f"NHS number: {p['nhs_number']}\n"
        f"Age: {p['age']}\n"
        f"Sex: {p['gender_identity']}\n"
        f"Admission date/time: {a['timestamp'].replace('T', ' ')}\n"
        f"Method of admission: {a['method']}\n"
        f"Ward/department: {a['department']}"
    )


def build_prompt(episode: dict) -> tuple[str, dict]:
    notes_block, mapping = build_notes_block(episode)
    prompt = PROMPT_TEMPLATE.format(
        section_spec=build_section_spec(),
        demographics=build_demographics(episode),
        notes_block=notes_block,
    )
    return prompt, mapping


def call_ollama(model: str, prompt: str, num_ctx: int, seed: int, timeout: int,
                no_think: bool = True) -> dict:
    if requests is None:
        raise RuntimeError("The 'requests' package is required: pip install requests")
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        # Keep the model resident between episodes. Ollama's default unloads it
        # after 5 minutes idle, which on CPU costs ~100s to reload each time —
        # over an hour wasted across a 50-episode run.
        "keep_alive": "60m",
        "options": {
            # Ollama defaults num_ctx to 2048, which would SILENTLY TRUNCATE these
            # prompts (median ~5k tokens, up to ~9.5k). This must be set explicitly.
            "num_ctx": num_ctx,
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": seed,
        },
    }
    # Reasoning ("thinking") models such as the Qwen3 family emit a long internal
    # monologue before answering, and Ollama returns it in a separate `thinking`
    # field. On CPU that monologue can consume the entire generation budget, so
    # the summary never gets written. Ask the model to skip it.
    if no_think:
        payload["think"] = False

    response = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=timeout)

    # Models that do not support the `think` flag reject the request; retry plainly.
    if response.status_code >= 400 and no_think:
        body = response.text.lower()
        if "think" in body:
            payload.pop("think", None)
            response = requests.post(f"{OLLAMA_URL}/api/generate",
                                     json=payload, timeout=timeout)

    if response.status_code != 200:
        # Ollama explains the real problem in the response body (out of memory,
        # context too large, model failed to load). Surface it instead of the
        # bare HTTP status, which tells you nothing useful.
        try:
            detail = response.json().get("error", response.text)
        except Exception:
            detail = response.text
        raise RuntimeError(f"Ollama returned {response.status_code}: {detail[:600]}")
    return response.json()


def check_ollama(model: str) -> bool:
    if requests is None:
        print("ERROR: pip install requests", file=sys.stderr)
        return False
    try:
        tags = requests.get(f"{OLLAMA_URL}/api/tags", timeout=10).json()
    except Exception as exc:
        print(f"ERROR: cannot reach Ollama at {OLLAMA_URL} ({exc})", file=sys.stderr)
        print("       Start it with:  ollama serve", file=sys.stderr)
        return False

    available = [m["name"] for m in tags.get("models", [])]
    print(f"Ollama reachable. Models installed: {available or '(none)'}")
    if not any(m == model or m.startswith(model.split(':')[0]) for m in available):
        print(f"\nERROR: model '{model}' is not installed.", file=sys.stderr)
        print(f"       Pull it with:  ollama pull {model}", file=sys.stderr)
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--episodes", default="out/episodes.json")
    ap.add_argument("--out", default="out/summaries_clinician")
    ap.add_argument("--model", default="mistral:latest")
    ap.add_argument("--num-ctx", type=int, default=16384,
                    help="context window; must exceed the longest prompt (~9.5k tokens)")
    ap.add_argument("--seed", type=int, default=20260821)
    ap.add_argument("--timeout", type=int, default=3600, help="per-episode timeout, seconds")
    ap.add_argument("--limit", type=int, default=None, help="process only the first N episodes")
    ap.add_argument("--dry-run", action="store_true",
                    help="write prompts only; do not call the model")
    ap.add_argument("--overwrite", action="store_true",
                    help="regenerate summaries that already exist")
    ap.add_argument("--smoke-test", action="store_true",
                    help="send one tiny prompt to check the model loads at all, then stop")
    args = ap.parse_args()

    if args.smoke_test:
        if not check_ollama(args.model):
            return 1
        print(f"\nSmoke test: loading {args.model} at num_ctx={args.num_ctx} ...")
        t0 = time.time()
        try:
            out = call_ollama(args.model, "Reply with the single word: ready",
                              args.num_ctx, args.seed, 600)
        except Exception as exc:
            print(f"\nFAILED after {time.time()-t0:.0f}s\n  {exc}", file=sys.stderr)
            print("\nMost likely: not enough free memory for this model at this "
                  "context size.\n  Try:  --num-ctx 4096\n  Or a smaller model: "
                  "--model mistral:latest", file=sys.stderr)
            return 1
        print(f"OK in {time.time()-t0:.0f}s. Model replied: "
              f"{out.get('response','').strip()[:120]!r}")
        print("The model loads fine at this context size.")
        return 0

    episodes = json.loads(Path(args.episodes).read_text(encoding="utf-8"))
    if args.limit:
        episodes = episodes[:args.limit]

    out_dir = Path(args.out)
    (out_dir / "prompts").mkdir(parents=True, exist_ok=True)

    if not args.dry_run and not check_ollama(args.model):
        return 1

    prompt_hash = hashlib.sha256(PROMPT_TEMPLATE.encode()).hexdigest()[:16]
    records, started = [], time.time()

    for i, episode in enumerate(episodes, 1):
        eid = episode["episode_id"]
        target = out_dir / f"{eid}.md"
        if target.exists() and not args.overwrite and not args.dry_run:
            print(f"[{i}/{len(episodes)}] {eid[:8]} — exists, skipping")
            continue

        prompt, mapping = build_prompt(episode)
        (out_dir / "prompts" / f"{eid}.txt").write_text(prompt, encoding="utf-8")
        approx_tokens = len(prompt) // 4

        if approx_tokens > args.num_ctx * 0.9:
            print(f"  WARNING: prompt ~{approx_tokens} tokens is close to "
                  f"num_ctx={args.num_ctx}; raise --num-ctx", file=sys.stderr)

        if args.dry_run:
            print(f"[{i}/{len(episodes)}] {eid[:8]} — prompt written "
                  f"(~{approx_tokens} tokens, {episode['note_count']} notes)")
            records.append({"episode_id": eid, "approx_prompt_tokens": approx_tokens,
                            "note_count": episode["note_count"], "dry_run": True})
            continue

        t0 = time.time()
        try:
            result = call_ollama(args.model, prompt, args.num_ctx, args.seed, args.timeout)
        except Exception as exc:
            print(f"[{i}/{len(episodes)}] {eid[:8]} — FAILED: {exc}", file=sys.stderr)
            records.append({"episode_id": eid, "error": str(exc)})
            continue

        elapsed = time.time() - t0

        # A reasoning model may put everything in `thinking` and leave `response`
        # empty. Save whatever we actually got rather than writing a 0-byte file,
        # and say plainly which field it came from.
        text = (result.get("response") or "").strip()
        thinking = (result.get("thinking") or "").strip()
        source = "response"
        if not text and thinking:
            text = thinking
            source = "thinking (model reasoned but never produced a final answer)"

        if not text:
            print(f"[{i}/{len(episodes)}] {eid[:8]} — EMPTY OUTPUT after "
                  f"{elapsed:.0f}s. The model generated "
                  f"{result.get('eval_count', '?')} tokens but returned nothing "
                  f"usable. Try a non-reasoning model: --model mistral:latest",
                  file=sys.stderr)
            records.append({"episode_id": eid, "error": "empty output",
                            "seconds": round(elapsed, 1),
                            "eval_count": result.get("eval_count")})
            continue

        target.write_text(text, encoding="utf-8")
        (out_dir / f"{eid}.notemap.json").write_text(
            json.dumps(mapping, indent=2), encoding="utf-8")

        records.append({
            "episode_id": eid,
            "note_count": episode["note_count"],
            "approx_prompt_tokens": approx_tokens,
            "prompt_eval_count": result.get("prompt_eval_count"),
            "eval_count": result.get("eval_count"),
            "seconds": round(elapsed, 1),
            "output_chars": len(text),
            "output_source": source,
        })
        print(f"[{i}/{len(episodes)}] {eid[:8]} — {elapsed:.0f}s, "
              f"{result.get('eval_count', '?')} tokens, {len(text)} chars written"
              + ("" if source == "response" else f"  [from {source}]"))

    # Merge with any previous manifest rather than replacing it. A later partial
    # run (e.g. regenerating two failed episodes) would otherwise discard the
    # timings and token counts from the original full run, which are needed for
    # the methodology chapter.
    manifest_path = out_dir / "generation_manifest.json"
    previous = []
    if manifest_path.exists():
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
            done = {r.get("episode_id") for r in records}
            previous = [r for r in old.get("episodes", [])
                        if r.get("episode_id") not in done]
        except Exception:
            pass
    records = previous + records

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "backend": "ollama (local, no network egress)",
        "parameters": {"num_ctx": args.num_ctx, "temperature": 0.0,
                       "top_p": 1.0, "seed": args.seed},
        "prompt_template_sha256_16": prompt_hash,
        "prsb_standard": "NHS England / PRSB eDischarge Summary Standard v2.1 (OGL v3.0)",
        "summary_type": "clinician-facing",
        "dry_run": args.dry_run,
        "episodes": records,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    ok = [r for r in records if "error" not in r and not r.get("dry_run")]
    print(f"\nDone in {time.time() - started:.0f}s. "
          f"{len(ok)} generated, {len([r for r in records if 'error' in r])} failed.")
    if ok:
        times = [r["seconds"] for r in ok]
        print(f"  per-episode: min {min(times):.0f}s  "
              f"median {sorted(times)[len(times)//2]:.0f}s  max {max(times):.0f}s")
    print(f"  manifest: {out_dir/'generation_manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
