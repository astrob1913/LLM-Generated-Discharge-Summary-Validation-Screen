"""
Which records support which summary statement?

Tests one unsupervised method against hand-verified links for episode 0219fb71.

Method: distinctive-term overlap.
  A token is 'distinctive' for this episode if it occurs in at most DF_MAX of the
  30 records. A record is linked to a statement if they share at least MIN_HITS
  distinctive tokens. No clinical lexicon, no model, no training.

Why this method first: it is explainable. The interface can state the reason for
every link it draws ("both mention sumatriptan, which occurs in 3 of 30 records"),
which R3 and R10 both require.
"""
import json, re, sys, collections

EPISODE = "0219fb71"
DF_MAX, MIN_HITS = 0.34, 1          # tunable; swept below

# ---- the 16 checkable statements, verbatim from the generated summary --------
STATEMENTS = {
 "nhs":     "NHS number: 141670292",
 "dob":     "Date of birth: 15/06/2004",
 "dx":      "Primary diagnosis: Reversible cerebral vasoconstriction syndrome (RCVS)",
 "dx2":     "Secondary diagnoses: Not documented",
 "dest":    "Discharge destination: Home",
 "ct":      "CT head: No evidence of intracranial haemorrhage or signs of raised ICP or mass lesion.",
 "bloods":  "Blood tests (FBC, U&E, CRP): Pending and normal upon discharge",
 "mri":     "MRI angiogram: Confirmed findings consistent with RCVS",
 "lp":      "Lumbar puncture (LP) planned but not performed during this episode",
 "amlo":    "Discharge medications: Amlodipine 5 mg OD",
 "nimo":    "Changes made during admission: Nimodipine 60 mg PO q4h",
 "trip":    "Triptans (sumatriptan 50 mg) and paracetamol (1 g every 6 hours) for headache relief",
 "allergy": "Known allergy: Pollen",
 "ther":    "Patient underwent physiotherapy assessment and mobility review, relaxation therapy, "
            "and cognitive therapy sessions.",
 "edu":     "Detailed educational materials on RCVS, recognising symptoms, lifestyle modifications, "
            "and when to seek help",
 "fu":      "Follow-up arrangements: Neurology OP review in 4 weeks",
}

# ---- hand-verified links (Section 4.3, checked against the 30 records) -------
TRUTH = {
 "nhs": [], "dob": [], "dx2": [], "dest": [],
 "dx":      ["N6","N26"],
 "ct":      ["N4","N5"],
 "bloods":  ["N5","N24","N26","N29"],
 "mri":     ["N12","N26","N29"],
 "lp":      ["N4","N5","N6"],
 "amlo":    ["N26","N29","N30"],
 "nimo":    ["N5","N6","N7","N13","N19","N21","N24"],
 "trip":    ["N9","N10","N13","N26","N29"],
 "allergy": ["N1","N5","N6"],
 "ther":    ["N8","N14","N20"],
 "edu":     ["N28"],
 "fu":      ["N26","N29","N30"],
}
FIELD_CHECKS = {"nhs", "dob"}       # settled against patients.csv, not the notes

STOP = set("""a an the and or of to in on for with without at by from as is are was were be been
being this that these those it its their his her patient patients no not none any all each per
today plan review reviewed continue continues start started initiate initiated during following
after before within due next further other than then there here have has had do does did will
would may might can could should if when while also more most less least new old same day days
mg ml kg hrs hr hours hour daily od bd tds qds prn po iv im sc""".split())

def norm(t):
    t = t.lower()
    t = re.sub(r"([a-z])([A-Z])", r"\1 \2", t)
    t = t.replace("&", " and ")
    t = re.sub(r"[^a-z0-9\s/-]", " ", t)
    return t

def toks(t):
    out = []
    for w in norm(t).split():
        w = w.strip("-/")
        if len(w) < 3 or w in STOP or w.isdigit():
            continue
        out.append(w)
    return out

