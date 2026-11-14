"""Tasks `tnmsc` and `rmsc` (scrape.json): list pages and documents of a state medical services corporation.

    python corp_task.py tnmsc        (tnmsc.tn.gov.in, Tamil Nadu)
    python corp_task.py rmsc         (rmsc.health.rajasthan.gov.in, Rajasthan)

Queue items (family.py) have one of two kinds:
  page  {"site": "tnmsc", "page": "blacklist", "arg": null, "round": "2026-11"}
        Fetch one list page, keep the raw HTML in the bucket (pages/<round>/<name>.html.gz), store one record per row (ids from
        the site module) and one record "page:<round>:<name>" for the snapshot.
  docs  {"site": "rmsc", "group": "bans", "shard": 0, "shards": 2, "round": "2026-11"}
        Fetch the group's list pages, take the linked documents of this shard, download each one, store it in the bucket by sha256
        (scans under ocr-needed/, OCR is off) and store one record per version: "doc:<sha1(url)[:12]>:<sha256[:16]>". A link that
        does not give the file gets "missing:<sha1(url)[:12]>:<round>" and a `doc-missing` failure.

Try it without the hub:
  python corp_task.py tnmsc --local page blacklist
  python corp_task.py rmsc --local page equipment-tenders
  python corp_task.py rmsc --local docs bans 0 2 [save_dir]
"""
import gzip
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests
from scrape_hub_client import HubClient, LocalHub, ca_bundle, stop_flag, timed_get

import docs
import htmltables
import rmsc
import tnmsc

SITES = {"tnmsc": tnmsc, "rmsc": rmsc}
PROJECT = os.environ.get("SCRAPE_POOL_PROJECT", "")
DEADLINE = time.time() + float(os.environ.get("SCRAPE_MAX_HOURS", "1")) * 3600 - 180
UA = "s1d-labs scraper (https://github.com/s1d-labs)"
STOP = stop_flag(install=False)
_pages = {}                # (site, page, arg) -> (fetched at, text): a worker with several doc shards fetches each list once


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def session():
    s = requests.Session()
    s.headers["User-Agent"] = UA
    s.verify = ca_bundle()
    return s


def pause(hub):
    time.sleep(max(1.0, hub.settings.get("delay_ms", 0) / 1000))


def fetch_page(hub, s, site, page, arg, cache=True):
    """(text, bytes) of a list page, or (None, None)."""
    key = (site, page, arg)
    hit = _pages.get(key)
    if cache and hit and time.time() - hit[0] < 3600:
        return hit[1], hit[2]
    r = timed_get(hub, s, SITES[site].page_url(page, arg), timeout=120, allow_redirects=True)
    if r is None or r.status_code != 200 or len(r.content) < 500:
        return None, None
    if not r.encoding or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding or "utf-8"
    _pages[key] = (time.time(), r.text, r.content)
    return r.text, r.content


def do_page(hub, s, item):
    p = item["payload"]
    site, page, arg, rnd = p["site"], p["page"], p.get("arg"), p.get("round", "")
    mod = SITES[site]
    text, data = fetch_page(hub, s, site, page, arg, cache=False)
    if text is None:
        return None, "page did not load"
    name = htmltables.page_name(page, arg)
    path = f"pages/{rnd}/{name}.html.gz"
    up = hub.upload_many([(path, gzip.compress(data), "application/gzip")])
    rows = mod.parse(page, text, arg)
    seen = now()
    for r_id, row in rows:
        hub.record(r_id, {**row, "site": site, "round": rnd, "seen_at": seen})
    hub.record(f"page:{rnd}:{name}", {"kind": "page", "site": site, "page": page, "arg": arg, "url": mod.page_url(page, arg),
                                      "round": rnd, "fetched_at": seen, "bytes": len(data),
                                      "sha256": hashlib.sha256(data).hexdigest(), "rows": len(rows), "bucket_path": path,
                                      "bucket_key": up[0]["key"] if up else None})
    if not rows and p.get("expected", 0) > 1:
        return None, "list page has no rows (layout changed?)"
    return len(rows) + 1, None


