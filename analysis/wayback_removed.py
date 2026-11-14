"""Rows of WBMSC listings in Wayback copies that are not in the current listing. Usage: removed.py PAGES_DIR OUT_CSV"""
import csv, gzip, os, re, subprocess, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import wbmsc
D, OUT = sys.argv[1], sys.argv[2]
q = """select data->>'listing', data->>'captured_first', data->>'captured_last', data->>'bucket_key' from records
 where project in ('medical-procurement-wbmsc-wayback','medical-procurement-wbmsc') and (data ? 'listing' or record_id like 'page:%')"""
rows = [l.split("|") for l in subprocess.run(["psql", "-d", "scrape_hub", "-Atc", q], capture_output=True, text=True).stdout.splitlines()]
cur_q = "select data->>'bucket_key' from records where project='medical-procurement-wbmsc' and record_id in ('page:2026-11:tender.php','page:2026-11:notice.php')"
def key(d):
    norm = lambda x: re.sub(r"[^a-z0-9]", "", (x or "").lower())
    return (d["section"], norm(d["number"]), d.get("date") or norm(d.get("date_raw")), norm(d["title"])[:120])
def load(bkey):
    f = os.path.join(D, bkey.replace("/", "_"))
    if not os.path.exists(f):
        subprocess.run(["mybucket", "get", bkey, f], capture_output=True)
    b = open(f, "rb").read()
    if b[:2] == b"\x1f\x8b": b = gzip.decompress(b)
    return b.decode("utf-8", "replace")
current = {}
for bkey in subprocess.run(["psql", "-d", "scrape_hub", "-Atc", cur_q], capture_output=True, text=True).stdout.split():
    sec = "tender" if "tender.php" in bkey else "notice"
    for _, d in wbmsc.parse_listing(load(bkey), sec):
        current[key(d)] = d
old = {}
for listing, first, last, bkey in rows:
    if listing not in ("tender", "notice") or not bkey: continue
    for _, d in wbmsc.parse_listing(load(bkey), listing):
        k = key(d)
        o = old.setdefault(k, {**d, "seen_first": first, "seen_last": last})
        o["seen_first"] = min(o["seen_first"], first); o["seen_last"] = max(o["seen_last"], last)
gone = [d for k, d in old.items() if k not in current]
with open(OUT, "w", newline="") as f:
    w = csv.writer(f)
    for d in gone:
        w.writerow([d["section"], d["number"], d.get("date"), d["title"], d.get("url"), d["seen_first"], d["seen_last"], d.get("kind")])
print("current", len(current), "archived distinct", len(old), "not in current", len(gone))
