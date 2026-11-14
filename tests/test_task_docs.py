"""The WBMSC document loop on a fake site: stored, unchanged (304), missing (404) and no answer. No network."""
import io
import json
from pathlib import Path

import requests
from scrape_hub_client import LocalHub

import wbmsc_task

PAGE = (Path(__file__).parent / "pages" / "wbmsc-tender.html").read_bytes()


class Resp:
    def __init__(self, status, content=b"", headers=None):
        self.status_code, self.content, self.headers = status, content, headers or {}


class FakeSite:
    """tender.php gives the saved list; the first 4 document links answer 304, 404, nothing, and a PDF; the rest 304."""
    def __init__(self, urls):
        self.answers = dict(zip(urls, ["304", "404", "none", "pdf"]))
        self.sent = []

    def request(self, method, url, **kw):
        self.sent.append((url, kw.get("headers")))
        if url.endswith("tender.php"):
            return Resp(200, PAGE)
        a = self.answers.get(url, "304")
        if a == "none":
            raise requests.ConnectionError("dropped")
        if a == "404":
            return Resp(404, b"<html><title>Object not found!</title></html>")
        if a == "pdf":
            return Resp(200, b"%PDF-1.4 " + b"x" * 300, {"content-type": "application/pdf"})
        return Resp(304)


def test_doc_loop_kinds(monkeypatch):
    monkeypatch.setattr(wbmsc_task, "RETRY_WAITS", ())
    monkeypatch.setattr(wbmsc_task, "pause", lambda hub: None)
    rows = wbmsc_task.wbmsc.parse_listing(PAGE.decode("utf-8", "replace"), "tender")
    urls = sorted(wbmsc_task.wbmsc.doc_urls(rows))
    site, out = FakeSite(urls), io.StringIO()
    hub = LocalHub(out=out)
    item = {"key": "k", "payload": {"kind": "docs", "section": "tender", "shard": 0, "shards": 1, "round": "t",
                                    "since": "Fri, 06 Nov 2026 00:00:00 GMT"}}
    n, err = wbmsc_task.do_docs(hub, site, item)
    kinds = [json.loads(line)["record_id"].split(":")[0] for line in out.getvalue().splitlines()]
    assert err is None and kinds.count("doc") == 1 and kinds.count("missing") == 1
    assert all(h == {"If-Modified-Since": "Fri, 06 Nov 2026 00:00:00 GMT"} for u, h in site.sent if u != wbmsc_task.SITE + "/tender.php")
    assert n == len(urls) - 1                          # everything except the document that did not answer
