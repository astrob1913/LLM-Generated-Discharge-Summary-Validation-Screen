"""
Linking summary statements to records: three methods compared on episode 0219fb71,
scored against hand-verified links.

A  distinctive-term overlap   tokens rarer than a cutoff; N shared terms required
B  idf-weighted, record level  every content token scores log(N/df); threshold on the sum
C  idf-weighted, sentence level as B, but the record is scored by its best single line

C is the one the interface would use if it wins, because a link it draws can be
explained by naming the line that produced it.
"""
import json, re, math, collections

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
    return pr, rc, (2*pr*rc/(pr+rc) if pr+rc else 0), per, (tp, fp, fn)

def main():
    ep = [e for e in json.load(open("out/episodes.json"))
          if e["episode_id"].startswith("0219fb71")][0]
    recs = {f"N{n['seq']}": n["text"] for n in ep["notes"]}
    print(f"episode 0219fb71 · {len(recs)} records · 14 statements scored "
          f"(2 settled as field checks)\n")

    print(f"  {'method':34} {'precision':>10} {'recall':>8} {'F1':>7}")
    best = {}
    for label, m, params in [("A  distinctive-term overlap", "A", [(0, 0.30, 2)]),
                             ("B  idf-weighted, whole record", "B", [(t, 0, 0) for t in (2,3,4,5,6,7,8)]),
                             ("C  idf-weighted, best line", "C", [(t, 0, 0) for t in (2,3,4,5,6,7,8)])]:
        top = None
        for thr, dmx, mh in params:
            pred, why = score_all(recs, m, thr, dmx or 0.30, mh or 2)
            pr, rc, f1, per, tot = score(pred)
            if top is None or f1 > top[0]:
                top = (f1, pr, rc, thr, pred, why, per, tot)
        f1, pr, rc, thr, pred, why, per, tot = top
        tag = f"{label}" + (f"  (threshold {thr})" if m != "A" else "")
        print(f"  {tag:34} {pr:>10.2f} {rc:>8.2f} {f1:>7.2f}")
        best[m] = top

    bm = max(best, key=lambda m: best[m][0])          # by F1, not hard-coded
    f1, pr, rc, thr, pred, why, per, (tp, fp, fn) = best[bm]
    print(f"\nBEST METHOD BY F1: {bm} — F1 {f1:.2f} — "
          f"{tp} correct, {fp} spurious, {fn} missed\n")
    print(f"{'statement':10} {'hit':>4} {'extra':>6} {'miss':>5}   remaining error")
    for k in STATEMENTS:
        if k in FIELD:
            print(f"{k:10} {'—':>4} {'—':>6} {'—':>5}   field check"); continue
        a, b, c = per[k]
        ex = sorted(set(pred[k]) - set(TRUTH[k]), key=lambda x: int(x[1:]))
        ms = sorted(set(TRUTH[k]) - set(pred[k]), key=lambda x: int(x[1:]))
        msg = ("spurious " + ",".join(ex) + " " if ex else "") + ("missed " + ",".join(ms) if ms else "")
        print(f"{k:10} {a:>4} {b:>6} {c:>5}   {msg or 'exact'}")

    print("\nTHE TWO RECORDS THAT MATTER MOST — does the method find them?")
    for k, want in (("trip", ["N26","N29"]),):
        for rid in want:
            got = rid in pred[k]
            det = why[k].get(rid)
            print(f"  {rid}  {'FOUND' if got else 'MISSED'}"
                  + (f"  score {det[0]:.1f} on: \"{det[2]}\"" if det else "  (below threshold)"))

if __name__ == "__main__":
    main()
