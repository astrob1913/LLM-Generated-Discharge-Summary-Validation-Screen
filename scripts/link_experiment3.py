"""
Linking summary statements to records: three methods compared on episode 0219fb71,
scored against hand-verified links.

A  distinctive-term overlap    tokens rarer than a cutoff; N shared terms required
B  idf-weighted, record level  every content token scores log(N/df); threshold on the sum
C  idf-weighted, sentence level  as B, but the record is scored by its best single line

WHAT CHANGED FROM link_experiment2.py, AND WHY
----------------------------------------------
v2 chose the best threshold within each method by F1, and then the best method by F1.
F1 weights precision and recall equally. For this task they are not equal.

The linking step does not decide anything. It puts candidate records in front of a
clinician, who decides. So:

  a MISSED link  -> the clinician never sees a record that contradicts the summary.
                    This is the dangerous error.
  a SPURIOUS link -> the clinician reads a record that turns out to be irrelevant.
                    This costs seconds and is self-correcting.

Optimising F1 treats those as equally bad and therefore picks the wrong operating
point for a screen with a human filter downstream. This version changes nothing about
the methods — it reports the whole precision/recall trade-off and three operating
points side by side, so the choice is visible rather than baked in:

  BEST F1       reproduces the v2 headline, so the earlier figure stays checkable
  BEST F2       F-beta with beta=2, which weights recall twice as heavily as precision
  MAX RECALL    the most complete retrieval available, whatever precision costs

It also prints the concrete cost of each point: how many irrelevant records a
clinician would have to read, per statement, to buy that recall.

Nothing here proves that a high-recall operating point is usable. That is a question
for the evaluation, not for this script.
"""
import json, re, math, collections
from pathlib import Path

# ---- find episodes.json whether this is run from pipeline/ or pipeline/scripts/ ----
HERE = Path(__file__).resolve().parent
CANDIDATES = [HERE / "out" / "episodes.json",
              HERE.parent / "out" / "episodes.json",
              Path("out/episodes.json"),
              Path("../out/episodes.json")]
EPISODES = next((p for p in CANDIDATES if p.exists()), None)
if EPISODES is None:
    raise SystemExit(
        "Cannot find out/episodes.json.\n"
        "Put this script in the pipeline folder (beside 'out' and 'data'),\n"
        "or in pipeline/scripts/, and run it with:  python link_experiment3.py\n"
        "Looked in:\n  " + "\n  ".join(str(p) for p in CANDIDATES))

STOP = set("""a an the and or of to in on for with without at by from as is are was were be been
being this that these those it its their his her patient patients no not none any all each per
today plan review reviewed continue continues start started initiate initiated during following
after before within due next further other than then there here have has had do does did will
would may might can could should if when while also more most less least new old same
day days mg ml kg hrs hr hours hour daily od bd tds qds prn po iv im sc noted note nil
assessed provided given seen well good stable normal today's dr nurse gmc nmc number""".split())

STATEMENTS = {
 "nhs":"NHS number: 141670292",
 "dob":"Date of birth: 15/06/2004",
 "dx":"Primary diagnosis: Reversible cerebral vasoconstriction syndrome (RCVS)",
 "dx2":"Secondary diagnoses: Not documented",
 "dest":"Discharge destination: Home",
 "ct":"CT head: No evidence of intracranial haemorrhage or signs of raised ICP or mass lesion.",
 "bloods":"Blood tests (FBC, U&E, CRP): Pending and normal upon discharge",
 "mri":"MRI angiogram: Confirmed findings consistent with RCVS",
 "lp":"Lumbar puncture (LP) planned but not performed during this episode",
 "amlo":"Discharge medications: Amlodipine 5 mg OD",
 "nimo":"Changes made during admission: Nimodipine 60 mg PO q4h",
 "trip":"Triptans (sumatriptan 50 mg) and paracetamol (1 g every 6 hours) for headache relief",
 "allergy":"Known allergy: Pollen",
 "ther":"Patient underwent physiotherapy assessment and mobility review, relaxation therapy, and cognitive therapy sessions.",
 "edu":"Detailed educational materials on RCVS, recognising symptoms, lifestyle modifications, and when to seek help",
 "fu":"Follow-up arrangements: Neurology OP review in 4 weeks",
}
TRUTH = {
 "nhs":[], "dob":[], "dx2":[], "dest":[],
 "dx":["N6","N26"], "ct":["N4","N5"], "bloods":["N5","N24","N26","N29"],
 "mri":["N12","N26","N29"], "lp":["N4","N5","N6"], "amlo":["N26","N29","N30"],
 "nimo":["N5","N6","N7","N13","N19","N21","N24"], "trip":["N9","N10","N13","N26","N29"],
 "allergy":["N1","N5","N6"], "ther":["N8","N14","N20"], "edu":["N28"],
 "fu":["N26","N29","N30"],
}
FIELD = {"nhs","dob"}
SCORED = [k for k in STATEMENTS if k not in FIELD]