def run(records, df_max, min_hits):
    n = len(records)
    df = collections.Counter()
    for txt in records.values():
        df.update(set(toks(txt)))
    distinctive = {w for w, c in df.items() if c / n <= df_max}

    predicted, reasons = {}, {}
    for k, s in STATEMENTS.items():
        if k in FIELD_CHECKS:
            predicted[k] = []
            continue
        keys = set(toks(s)) & distinctive
        hits = {}
        for rid, txt in records.items():
            shared = keys & set(toks(txt))
            if len(shared) >= min_hits:
                hits[rid] = sorted(shared)
        predicted[k] = sorted(hits, key=lambda r: int(r[1:]))
        reasons[k] = hits
    return predicted, reasons, distinctive

def score(pred):
    tp = fp = fn = 0
    per = {}
    for k, truth in TRUTH.items():
        if k in FIELD_CHECKS:
            continue
        p, t = set(pred[k]), set(truth)
        a, b, c = len(p & t), len(p - t), len(t - p)
        tp += a; fp += b; fn += c
        per[k] = (a, b, c)
    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
    return prec, rec, f1, per, (tp, fp, fn)

def main():
    eps = json.load(open("out/episodes.json"))
    ep = [e for e in eps if e["episode_id"].startswith(EPISODE)][0]
    records = {f"N{n['seq']}": n["text"] for n in ep["notes"]}
    print(f"episode {ep['episode_id']}  ·  {len(records)} records  ·  "
          f"{len(STATEMENTS)} statements, {len(FIELD_CHECKS)} settled as field checks\n")

    print("PARAMETER SWEEP")
    print(f"  {'df_max':>7} {'min_hits':>9} {'precision':>10} {'recall':>8} {'F1':>7}")
    best = None
    for df_max in (0.20, 0.25, 0.30, 0.34, 0.40, 0.50):
        for min_hits in (1, 2):
            pred, _, _ = run(records, df_max, min_hits)
            p, r, f1, _, _ = score(pred)
            print(f"  {df_max:>7.2f} {min_hits:>9} {p:>10.2f} {r:>8.2f} {f1:>7.2f}")
            if best is None or f1 > best[0]:
                best = (f1, df_max, min_hits)
    f1, df_max, min_hits = best
    print(f"\nBEST: df_max={df_max}, min_hits={min_hits}, F1={f1:.2f}\n")

    pred, reasons, distinctive = run(records, df_max, min_hits)
    p, r, f1, per, (tp, fp, fn) = score(pred)
    print(f"distinctive vocabulary: {len(distinctive)} tokens "
          f"(occurring in <= {df_max:.0%} of records)")
    print(f"links: {tp} correct, {fp} spurious, {fn} missed  |  "
          f"precision {p:.2f}  recall {r:.2f}  F1 {f1:.2f}\n")

    print(f"{'statement':10} {'hit':>4} {'extra':>6} {'miss':>5}   what went wrong")
    for k in STATEMENTS:
        if k in FIELD_CHECKS:
            print(f"{k:10} {'—':>4} {'—':>6} {'—':>5}   settled against patients.csv")
            continue
        a, b, c = per[k]
        extra = sorted(set(pred[k]) - set(TRUTH[k]), key=lambda x: int(x[1:]))
        miss = sorted(set(TRUTH[k]) - set(pred[k]), key=lambda x: int(x[1:]))
        note = ""
        if extra: note += "spurious " + ",".join(extra) + " "
        if miss:  note += "missed " + ",".join(miss)
        print(f"{k:10} {a:>4} {b:>6} {c:>5}   {note or 'exact match'}")

    print("\nWHY EACH LINK WAS DRAWN (the reason the interface would show)")
    for k in ("trip", "nimo", "bloods", "dest"):
        print(f"\n  {k} — \"{STATEMENTS[k][:64]}...\"")
        if not reasons.get(k):
            print("     no record shares a distinctive term  ->  no evidence")
        for rid, shared in sorted(reasons[k].items(), key=lambda x: int(x[0][1:])):
            mark = "ok " if rid in TRUTH[k] else "XX "
            print(f"     {mark}{rid:4} shares: {', '.join(shared[:6])}")

if __name__ == "__main__":
    main()
