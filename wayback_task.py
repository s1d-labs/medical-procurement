"""Task `wayback` (scrape.json): old versions of a site's pages and documents from the Internet Archive's Wayback Machine.

Why: www.wbmsc.gov.in overwrites old tender documents when it reuses a random file number (see wbmsc.py). The Wayback Machine holds
copies made before the overwrite (in Nov 2026: 821 of the 2,017 overwritten tender documents), and 60+ old copies of each listing
page, which show tenders that later left the public list.

Queue item: {"prefix": "wbmsc.gov.in/*", "shard": 3, "shards": 24}
  1. Read the CDX index of every 200 capture under `prefix` (cached for the process).
  2. Group captures by (path, content digest): one distinct content = one unit of work. Keep this shard's units.
  3. Download each unit's earliest capture raw (`/web/<ts>id_/<url>`), store it by sha256, store one record
     "wb:<path>:<digest[:16]>" with every capture time of that content.
Images, stylesheets and scripts are skipped.

Try it without the hub:  python wayback_task.py --local wbmsc.gov.in/* 0 200 [save_dir]
"""
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from scrape_hub_client import HubClient, LocalHub, stop_flag, timed_get

import docs
import wbmsc

PROJECT = os.environ.get("SCRAPE_POOL_PROJECT", "")
BUDGET_S = float(os.environ.get("SCRAPE_MAX_HOURS", "1")) * 3600
DEADLINE = time.time() + BUDGET_S - 180
# a shard takes up to ~30 min: do not claim one that cannot finish (a retry starts the shard again from the start)
CLAIM_MARGIN_S = 30 * 60 if BUDGET_S > 3 * 30 * 60 else 0
UA = "s1d-labs scraper (https://github.com/s1d-labs)"
CDX = "https://web.archive.org/cdx/search/cdx"
STOP = stop_flag(install=False)
SKIP_MIME = re.compile(r"^(image/|text/css|application/(x-)?javascript|text/javascript|font/|application/font)", re.I)
SKIP_PATH = re.compile(r"\.(gif|png|jpe?g|ico|css|js|svg|woff2?|ttf|eot)$", re.I)
_cdx = {}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pause(hub, floor=1.0):
    time.sleep(max(floor, hub.settings.get("delay_ms", 0) / 1000))


def norm_path(original):
    """'http://www.wbmsc.gov.in:80/tender/x.pdf?' -> 'wbmsc.gov.in/tender/x.pdf' (host without www, no port, no empty query)."""
    u = re.sub(r"^https?://", "", original.strip(), flags=re.I)
    host, _, rest = u.partition("/")
    host = re.sub(r":(80|443)$", "", host.lower())
    host = re.sub(r"^www\.", "", host)
    return f"{host}/{rest}".rstrip("?")


def units(rows):
    """CDX rows [timestamp, original, statuscode, digest, length, mimetype] -> {(path, digest): {...}}, skipping assets."""
    out = {}
    for row in rows:
        ts, original, status, digest, length, mime = (row + [""] * 6)[:6]
        if status != "200" or not digest:
            continue
        path = norm_path(original)
        if SKIP_MIME.match(mime or "") or SKIP_PATH.search(path.split("?")[0]):
            continue
        u = out.setdefault((path, digest), {"path": path, "digest": digest, "mime": mime, "captures": []})
        u["captures"].append((ts, original))
    for u in out.values():
        u["captures"].sort()
    return out


def section_of(path):
    """wbmsc.gov.in/tender/x.pdf -> 'tender'; a page (tender.php, /) -> 'pages'."""
    parts = path.split("/")
    return parts[1].lower() if len(parts) > 2 and parts[1] else "pages"


def cdx_rows(hub, s, prefix):
    if prefix in _cdx:
        return _cdx[prefix]
    params = {"url": prefix, "output": "json", "fl": "timestamp,original,statuscode,digest,length,mimetype",
              "filter": "statuscode:200", "limit": "200000"}
    for attempt in range(4):
        r = timed_get(hub, s, CDX, params=params, timeout=180)
        if r is not None and r.status_code == 200 and r.text.strip().startswith("["):
            rows = r.json()[1:]
            _cdx[prefix] = rows
            return rows
        time.sleep(20 * (attempt + 1))
    return None


