"""Tasks `tnmsc`, `rmsc`, `hmscl`, `bmsicl`, `tgmsidc`, `upmscl` and `kmscl` (scrape.json): list pages and documents of a state medical
services corporation.

    python corp_task.py tnmsc        (tnmsc.tn.gov.in, Tamil Nadu)
    python corp_task.py rmsc         (rmsc.health.rajasthan.gov.in, Rajasthan)
    python corp_task.py hmscl        (hmscl.org.in, Haryana)
    python corp_task.py bmsicl       (bmsicl.gov.in, Bihar; HTTP only)
    python corp_task.py tgmsidc      (tgmsidc.telangana.gov.in, Telangana)
    python corp_task.py upmscl       (upmsc.in, Uttar Pradesh)
    python corp_task.py kmscl        (kmscl.kerala.gov.in, Kerala)

Queue items (family.py) have one of two kinds:
  page  {"site": "tnmsc", "page": "blacklist", "arg": null, "round": "2026-11"}
        Fetch one list page, keep the raw HTML in the bucket (pages/<round>/<name>.html.gz), store one record per row (ids from
        the site module) and one record "page:<round>:<name>" for the snapshot.
  docs  {"site": "rmsc", "group": "bans", "shard": 0, "shards": 2, "round": "2026-11"}
        Fetch the group's list pages, take the linked documents of this shard, download each one, store it in the bucket by sha256
        (scans under ocr-needed/, OCR is off) and store one record per version: "doc:<sha1(url)[:12]>:<sha256[:16]>". A link that
        does not give the file gets "missing:<sha1(url)[:12]>:<round>" and a `doc-missing` failure. If the site module has
        parse_doc(url, bytes, rows that link it), the rows of the document (rate contracts, blacklists in PDFs) are stored too.

Try it without the hub:
  python corp_task.py tnmsc --local page blacklist
  python corp_task.py rmsc --local page equipment-tenders
  python corp_task.py rmsc --local docs bans 0 2 [save_dir]
"""
import gzip
import hashlib
import inspect
import json
import os
import re
import sys
import time

from scrape_hub_client import HubClient, LocalHub, stop_flag, timed_get

import docs
import taskrun
from taskrun import now, pause, time_up, session
import bmsicl
import hmscl
import htmltables
import kmscl
import rmsc
import tgmsidc
import tnmsc
import upmscl

SITES = {"tnmsc": tnmsc, "rmsc": rmsc, "hmscl": hmscl, "bmsicl": bmsicl, "tgmsidc": tgmsidc, "upmscl": upmscl, "kmscl": kmscl}
PROJECT = os.environ.get("SCRAPE_POOL_PROJECT", "")
_pages = {}                # (site, page, arg) -> (fetched at, text): a worker with several doc shards fetches each list once


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
    by_id = dict(rows)
    mine = sorted(u for u in links if htmltables.shard_of(u, shards) == shard)
    stored = errors = 0
    hdr = {"If-Modified-Since": p["since"]} if p.get("since") else None   # weekly rounds: unchanged files answer 304
    for url in mine:
        if time_up():
            return None, "time up before the shard finished"
        r = timed_get(hub, s, url, timeout=120, allow_redirects=True, headers=hdr)
        pause(hub)
        if r is None:
            errors += 1
            hub.failure("doc-error", url[:200], "no answer", group=group)
            continue
        if r.status_code == 304:
            stored += 1
            continue
        if hasattr(mod, "attachments") and r.status_code == 200 and docs.kind_of(r.content) == "html":
            # a post page (BMSICL): its order files are the documents
            subs = mod.attachments(url, r.text)
            if not subs:
                hub.failure("doc-missing", url[:200], "post page has no attachment", group=group)
            for sub in subs:
                if time_up():
                    return None, "time up before the shard finished"
                rs = timed_get(hub, s, sub, timeout=120, allow_redirects=True)
                pause(hub)
                if rs is None:
                    errors += 1
                    hub.failure("doc-error", sub[:200], "no answer", group=group)
                    continue
                stored += store_doc(hub, mod, site, group, sub, rs, links[url], rnd, post_url=url,
                                    link_rows=[by_id[i] for i in links[url] if i in by_id])
            continue
        stored += store_doc(hub, mod, site, group, url, r, links[url], rnd,
                            link_rows=[by_id[i] for i in links[url] if i in by_id])
    if mine and errors > len(mine) // 2:
        return None, f"{errors} of {len(mine)} documents did not answer"
    return stored, None


def store_doc(hub, mod, site, group, url, r, row_ids, rnd, post_url=None, link_rows=None):
    """Store one downloaded document (or a "missing" record); rows parsed from it (rate contract files) become records too.
    A site module's parse_doc(url, body, txt[, link_rows]) gets the list rows that link the document when it takes a 4th argument
    (their title tells which kind of document it is)."""
    uid = hashlib.sha1(url.encode()).hexdigest()[:12]
    file = _file_name(url, r)
    body = r.content
    if r.status_code != 200 or (len(body) < 4000 and docs.kind_of(body) == "html"):
        hub.record(f"missing:{uid}:{rnd}", {"kind": "missing", "site": site, "url": url, "group": group, "file": file,
                                            "status": r.status_code, "rows": row_ids, "post_url": post_url, "round": rnd,
                                            "checked_at": now()})
        hub.failure("doc-missing", url[:200], f"HTTP {r.status_code}", group=group)
        return 1
    info, txt = docs.inspect(body, r.headers.get("content-type", ""), file)
    files, fields = docs.uploads(info, body, txt, group)
    up = hub.upload_many(files)
    hub.record(f"doc:{uid}:{info['sha256'][:16]}", {
        "kind": "doc", "site": site, "url": url, "group": group, "file": file, "rows": row_ids, "post_url": post_url,
        "round": rnd, "fetched_at": now(), "last_modified": r.headers.get("last-modified"), "etag": r.headers.get("etag"),
        "content_type": r.headers.get("content-type"), **info, **fields, "bucket_key": up[0]["key"] if up else None})
    if hasattr(mod, "parse_doc"):
        seen = now()
        args = (url, body, txt, link_rows or []) if len(inspect.signature(mod.parse_doc).parameters) >= 4 else (url, body, txt)
        try:
            parsed = mod.parse_doc(*args)
        except Exception as e:                           # a document that does not parse is still stored
            hub.failure("doc-parse", url[:200], f"{type(e).__name__}: {e}"[:200], group=group)
            parsed = []
        for r_id, row in parsed:
            hub.record(r_id, {**row, "site": site, "round": rnd, "seen_at": seen, "source_doc": url,
                              "doc_sha256": info["sha256"]})
    return 1


def _file_name(url, r):
    """The file name from Content-Disposition when the URL has none (download.php?id=...), else the last URL segment."""
    cd = r.headers.get("content-disposition") or ""
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd, re.I)
    return m.group(1).strip() if m else url.rsplit("/", 1)[-1]


HANDLERS = {"page": do_page, "docs": do_docs}


def run(hub):
    taskrun.run(hub, session(), HANDLERS, margin_min=0)


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