def norm(t):
    t = re.sub(r"([a-z])([A-Z])", r"\1 \2", t).lower().replace("&"," and ")
    return re.sub(r"[^a-z0-9\s/-]", " ", t)

def toks(t):
    return [w.strip("-/") for w in norm(t).split()
            if len(w.strip("-/")) >= 3 and w.strip("-/") not in STOP and not w.isdigit()]

def lines(t):
    parts = re.split(r"(?<=[.;])\s+|\n+|(?<=\d\.)\s", t)
    return [p for p in parts if len(p.strip()) > 12]

def score_all(records, method, thr, df_max=0.30, min_hits=2):
    N = len(records)
    df = collections.Counter()
    for t in records.values():
        df.update(set(toks(t)))
    idf = {w: math.log(N / c) for w, c in df.items()}
    distinctive = {w for w, c in df.items() if c / N <= df_max}

    pred, why = {}, {}
    for k, s in STATEMENTS.items():
        if k in FIELD:
            pred[k] = []; continue
        st = set(toks(s))
        hits = {}
        for rid, txt in records.items():
            if method == "A":
                shared = st & distinctive & set(toks(txt))
                if len(shared) >= min_hits:
                    hits[rid] = (len(shared), sorted(shared), "")
            elif method == "B":
                shared = st & set(toks(txt))
                sc = sum(idf.get(w, 0) for w in shared)
                if sc >= thr:
                    hits[rid] = (sc, sorted(shared, key=lambda w: -idf.get(w, 0)), "")
            else:                                     # C — best single line
                best = (0, [], "")
                for ln in lines(txt):
                    shared = st & set(toks(ln))
                    sc = sum(idf.get(w, 0) for w in shared)
                    if sc > best[0]:
                        best = (sc, sorted(shared, key=lambda w: -idf.get(w, 0)), ln.strip()[:90])
                if best[0] >= thr:
                    hits[rid] = best
        pred[k] = sorted(hits, key=lambda r: int(r[1:]))
        why[k] = hits
    return pred, why

def fbeta(pr, rc, beta):
    b2 = beta * beta
    return (1 + b2) * pr * rc / (b2 * pr + rc) if (b2 * pr + rc) else 0

def score(pred):
    tp = fp = fn = 0
    per = {}
    for k, t in TRUTH.items():
        if k in FIELD: continue
        p, t = set(pred[k]), set(t)
        a, b, c = len(p & t), len(p - t), len(t - p)
        tp += a; fp += b; fn += c
        per[k] = (a, b, c)
    pr = tp / (tp + fp) if tp + fp else 0
    rc = tp / (tp + fn) if tp + fn else 0
    return dict(pr=pr, rc=rc, f1=fbeta(pr, rc, 1), f2=fbeta(pr, rc, 2),
                per=per, tp=tp, fp=fp, fn=fn)

def sweep(recs):
    """Every method at every threshold. One row per operating point."""
    # v2 swept thresholds 2..8 only. The recall end of the curve lives below 2, and that
    # is the half of the trade-off this script exists to show, so the sweep starts lower.
    THR = [0.5, 1, 1.5, 2, 3, 4, 5, 6, 7, 8]
    grid = [("A", "distinctive-term overlap", [(0, 0.30, 2)])]
    grid += [("B", "idf-weighted, whole record", [(t, 0, 0) for t in THR])]
    grid += [("C", "idf-weighted, best line",  [(t, 0, 0) for t in THR])]
    rows = []
    for m, label, params in grid:
        for thr, dmx, mh in params:
            pred, why = score_all(recs, m, thr, dmx or 0.30, mh or 2)
            s = score(pred)
            s.update(method=m, label=label, thr=thr, pred=pred, why=why)
            rows.append(s)
    return rows