def fetch_capture(hub, s, unit):
    """Raw bytes of the first capture that downloads, with its timestamp; (None, None) if none does (tries 3)."""
    for ts, original in unit["captures"][:3]:
        r = timed_get(hub, s, f"https://web.archive.org/web/{ts}id_/{original}", timeout=120)
        pause(hub)
        if r is not None and r.status_code == 200 and r.content:
            return r, ts
        if r is not None and r.status_code == 429:
            time.sleep(60)
    return None, None


def do_unit(hub, s, unit, site):
    r, ts = fetch_capture(hub, s, unit)
    path, digest = unit["path"], unit["digest"]
    rid = f"wb:{path}:{digest[:16]}"
    if len(rid) > 190:
        rid = f"wb:{hashlib.sha1(path.encode()).hexdigest()}:{digest[:16]}"
    if r is None:
        hub.failure("wayback-error", rid, "no capture downloaded", path=path)
        return False
    body = r.content
    section = section_of(path)
    file = path.rsplit("/", 1)[-1] or "index"
    info, txt = docs.inspect(body, r.headers.get("content-type", ""), file)
    extra = {}
    if site == "wbmsc" and info["type"] == "html":
        listing = next((sec for sec, pg in wbmsc.LISTINGS.items() if path.endswith("/" + pg)), None)
        if listing:
            extra["listing"] = listing
            extra["listing_rows"] = len(wbmsc.parse_listing(body.decode("utf-8", "replace"), listing))
        txt = ""                                                     # keep HTML as it is; no text file for pages
    files, fields = docs.uploads(info, body, txt, section, prefix="wayback/")
    up = hub.upload_many(files)
    caps = unit["captures"]
    hub.record(rid, {"kind": "wayback", "site": site, "path": path, "section": section, "file": file, "digest": digest,
                     "mime": unit["mime"], "captured_first": caps[0][0], "captured_last": caps[-1][0], "captures": len(caps),
                     "timestamps": [c[0] for c in caps][:100], "downloaded_ts": ts, "original": caps[0][1],
                     "fetched_at": now(), **info, **fields, **extra, "bucket_key": up[0]["key"] if up else None})
    hub.clear_failure("wayback-error", rid)
    return True


def do_shard(hub, s, item):
    p = item["payload"]
    rows = cdx_rows(hub, s, p["prefix"])
    if rows is None:
        return None, "CDX index did not load"
    us = units(rows)
    mine = sorted((u for u in us.values() if wbmsc.shard_of(u["digest"], int(p["shards"])) == int(p["shard"])),
                  key=lambda u: u["path"])
    ok = bad = 0
    for u in mine:
        if STOP.is_set() or time.time() > DEADLINE:
            return None, "time up before the shard finished"
        if do_unit(hub, s, u, p.get("site", "")):
            ok += 1
        else:
            bad += 1
    if mine and bad > len(mine) // 3:
        return None, f"{bad} of {len(mine)} captures did not download"
    return ok, None


def run(hub):
    s = requests.Session()
    s.headers["User-Agent"] = UA
    try:
        while time.time() < DEADLINE and not STOP.is_set():
            if hub.settings.get("paused"):
                time.sleep(30)
                continue
            if DEADLINE - time.time() < CLAIM_MARGIN_S:
                break                                  # too little time left for a whole shard: leave it to a fresh worker
            items = hub.claim(1, steal=True, retry_failed=True)
            if not items:
                break
            item = items[0]
            n, err = do_shard(hub, s, item)
            if err:
                hub.complete([item["key"]], "failed", error=err[:200])
            else:
                hub.complete([item["key"]], "done", fetched=n)
        if STOP.is_set():
            hub.close("failed", "stopped by signal")
        else:
            hub.close()
    except BaseException as e:
        hub.close("failed", f"{type(e).__name__}: {e}"[:200])
        raise


def local(argv):
    payload = {"prefix": argv[0], "shard": int(argv[1]), "shards": int(argv[2]), "site": "wbmsc"}
    hub = LocalHub(items=[{"key": "local-1", "payload": payload, "attempts": 0}], save_dir=argv[3] if len(argv) > 3 else None,
                   delay_ms=1500, out=open(os.devnull, "w") if os.environ.get("QUIET") else None)
    run(hub)
    print(json.dumps({"done": hub.done, "failed": hub.failed, "records": hub.records, "counts": hub.counts}), file=sys.stderr)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--local"]:
        local(sys.argv[2:])
    else:
        stop_flag()
        run(HubClient(PROJECT, job_index=int(os.environ.get("SCRAPE_JOB_INDEX", "0")),
                      total_jobs=int(os.environ.get("SCRAPE_TOTAL_JOBS", "1"))))
