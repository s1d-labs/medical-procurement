"""Task `mpphscl` (scrape.json): mpphscl.mp.gov.in, Madhya Pradesh Public Health Services Corporation Ltd.

Queue items (family.py) have one of two kinds:
  page  {"page": "TenderALL.aspx", "round": "2026-11"}
        Fetch one list page, keep the raw HTML in the bucket (pages/<round>/<page>.html.gz) and store one record per row:
        "tender:<number>:<hash>" (with every linked document and its label) or "blacklist-<firm|product|lab>:<hash>".
        One record "page:<round>:<page>" describes the snapshot.
  docs  {"group": "tender" | "blacklist", "shard": 3, "shards": 120, "round": "2026-11"}
        Fetch the group's list page(s), take the documents of this shard, download each one, store it in the bucket by sha256
        (scans under ocr-needed/, OCR is off) and store one record per version: "doc:<group>/<sha1 of url[:12]>:<sha256[:16]>"
        with the label, the document kind (comparative, rate_list, final_status, ...) and the rows that link it.
        A link that does not give the file gets "missing:<group>/<sha1 of url[:12]>:<round>" and a `doc-missing` failure.

The server only talks to clients that allow legacy TLS renegotiation (OpenSSL 3 refuses it by default): session() sets
OP_LEGACY_SERVER_CONNECT. Certificate verification stays on.

Try it without the hub:
  python mpphscl_task.py --local page BlackListFirm.aspx
  python mpphscl_task.py --local docs blacklist 0 40 [save_dir]
"""
import gzip
import hashlib
import json
import os
import ssl
import sys
import time
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from scrape_hub_client import HubClient, LocalHub, ca_bundle, stop_flag, timed_get

import docs
import mpphscl

PROJECT = os.environ.get("SCRAPE_POOL_PROJECT", "")
SITE = os.environ.get("SITE", mpphscl.SITE)
DEADLINE = time.time() + float(os.environ.get("SCRAPE_MAX_HOURS", "1")) * 3600 - 180
UA = "s1d-labs scraper (https://github.com/s1d-labs)"
STOP = stop_flag(install=False)
GROUPS = {"tender": [mpphscl.TENDERS], "blacklist": list(mpphscl.BLACKLISTS.values())}
_pages = {}               # page -> (fetched at, bytes): the 11.5 MB tender list is fetched once per hour per process


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LegacyTLS(HTTPAdapter):
    """Verified TLS that also allows the server's legacy renegotiation."""

    def init_poolmanager(self, *a, **kw):
        ctx = ssl.create_default_context(cafile=ca_bundle())
        ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
        kw["ssl_context"] = ctx
        return super().init_poolmanager(*a, **kw)

    def proxy_manager_for(self, proxy, **kw):         # the same context through HTTPS_PROXY (proxy="IN")
        ctx = ssl.create_default_context(cafile=ca_bundle())
        ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
        kw["ssl_context"] = ctx
        return super().proxy_manager_for(proxy, **kw)


def session():
    s = requests.Session()
    s.headers["User-Agent"] = UA
    s.mount("https://", LegacyTLS())
    return s


def pause(hub):
    time.sleep(max(1.0, hub.settings.get("delay_ms", 0) / 1000))


def get(hub, s, url, timeout=120, **kw):
    return timed_get(hub, s, url, timeout=timeout, allow_redirects=True, **kw)


def page_bytes(hub, s, page, cache=False):
    hit = _pages.get(page)
    if cache and hit and time.time() - hit[0] < 3600:
        return hit[1]
    r = get(hub, s, f"{SITE}/{page}")
    if r is None or r.status_code != 200 or len(r.content) < 2000:
        return None
    _pages[page] = (time.time(), r.content)
    return r.content


def parse(page, data):
    body = data.decode("utf-8", "replace")
    if page == mpphscl.TENDERS:
        return mpphscl.parse_tenders(body)
    which = next((w for w, p in mpphscl.BLACKLISTS.items() if p == page), None)
    return mpphscl.parse_blacklist(body, which) if which else []


