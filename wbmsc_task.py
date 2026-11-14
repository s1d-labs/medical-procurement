"""Task `wbmsc` (scrape.json): www.wbmsc.gov.in, West Bengal Medical Services Corporation Ltd.

Queue items (family.py) have one of two kinds:
  page  {"page": "tender.php", "round": "2026-11"}
        Fetch one page, keep the raw HTML in the bucket (pages/<round>/<page>.html.gz) and, for a listing page, store one
        record per row (id "<section>:<hash of the row's text>"). One record "page:<round>:<page>" describes the snapshot.
  docs  {"section": "tender", "shard": 3, "shards": 24, "round": "2026-11"}
        Fetch the listing, take the documents of this shard, download each one, store it in the bucket by sha256 and store one
        record per version: "doc:<section>/<file>:<sha256[:16]>". A link that does not answer with the file gets a record
        "missing:<section>/<file>:<round>" and a `doc-missing` failure on the dashboard.

Try it without the hub:
  python wbmsc_task.py --local page tender.php
  python wbmsc_task.py --local docs tender 0 400 [save_dir]
"""
import gzip
import hashlib
import json
import os
import sys
import time

from scrape_hub_client import HubClient, LocalHub, stop_flag

import docs
import taskrun
from taskrun import STOP, now, pause, time_up, session, get
import wbmsc

PROJECT = os.environ.get("SCRAPE_POOL_PROJECT", "")
SITE = os.environ.get("SITE", wbmsc.SITE)
_listings = {}            # section -> (fetched at, bytes): a worker that claims several shards fetches the 3 MB listing once


RETRY_WAITS = (10, 30)   # seconds before the 2nd and 3rd try of a document that did not answer


def page_bytes(hub, s, page):
    r = get(hub, s, f"{SITE}/{page}")
    if r is None or r.status_code != 200 or len(r.content) < 500:
        return None
    return r.content


def listing(hub, s, section):
    hit = _listings.get(section)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    data = page_bytes(hub, s, wbmsc.LISTINGS[section])
    if data:
        _listings[section] = (time.time(), data)
    return data


def do_page(hub, s, item):
    p = item["payload"]
    page, rnd = p["page"], p.get("round", "")
    data = page_bytes(hub, s, page)
    if data is None:
        return None, "page did not load"
    path = f"pages/{rnd}/{page}.html.gz"
    up = hub.upload_many([(path, gzip.compress(data), "application/gzip")])
    section = next((sec for sec, pg in wbmsc.LISTINGS.items() if pg == page), None)
    rows = wbmsc.parse_listing(data.decode("utf-8", "replace"), section) if section else []
    seen = now()
    for rid, row in rows:
        hub.record(rid, {**row, "round": rnd, "seen_at": seen, "source": SITE})
    hub.record(f"page:{rnd}:{page}", {"kind": "page", "page": page, "url": f"{SITE}/{page}", "round": rnd, "fetched_at": seen,
                                       "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "rows": len(rows),
                                       "bucket_path": path, "bucket_key": up[0]["key"] if up else None})
    if section and not rows:
        return None, "listing page has no rows (layout changed?)"
    return len(rows) + 1, None


def do_docs(hub, s, item):
    p = item["payload"]
    section, shard, shards, rnd = p["section"], int(p["shard"]), int(p["shards"]), p.get("round", "")
    data = listing(hub, s, section)
    if data is None:
        return None, "listing did not load"
    rows = wbmsc.parse_listing(data.decode("utf-8", "replace"), section)
    links = wbmsc.doc_urls(rows)
    mine = sorted(u for u in links if wbmsc.shard_of(u, shards) == shard)
    stored = errors = 0
    hdr = {"If-Modified-Since": p["since"]} if p.get("since") else None   # weekly rounds: unchanged files answer 304
    for url in mine:
        if time_up():
            return None, "time up before the shard finished"
        file = url.rsplit("/", 1)[-1]
        r = get(hub, s, url, headers=hdr)
        pause(hub)
        for wait in RETRY_WAITS:                       # the server sometimes drops a connection: try again after a pause
            if r is not None or STOP.is_set():
                break
            time.sleep(wait)
            r = get(hub, s, url, headers=hdr)
        if r is None:
            errors += 1
            hub.failure("doc-error", url, "no answer", section=section)
            continue
        hub.clear_failure("doc-error", url)
        if r.status_code == 304:
            stored += 1
            continue
        body = r.content
        if r.status_code != 200 or docs.is_not_found_page(body):
            hub.record(f"missing:{section}/{file}:{rnd}", {"kind": "missing", "url": url, "section": section, "file": file,
                                                           "status": r.status_code, "rows": links[url], "round": rnd,
                                                           "checked_at": now()})
            hub.failure("doc-missing", url, f"HTTP {r.status_code}", section=section)
            stored += 1
            continue
        info, txt = docs.inspect(body, r.headers.get("content-type", ""), file)
        files, fields = docs.uploads(info, body, txt, section)
        up = hub.upload_many(files)
        hub.record(f"doc:{section}/{file}:{info['sha256'][:16]}", {
            "kind": "doc", "url": url, "section": section, "file": file, "rows": links[url], "round": rnd, "fetched_at": now(),
            "last_modified": r.headers.get("last-modified"), "etag": r.headers.get("etag"),
            "content_type": r.headers.get("content-type"), **info, **fields, "bucket_key": up[0]["key"] if up else None})
        stored += 1
    if mine and errors > len(mine) // 2:
        return None, f"{errors} of {len(mine)} documents did not answer"
    return stored, None


HANDLERS = {"page": do_page, "docs": do_docs}


def run(hub):
    taskrun.run(hub, session(), HANDLERS, margin_min=50)


def local(argv):
    kind = argv[0]
    if kind == "page":
        payload = {"kind": "page", "page": argv[1], "round": "local"}
    else:
        payload = {"kind": "docs", "section": argv[1], "shard": int(argv[2]), "shards": int(argv[3]), "round": "local"}
    save = argv[4] if kind == "docs" and len(argv) > 4 else None
    hub = LocalHub(items=[{"key": "local-1", "payload": payload, "attempts": 0}], save_dir=save, delay_ms=500,
                   out=open(os.devnull, "w") if os.environ.get("QUIET") else None)
    run(hub)
    print(json.dumps({"done": hub.done, "failed": hub.failed, "records": hub.records, "counts": hub.counts}), file=sys.stderr)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--local"]:
        local(sys.argv[2:])
    else:
        stop_flag()                                    # install the SIGINT / SIGTERM handlers that set STOP
        run(HubClient(PROJECT, job_index=int(os.environ.get("SCRAPE_JOB_INDEX", "0")),
                      total_jobs=int(os.environ.get("SCRAPE_TOTAL_JOBS", "1"))))
