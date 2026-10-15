#!/usr/bin/env python3
"""
preprocess.py — Stage 1 of the validation-study data pipeline.

Turns the three supplied synthetic CSV files into a clean, deduplicated,
chronologically ordered set of clinical episodes ready for summary generation.

WHAT IT FIXES (see Dataset_Evidence_Report_v1.md for the evidence behind each):
  1. Duplication  — 19 patients appear twice with byte-identical note sets.
                    69 rows collapse to 50 distinct patients / 50 episodes.
  2. Encoding     — mojibake ("Â·", "Â°") in all 69 bed_location values and
                    124 note texts, from a UTF-8/Latin-1 double-encoding.
  3. Broken field — the `ward` column is the literal string "ward" in all rows;
                    real setting is parsed out of `bed_location`.
  4. Dates        — timestamps are DD/MM/YYYY. Parsing without dayfirst=True
                    silently mangles them (e.g. 12/01/2026 -> 1 Dec).
  5. Chronology   — notes are ordered per episode; notes predating the
                    admission timestamp are flagged as pre-admission
                    (legitimate for the 21 booked admissions, which have
                    pre-operative outpatient notes).

OUTPUT
  out/episodes.json        one record per episode, notes ordered, metadata attached
  out/episode_index.csv    flat index for quick inspection
  out/pseudonyms.csv       stable patient pseudonyms for use in figures/screenshots

--------------------------------------------------------------------------
ATTRIBUTION: This file was written with AI assistance (Claude, Anthropic) and
reviewed/adapted by the author. Retained per City St George's MSc Project
Guidance, Appendix C items 7 and 9, which require source code to be identified
as automatically generated, re-used, library or original.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

try:
    import ftfy
except ImportError:  # graceful fallback if ftfy is unavailable
    ftfy = None


# --------------------------------------------------------------------------
# Text repair
# --------------------------------------------------------------------------

def fix_text(value):
    """Repair UTF-8/Latin-1 double-encoding ('Â·' -> '·', 'Â°' -> '°')."""
    if not isinstance(value, str):
        return value
    if ftfy is not None:
        return ftfy.fix_text(value)
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


# --------------------------------------------------------------------------
# Setting derivation
# --------------------------------------------------------------------------

# bed_location looks like: "Neurology Ward · Bay 00 · Bed B00"
def parse_department(bed_location: str) -> str:
    if not isinstance(bed_location, str):
        return "Unknown"
    return bed_location.split("·")[0].strip()


SETTING_PATTERNS = [
    ("Paediatric",  r"paediatric|pediatric|children'?s"),
    ("Orthopaedic", r"orthopaedic|orthopedic|trauma and orth|t&o"),
    ("Respiratory", r"respiratory"),
    ("Neurology",   r"neurolog|neurosurg"),
    ("Acute/Assessment", r"acute medical|assessment unit|\bamu\b|\bsau\b|\bpau\b|observation"),
    ("Surgical",    r"surg"),
]


def classify_setting(department: str) -> list[str]:
    """A department can legitimately match more than one setting
    (e.g. 'Paediatric Orthopaedic Ward 3B')."""
    d = department.lower()
    tags = [name for name, pattern in SETTING_PATTERNS if re.search(pattern, d)]
    return tags or ["Other"]


def is_high_dependency(department: str) -> bool:
    return bool(re.search(r"\bhdu\b|high dependency|\bicu\b|intensive care|critical care",
                          department, re.I))


# --------------------------------------------------------------------------
# Age banding (PRSB-agnostic, used for cohort description only)
# --------------------------------------------------------------------------

AGE_BINS = [0, 1, 5, 12, 18, 40, 65, 75, 200]
AGE_LABELS = ["<1", "1-4", "5-11", "12-17", "18-39", "40-64", "65-74", "75+"]


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data", help="directory holding the three CSVs")
    ap.add_argument("--out", default="out", help="output directory")
    args = ap.parse_args()

    data_dir, out_dir = Path(args.data), Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- load -------------------------------------------------------------
    patients = pd.read_csv(data_dir / "patients.csv")
    admissions = pd.read_csv(data_dir / "admissions.csv")
    notes = pd.read_csv(data_dir / "synthetic_clinical_notes.csv")

    raw_counts = dict(patients=len(patients), admissions=len(admissions), notes=len(notes))

    # ---- 1. deduplicate ---------------------------------------------------
    # patients.csv contains 19 exact duplicate rows.
    patients = patients.drop_duplicates(subset="person_id").reset_index(drop=True)

    # 19 patients have two admission_ids whose note sets are byte-identical.
    # Keep one admission per patient, chosen deterministically by sorted id
    # so that repeated runs of this script give identical output.
    admissions = (admissions.sort_values("admission_id")
                            .drop_duplicates(subset="patient_id")
                            .reset_index(drop=True))
    kept_admissions = set(admissions["admission_id"])
    notes = notes[notes["admission_id"].isin(kept_admissions)].copy()

    # ---- 2. repair encoding ----------------------------------------------
    notes["clean_note_text"] = notes["clean_note_text"].map(fix_text)
    notes["note_subject"] = notes["note_subject"].map(fix_text)
    admissions["bed_location"] = admissions["bed_location"].map(fix_text)

    # ---- 3. derive setting ------------------------------------------------
    admissions["department"] = admissions["bed_location"].map(parse_department)
    admissions["setting_tags"] = admissions["department"].map(classify_setting)
    admissions["high_dependency"] = admissions["department"].map(is_high_dependency)
    admissions = admissions.drop(columns=["ward"])  # literal "ward", carries no information

    # ---- 4. parse dates (dayfirst is essential) ---------------------------
    for col in ("creation_timestamp", "ingest_timestamp", "updt_dt_tm"):
        notes[col] = pd.to_datetime(notes[col], format="mixed", dayfirst=True)
    admissions["admission_timestamp"] = pd.to_datetime(
        admissions["admission_timestamp"], format="mixed", dayfirst=True)
    patients["date_of_birth"] = pd.to_datetime(
        patients["date_of_birth"], format="mixed", dayfirst=True)

    # ---- 5. order chronologically, flag pre-admission ---------------------
    notes = notes.sort_values(["admission_id", "creation_timestamp"]).reset_index(drop=True)
    notes["note_seq"] = notes.groupby("admission_id").cumcount() + 1

    adm_start = admissions.set_index("admission_id")["admission_timestamp"]
    notes["pre_admission"] = (
        notes["creation_timestamp"] < notes["admission_id"].map(adm_start)
    )

    # ---- pseudonyms for figures ------------------------------------------
    pseudo = {pid: f"PT-{i + 1:03d}" for i, pid in enumerate(sorted(patients["person_id"]))}
    pd.DataFrame({"person_id": list(pseudo), "pseudonym": list(pseudo.values())}) \
        .to_csv(out_dir / "pseudonyms.csv", index=False)

    # ---- assemble episodes ------------------------------------------------
    pat_by_id = patients.set_index("person_id")
    episodes, index_rows = [], []

    for adm in admissions.to_dict("records"):
        aid, pid = adm["admission_id"], adm["patient_id"]
        ep_notes = notes[notes["admission_id"] == aid]
        if ep_notes.empty:
            continue
        p = pat_by_id.loc[pid]

        note_records = [{
            "note_id": r["clinical_note_id"],
            "seq": int(r["note_seq"]),
            "timestamp": r["creation_timestamp"].isoformat(),
            "note_type": r["note_type"],
            "note_subject": r["note_subject"],
            "pre_admission": bool(r["pre_admission"]),
            "text": r["clean_note_text"],
        } for r in ep_notes.to_dict("records")]

        first, last = ep_notes["creation_timestamp"].min(), ep_notes["creation_timestamp"].max()

        episodes.append({
            "episode_id": aid,
            "patient": {
                "person_id": pid,
                "pseudonym": pseudo[pid],
                "full_name": p["full_name"],          # synthetic; suppress in figures
                "nhs_number": str(p["nhs_number"]),   # synthetic; suppress in figures
                "date_of_birth": p["date_of_birth"].strftime("%d/%m/%Y"),
                "age": int(p["age"]),
                "gender_identity": p["gender_identity"],
                "is_paediatric": bool(p["age"] < 18),
            },
            "admission": {
                "method": adm["admission_method"],
                "timestamp": adm["admission_timestamp"].isoformat(),
                "bed_location": adm["bed_location"],
                "department": adm["department"],
                "setting_tags": adm["setting_tags"],
                "high_dependency": bool(adm["high_dependency"]),
                "site_name": adm["site_name"],
            },
            "span": {
                "first_note": first.isoformat(),
                "last_note": last.isoformat(),
                "days": round((last - first).total_seconds() / 86400, 2),
            },
            "note_count": len(note_records),
            "pre_admission_note_count": int(ep_notes["pre_admission"].sum()),
            "notes": note_records,
        })

        index_rows.append({
            "episode_id": aid,
            "pseudonym": pseudo[pid],
            "age": int(p["age"]),
            "age_band": pd.cut([p["age"]], bins=AGE_BINS, right=False,
                               labels=AGE_LABELS)[0],
            "is_paediatric": bool(p["age"] < 18),
            "admission_method": adm["admission_method"],
            "department": adm["department"],
            "setting_tags": "|".join(adm["setting_tags"]),
            "note_count": len(note_records),
            "span_days": round((last - first).total_seconds() / 86400, 2),
            "total_chars": int(ep_notes["clean_note_text"].str.len().sum()),
        })

    # ---- write ------------------------------------------------------------
    (out_dir / "episodes.json").write_text(
        json.dumps(episodes, indent=2, ensure_ascii=False), encoding="utf-8")

    idx = pd.DataFrame(index_rows).sort_values("episode_id")
    idx.to_csv(out_dir / "episode_index.csv", index=False)

    # ---- report -----------------------------------------------------------
    print("PREPROCESSING COMPLETE")
    print(f"  raw rows            patients={raw_counts['patients']} "
          f"admissions={raw_counts['admissions']} notes={raw_counts['notes']}")
    print(f"  after deduplication patients={len(patients)} "
          f"episodes={len(episodes)} notes={len(notes)}")
    print(f"  paediatric episodes {int(idx['is_paediatric'].sum())} / {len(idx)}")
    print(f"  aged 65+            {int((idx['age'] >= 65).sum())}")
    print(f"  notes per episode   min={idx['note_count'].min()} "
          f"median={idx['note_count'].median()} max={idx['note_count'].max()}")
    print(f"  episode span (days) min={idx['span_days'].min()} "
          f"median={idx['span_days'].median()} max={idx['span_days'].max()}")
    print(f"  pre-admission notes {int(sum(e['pre_admission_note_count'] for e in episodes))}")
    print(f"  chars per episode   min={idx['total_chars'].min()} "
          f"median={int(idx['total_chars'].median())} max={idx['total_chars'].max()}")
    print(f"\n  wrote {out_dir/'episodes.json'}")
    print(f"  wrote {out_dir/'episode_index.csv'}")
    print(f"  wrote {out_dir/'pseudonyms.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
