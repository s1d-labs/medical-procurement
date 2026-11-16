r"""Tenders cancelled after the price bids were opened, matched to a later awarded tender of the same corporation (title
similarity >= 0.85 after removing tender numbers and filler, published 0-550 days later). Output -> medproc.retender_pairs.

Input (TSV, no header): corp, tender_id, stage, published, title, l1_bidder, l1_bid_value, winner, awarded_value,
bids_count, award_date, reached_finance (t/f), n_bids:
  psql -d ws_trideep -At -F$'\t' -c "with f as (select corp, tender_id, bool_or(status ilike '%finance%') fin, count(*) nb from medproc.medcorp_bids group by 1,2) select r.corp, r.tender_id, r.stage, t.published::date, regexp_replace(r.title,'[\t\n]',' ','g'), r.l1_bidder, r.l1_bid_value, t.winner, t.awarded_value, t.bids_count, t.award_date::date, f.fin, f.nb from medproc.medcorp_tenders_raw r join medproc.medcorp_tenders t using (corp, tender_id) left join f using (corp, tender_id)" > all.tsv
Rate contracts (MPPHSCL) compare unit rates with totals: read ratios there with care.
Usage: python3 analysis/retender_pairs.py all.tsv retender_pairs.csv
"""
import sys
import csv, re, difflib, datetime as dt
from collections import defaultdict
K = lambda s: re.sub(r"[^A-Z0-9]", "", (s or "").upper().replace("PRIVATE", "PVT").replace("LIMITED", "LTD"))
def T(s):  # title without tender numbers, dates and filler
    s = re.sub(r"(?i)\b(tender|e-?tender|nit|no|ref|re-?tender|retender|online|dated?|for|the|of|and|at|in)\b", " ", s or "")
    s = re.sub(r"[^a-z ]", " ", s.lower()); return " ".join(w for w in s.split() if len(w) > 2)
D = lambda s: dt.date.fromisoformat(s) if s else None
F = lambda s: float(s) if s not in ("", None) else 0.0
rows = list(csv.reader(open(sys.argv[1]), delimiter="\t"))
byc = defaultdict(list)
for r in rows: byc[r[0]].append(r)
out = []
for r in rows:
    corp, tid, stage, pub, title, l1, l1v, *_ , fin, nb = r
    if "Cancel" not in stage or fin != "t" or F(l1v) <= 0 or not l1: continue
    t0, p0 = T(title), D(pub)
    best = None
    for s in byc[corp]:
        if s[1] == tid or not s[7] or F(s[8]) <= 0 or not D(s[3]) or not p0: continue
        gap = (D(s[3]) - p0).days
        if not (0 <= gap <= 550): continue
        sc = difflib.SequenceMatcher(None, t0, T(s[4])).ratio()
        if sc >= 0.85 and (best is None or sc > best[0] or (sc == best[0] and gap < best[1])):
            best = (sc, gap, s)
    if best:
        sc, gap, s = best
        out.append(dict(corp=corp, cancelled=tid, published=pub, title=title[:90], cancelled_l1=l1, cancelled_l1_value=F(l1v),
                        retender=s[1], re_published=s[3], re_winner=s[7], re_value=F(s[8]), re_bids=s[9], same_firm=K(l1) == K(s[7]),
                        ratio=round(F(s[8]) / F(l1v), 2), score=round(sc, 2), gap_days=gap))
w = csv.DictWriter(open(sys.argv[2], "w"), fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
print(len(out), "matched;", sum(o["same_firm"] for o in out), "same firm won again")
for o in sorted(out, key=lambda o: -o["re_value"] + o["cancelled_l1_value"])[:15]:
    print(o["corp"], o["cancelled"], o["cancelled_l1"][:22], round(o["cancelled_l1_value"]/1e5,1), "->", o["retender"], o["re_winner"][:22], round(o["re_value"]/1e5,1), "lakh", o["ratio"], "x", o["re_bids"], "bids", o["gap_days"], "d |", o["title"][:50])
