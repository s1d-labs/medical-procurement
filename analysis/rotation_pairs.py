r"""Firm pairs that take turns: they meet at the price stage (bids not rejected technically) in 5+ single-winner tenders
with 2-6 price bids, each wins 2+, and together they win 80 %+. Output -> medproc.rotation_pairs.

Input (TSV, no header: corp, tender_id, firm key, firm name, won t/f, awarded value, published):
  psql -d ws_trideep -At -F$'\t' -c "select b.corp, b.tender_id, upper(regexp_replace(regexp_replace(b.bidder,'(?i)\m(private|pvt|limited|ltd|m/s)\M','','g'),'[^A-Za-z0-9]','','g')) k, min(b.bidder), bool_or(b.status ilike '%AOC%' and b.status ilike 'Accepted%'), coalesce(t.awarded_value,0), t.published::date from medproc.medcorp_bids b join medproc.medcorp_tenders t using (corp,tender_id) where b.status not ilike '%technical%' and b.status not ilike 'not admitted%' and t.winner is not null and t.winner not like '%;%' group by 1,2,3,6,7" > price_stage.tsv
Usage: python3 analysis/rotation_pairs.py price_stage.tsv rotation_pairs.csv
"""
import sys
import csv, itertools
from collections import defaultdict
T = defaultdict(list); val = {}; pub = {}
for corp, tid, k, name, won, v, p in csv.reader(open(sys.argv[1]), delimiter="\t"):
    T[(corp, tid)].append((k, name, won == "t")); val[(corp, tid)] = float(v or 0); pub[(corp, tid)] = p
pair = defaultdict(lambda: {"n": 0, "a": 0, "b": 0, "v": 0.0, "only": 0, "years": set()})
names = {}
for key, bs in T.items():
    if len(bs) < 2 or len(bs) > 6: continue
    for (k1, n1, w1), (k2, n2, w2) in itertools.combinations(sorted(bs), 2):
        names[k1], names[k2] = n1, n2
        d = pair[(key[0], k1, k2)]
        d["n"] += 1; d["a"] += w1; d["b"] += w2; d["v"] += val[key] if (w1 or w2) else 0
        d["only"] += len(bs) == 2; d["years"].add(pub[key][:4])
rows = []
for (corp, k1, k2), d in pair.items():
    if d["n"] >= 5 and d["a"] >= 2 and d["b"] >= 2 and d["a"] + d["b"] >= 0.8 * d["n"]:
        rows.append((corp, names[k1][:28], names[k2][:28], d["n"], d["a"], d["b"], d["only"], round(d["v"] / 1e7, 1), ",".join(sorted(d["years"]))))
rows.sort(key=lambda r: -r[7])
w = csv.writer(open(sys.argv[2], "w")); w.writerow(["corp", "firm_a", "firm_b", "met_at_price", "a_won", "b_won", "only_two", "cr_won_by_pair", "years"]); w.writerows(rows)
for r in rows[:25]: print(*r, sep=" | ")
print(len(rows), "pairs")