def do_page(hub, s, item):
    p = item["payload"]
    page, rnd = p["page"], p.get("round", "")
    data = page_bytes(hub, s, page)
    if data is None:
        return None, "page did not load"
    path = f"pages/{rnd}/{page}.html.gz"
    up = hub.upload_many([(path, gzip.compress(data), "application/gzip")])
    rows = parse(page, data)
    seen = now()
    for rid, row in rows:
        hub.record(rid, {**row, "page": page, "round": rnd, "seen_at": seen, "source": SITE})
    hub.record(f"page:{rnd}:{page}", {"kind": "page", "page": page, "url": f"{SITE}/{page}", "round": rnd, "fetched_at": seen,
                                       "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "rows": len(rows),
                                       "bucket_path": path, "bucket_key": up[0]["key"] if up else None})
    if page in mpphscl.PAGES and not rows and page != mpphscl.BLACKLISTS["lab"]:
        return None, "list page has no rows (layout changed?)"
    return len(rows) + 1, None


def do_docs(hub, s, item):
    p = item["payload"]
    group, shard, shards, rnd = p["group"], int(p["shard"]), int(p["shards"]), p.get("round", "")
    rows = []
    for page in GROUPS[group]:
        data = page_bytes(hub, s, page, cache=True)
        if data is None:
            return None, f"{page} did not load"
        rows += parse(page, data)
    links = mpphscl.doc_urls(rows)
    mine = sorted(u for u in links if mpphscl.shard_of(u, shards) == shard)
    stored = errors = 0
    hdr = {"If-Modified-Since": p["since"]} if p.get("since") else None   # weekly rounds: unchanged files answer 304
    for url in mine:
        if STOP.is_set() or time.time() > DEADLINE:
            return None, "time up before the shard finished"
        file = mpphscl.file_of(url)
        uid = hashlib.sha1(url.encode()).hexdigest()[:12]
        r = get(hub, s, url, headers=hdr)
        pause(hub)
        if r is None:
            errors += 1
            hub.failure("doc-error", url[:200], "no answer", group=group)
            continue
        if r.status_code == 304:
            stored += 1
            continue
        body = r.content
        info, txt = docs.inspect(body, r.headers.get("content-type", ""), file)
        if r.status_code != 200 or (info["type"] == "html" and not file.lower().endswith((".htm", ".html"))):
            hub.record(f"missing:{group}/{uid}:{rnd}", {"kind": "missing", "url": url, "group": group, "file": file,
                                                        "status": r.status_code, "rows": links[url], "round": rnd,
                                                        "checked_at": now()})
            hub.failure("doc-missing", url[:200], f"HTTP {r.status_code}", group=group)
            stored += 1
            continue
        files, fields = docs.uploads(info, body, txt, group)
        up = hub.upload_many(files)
        hub.record(f"doc:{group}/{uid}:{info['sha256'][:16]}", {
            "kind": "doc", "url": url, "group": group, "file": file, "rows": links[url],
            "doc_kinds": sorted({x["kind"] for x in links[url]}), "gepnic_ids": mpphscl.gepnic_ids(txt), "round": rnd,
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
            if kind not in HANDLERS:
                hub.complete([item["key"]], "failed", error=f"unknown item kind {kind!r}")
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


def local(argv):
    kind = argv[0]
    if kind == "page":
        payload = {"kind": "page", "page": argv[1], "round": "local"}
    else:
        payload = {"kind": "docs", "group": argv[1], "shard": int(argv[2]), "shards": int(argv[3]), "round": "local"}
    save = argv[4] if kind == "docs" and len(argv) > 4 else None
    hub = LocalHub(items=[{"key": "local-1", "payload": payload, "attempts": 0}], save_dir=save, delay_ms=1000,
                   out=open(os.devnull, "w") if os.environ.get("QUIET") else None)
    run(hub)
    print(json.dumps({"done": hub.done, "failed": hub.failed, "records": hub.records, "counts": hub.counts}), file=sys.stderr)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--local"]:
        local(sys.argv[2:])
    else:
        stop_flag()
        run(HubClient(PROJECT, job_index=int(os.environ.get("SCRAPE_JOB_INDEX", "0")),
                      total_jobs=int(os.environ.get("SCRAPE_TOTAL_JOBS", "1"))))