def do_docs(hub, s, item):
    p = item["payload"]
    site, group, shard, shards, rnd = p["site"], p["group"], int(p["shard"]), int(p["shards"]), p.get("round", "")
    mod = SITES[site]
    rows = []
    for page, arg in mod.DOC_GROUPS[group]:
        text, _ = fetch_page(hub, s, site, page, arg)
        if text is None:
            return None, f"list {htmltables.page_name(page, arg)} did not load"
        rows += mod.parse(page, text, arg)
        pause(hub)
    links = mod.doc_urls(rows)
    mine = sorted(u for u in links if htmltables.shard_of(u, shards) == shard)
    stored = errors = 0
    for url in mine:
        if STOP.is_set() or time.time() > DEADLINE:
            return None, "time up before the shard finished"
        uid = hashlib.sha1(url.encode()).hexdigest()[:12]
        file = url.rsplit("/", 1)[-1]
        r = timed_get(hub, s, url, timeout=120, allow_redirects=True)
        pause(hub)
        if r is None:
            errors += 1
            hub.failure("doc-error", url[:200], "no answer", group=group)
            continue
        body = r.content
        if r.status_code != 200 or (len(body) < 4000 and docs.kind_of(body) == "html"):
            hub.record(f"missing:{uid}:{rnd}", {"kind": "missing", "site": site, "url": url, "group": group, "file": file,
                                                "status": r.status_code, "rows": links[url], "round": rnd, "checked_at": now()})
            hub.failure("doc-missing", url[:200], f"HTTP {r.status_code}", group=group)
            stored += 1
            continue
        info, txt = docs.inspect(body, r.headers.get("content-type", ""), file)
        files, fields = docs.uploads(info, body, txt, group)
        up = hub.upload_many(files)
        hub.record(f"doc:{uid}:{info['sha256'][:16]}", {
            "kind": "doc", "site": site, "url": url, "group": group, "file": file, "rows": links[url], "round": rnd,
            "fetched_at": now(), "last_modified": r.headers.get("last-modified"), "etag": r.headers.get("etag"),
            "content_type": r.headers.get("content-type"), **info, **fields, "bucket_key": up[0]["key"] if up else None})
        stored += 1
    if mine and errors > len(mine) // 2:
        return None, f"{errors} of {len(mine)} documents did not answer"
    return stored, None


HANDLERS = {"page": do_page, "docs": do_docs}


def run(hub):
    s = session()
    try:
        while time.time() < DEADLINE and not STOP.is_set():
            if hub.settings.get("paused"):
                time.sleep(30)
                continue
            items = hub.claim(1, steal=True, retry_failed=True)
            if not items:
                break
            item = items[0]
            kind = item["payload"].get("kind")
            if kind not in HANDLERS or item["payload"].get("site") not in SITES:
                hub.complete([item["key"]], "failed", error=f"unknown item {kind!r} / {item['payload'].get('site')!r}")
                continue
            n, err = HANDLERS[kind](hub, s, item)
            if err:
                hub.complete([item["key"]], "failed", error=err[:200])
            else:
                hub.complete([item["key"]], "done", fetched=n)
            pause(hub)
        if STOP.is_set():
            hub.close("failed", "stopped by signal")
        else:
            hub.close()
    except BaseException as e:
        hub.close("failed", f"{type(e).__name__}: {e}"[:200])
        raise


def local(site, argv):
    kind = argv[0]
    if kind == "page":
        payload = {"kind": "page", "site": site, "page": argv[1], "arg": argv[2] if len(argv) > 2 else None, "round": "local"}
        save = None
    else:
        payload = {"kind": "docs", "site": site, "group": argv[1], "shard": int(argv[2]), "shards": int(argv[3]), "round": "local"}
        save = argv[4] if len(argv) > 4 else None
    if payload.get("arg") and payload["arg"].isdigit():
        payload["arg"] = int(payload["arg"])
    hub = LocalHub(items=[{"key": "local-1", "payload": payload, "attempts": 0}], save_dir=save, delay_ms=1000,
                   out=open(os.devnull, "w") if os.environ.get("QUIET") else None)
    run(hub)
    print(json.dumps({"done": hub.done, "failed": hub.failed, "records": hub.records, "counts": hub.counts}), file=sys.stderr)


if __name__ == "__main__":
    site = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CORP_SITE", "")
    if site not in SITES:
        sys.exit(f"usage: corp_task.py {{{','.join(SITES)}}} [--local page <page> [arg] | --local docs <group> <shard> <shards> [dir]]")
    if sys.argv[2:3] == ["--local"]:
        local(site, sys.argv[3:])
    else:
        stop_flag()
        run(HubClient(PROJECT, job_index=int(os.environ.get("SCRAPE_JOB_INDEX", "0")),
                      total_jobs=int(os.environ.get("SCRAPE_TOTAL_JOBS", "1"))))