def show_point(title, s, n_scored):
    """One operating point, with the cost of it stated in records-to-read."""
    print(f"\n{title}")
    print(f"  method {s['method']}" + (f", threshold {s['thr']:g}" if s['method'] != "A" else "")
          + f"  —  precision {s['pr']:.2f}   recall {s['rc']:.2f}   "
            f"F1 {s['f1']:.2f}   F2 {s['f2']:.2f}")
    print(f"  {s['tp']} correct, {s['fp']} spurious, {s['fn']} missed")
    print(f"  cost: the clinician reads {s['fp']/n_scored:.1f} irrelevant records per "
          f"statement on average")
    print(f"  risk: {s['fn']} true link{'' if s['fn']==1 else 's'} never shown at all")
    tripfound = [r for r in ("N26","N29") if r in s['pred']['trip']]
    print(f"  the two triptan stop records (N26, N29): "
          + (", ".join(tripfound) + " found" if tripfound else "NEITHER found")
          + (f"  [{2-len(tripfound)} still missed]" if len(tripfound) < 2 else ""))

def main():
    ep = [e for e in json.load(open(EPISODES, encoding="utf-8"))
          if e["episode_id"].startswith("0219fb71")][0]
    recs = {f"N{n['seq']}": n["text"] for n in ep["notes"]}
    n_scored = len(SCORED)
    print(f"episode 0219fb71 · {len(recs)} records · {n_scored} statements scored "
          f"({len(FIELD)} settled as field checks)")
    print(f"data: {EPISODES}")
    print(f"ground truth: {sum(len(v) for k, v in TRUTH.items() if k not in FIELD)} "
          f"hand-verified links\n")

    rows = sweep(recs)

    # ---- the whole trade-off, not one point ----
    print("ALL OPERATING POINTS")
    print(f"  {'method':32} {'thr':>4} {'prec':>6} {'recall':>7} {'F1':>6} {'F2':>6}"
          f" {'miss':>5} {'spur':>5}")
    for s in rows:
        tag = f"{s['method']}  {s['label']}"
        thr = "—" if s["method"] == "A" else f"{s['thr']:g}"
        print(f"  {tag:32} {thr:>4} {s['pr']:>6.2f} {s['rc']:>7.2f} "
              f"{s['f1']:>6.2f} {s['f2']:>6.2f} {s['fn']:>5} {s['fp']:>5}")

    best_f1  = max(rows, key=lambda s: s['f1'])
    best_f2  = max(rows, key=lambda s: s['f2'])
    best_rc  = max(rows, key=lambda s: (s['rc'], s['pr']))

    show_point("BEST BY F1  (what link_experiment2.py reported — precision and recall "
               "weighted equally)", best_f1, n_scored)
    show_point("BEST BY F2  (recall weighted twice as heavily — the clinician is the filter)",
               best_f2, n_scored)
    show_point("MAX RECALL  (the most complete retrieval these methods reach)",
               best_rc, n_scored)

    # ---- per-statement detail at the recall-weighted point ----
    s = best_f2
    print(f"\nPER STATEMENT at the F2 point (method {s['method']}"
          + (f", threshold {s['thr']:g}" if s['method'] != "A" else "") + ")")
    print(f"  {'statement':10} {'hit':>4} {'extra':>6} {'miss':>5}   remaining error")
    for k in STATEMENTS:
        if k in FIELD:
            print(f"  {k:10} {'—':>4} {'—':>6} {'—':>5}   field check"); continue
        a, b, c = s['per'][k]
        ex = sorted(set(s['pred'][k]) - set(TRUTH[k]), key=lambda x: int(x[1:]))
        ms = sorted(set(TRUTH[k]) - set(s['pred'][k]), key=lambda x: int(x[1:]))
        msg = ("spurious " + ",".join(ex) + " " if ex else "") + \
              ("missed " + ",".join(ms) if ms else "")
        print(f"  {k:10} {a:>4} {b:>6} {c:>5}   {msg or 'exact'}")

    print("\nREAD THIS BEFORE QUOTING ANY NUMBER ABOVE")
    print("  These are three lexical methods on one episode with 14 scored statements.")
    print("  They do not measure what an embedding model, an entailment model or an LLM")
    print("  would achieve — none of those was tested. A high recall figure here is not")
    print("  evidence that a high-recall operating point is workable in practice: that")
    print("  depends on whether a clinician tolerates the spurious records it brings,")
    print("  which is an evaluation question and is not answered by this script.")

if __name__ == "__main__":
    main()
