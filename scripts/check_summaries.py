#!/usr/bin/env python3
"""
check_summaries.py — quality check across the generated summary set.

Reports, for all 50 summaries at once:
  * whether every PRSB section heading is present
  * how many note citations each summary carries, and where they fall
  * whether the prompt-guidance text is being echoed back as a label
  * whether mandatory demographic fields were populated
  * length distribution

Run:  python scripts\\check_summaries.py

--------------------------------------------------------------------------
ATTRIBUTION: Written with AI assistance (Claude, Anthropic), reviewed and
adapted by the author. Retained per MSc Project Guidance Appendix C, items 7/9.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from pathlib import Path

SUMMARY_DIR = Path("out/summaries_clinician")

PRSB_HEADINGS = [
    "Patient demographics", "Admission details", "Discharge details", "Diagnoses",
    "Clinical summary", "Procedures", "Investigations and results",
    "Medications and medical devices", "Allergies and adverse reactions",
    "Plan and requested actions", "Information provided to patient",
    "Person completing record",
]

# Fragments of the prompt guidance. If these appear in the OUTPUT the model is
# echoing my instructions back as labels rather than writing content.
ECHO_MARKERS = [
    "Name and role of the clinician, as recorded in the notes",
    "Discharge medications with dose, route and frequency",
    "Date and time of admission, method of admission",
    "Primary diagnosis first, then secondary diagnoses",
    "Narrative of the admission: presentation",
    "Follow-up arrangements, actions for the GP",
    "What the patient or carer was told",
    "(MANDATORY)", "(required)", "->",
]

CITE = re.compile(r"\[N\d+\]")


def section_body(text: str, heading: str) -> str:
    """Return the text under one heading, up to the next heading."""
    m = re.search(rf"^##\s*{re.escape(heading)}\s*$", text, re.M | re.I)
    if not m:
        return ""
    rest = text[m.end():]
    nxt = re.search(r"^##\s", rest, re.M)
    return rest[:nxt.start()] if nxt else rest


def main() -> None:
    files = sorted(SUMMARY_DIR.glob("*.md"))
    if not files:
        print(f"No .md files found in {SUMMARY_DIR.resolve()}")
        return

    print(f"Checking {len(files)} summaries in {SUMMARY_DIR}\n")

    lengths, cite_counts, missing_headings = [], [], Counter()
    echo_hits, no_dob, empty_clinical, clin_no_cites = [], [], [], []
    cites_by_section = Counter()
    not_documented = Counter()

    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        sid = f.stem[:8]
        lengths.append(len(text))
        cite_counts.append(len(CITE.findall(text)))

        for h in PRSB_HEADINGS:
            body = section_body(text, h)
            if not re.search(rf"^##\s*{re.escape(h)}\s*$", text, re.M | re.I):
                missing_headings[h] += 1
            else:
                cites_by_section[h] += len(CITE.findall(body))
                if re.search(r"not documented", body, re.I):
                    not_documented[h] += 1

        for marker in ECHO_MARKERS:
            if marker in text:
                echo_hits.append((sid, marker))
                break

        demo = section_body(text, "Patient demographics")
        if re.search(r"date of birth[^\n]*not documented", demo, re.I) or \
           not re.search(r"date of birth", demo, re.I):
            no_dob.append(sid)

        clin = section_body(text, "Clinical summary").strip()
        if len(clin) < 100:
            empty_clinical.append(sid)
        elif not CITE.search(clin):
            clin_no_cites.append(sid)

    print("=== STRUCTURE ===")
    if missing_headings:
        for h, n in missing_headings.most_common():
            print(f"  MISSING in {n:2d}/{len(files)}:  {h}")
    else:
        print(f"  All 12 PRSB headings present in all {len(files)} summaries.")

    print("\n=== LENGTH (characters) ===")
    print(f"  min {min(lengths)}  median {int(statistics.median(lengths))}  "
          f"mean {int(statistics.mean(lengths))}  max {max(lengths)}")

    print("\n=== CITATIONS ===")
    print(f"  per summary: min {min(cite_counts)}  "
          f"median {int(statistics.median(cite_counts))}  max {max(cite_counts)}")
    print(f"  summaries with zero citations: {sum(1 for c in cite_counts if c == 0)}")
    print("  total citations by section:")
    for h in PRSB_HEADINGS:
        print(f"    {cites_by_section[h]:5d}  {h}")

    print("\n=== PROMPT FIX CHECKS ===")
    print(f"  echoing guidance text as labels: {len(echo_hits)}/{len(files)}"
          + (f"   e.g. {echo_hits[0]}" if echo_hits else "   (fixed)"))
    print(f"  date of birth missing:           {len(no_dob)}/{len(files)}"
          + (f"   {no_dob[:6]}" if no_dob else "   (fixed)"))
    print(f"  clinical summary empty/short:    {len(empty_clinical)}/{len(files)}"
          + (f"   {empty_clinical[:6]}" if empty_clinical else ""))
    print(f"  clinical summary lacks citations:{len(clin_no_cites)}/{len(files)}"
          + (f"   {clin_no_cites[:6]}" if clin_no_cites else "   (fixed)"))

    print("\n=== 'Not documented' BY SECTION ===")
    for h, n in not_documented.most_common():
        print(f"  {n:3d}/{len(files)}  {h}")

    man = SUMMARY_DIR / "generation_manifest.json"
    if man.exists():
        m = json.loads(man.read_text(encoding="utf-8"))
        eps = [e for e in m.get("episodes", []) if "seconds" in e]
        print("\n=== RUN ===")
        print(f"  model: {m.get('model')}   params: {m.get('parameters')}")
        print(f"  prompt sha256(16): {m.get('prompt_template_sha256_16')}")
        if eps:
            secs = [e["seconds"] for e in eps]
            print(f"  episodes timed: {len(eps)}   "
                  f"per-episode seconds: min {min(secs):.0f} "
                  f"median {statistics.median(secs):.0f} max {max(secs):.0f}")
            print(f"  total generation time: {sum(secs)/3600:.1f} hours")


if __name__ == "__main__":
    main()
