"""Pure parsing of upmsc.in (Uttar Pradesh Medical Supplies Corporation Ltd.): no network, tested on saved pages.

Pages (checked 2026-11-14; ASP.NET MVC, server HTML, no pagination):
  nsq        /Home/NSQ ("Blacklisting"): firms blacklisted for an NSQ drug batch (drug, firm, firm address, reason, order number,
             date, years, order PDF). The order PDFs are scans (the batch number is only there): they go to ocr-needed/.
  tenders    /Home/tenders?cat=6: all tenders (drugs, equipment, consumables, QC, other) with their documents: NIT, corrigenda,
             technical and financial results, "approved items list for L1 and matched L1 bidders" (rate contracts).
Copyright policy of the site: contents are not to be reproduced without written permission. Use the data as facts with the
source, not as copies of the pages.
"""
import html as _html
import re
from urllib.parse import quote, urljoin

import htmltables as H
import pdftables as P

SITE = "https://upmsc.in"
_PATHS = {"nsq": "/Home/NSQ", "tenders": "/Home/tenders?cat=6"}
PAGES = [("nsq", None), ("tenders", None)]
DOC_GROUPS = {"nsq-orders": [("nsq", None)], "results": [("tenders", None)]}

# documents of a tender row that are stored ("results" group); NITs, bid documents and plain corrigenda are not
_DOC_KINDS = [("rate-list", r"rate accept|approved items? list|matched L1|L1 and matched|rate contract"),
              ("financial-result", r"financ|price bid|commercial"),
              ("technical-result", r"technical|tech\.? result|qualified|responsive"),
              ("result", r"result|award|\bLOI\b|letter of intent")]
STORED_KINDS = {k for k, _ in _DOC_KINDS}


def page_url(page, arg=None):
    return SITE + _PATHS[page]


def url_of(href):
    """Absolute URL of a link of the site: backslashes become slashes, spaces are encoded."""
    if not href:
        return None
    h = _html.unescape(href.strip()).replace("\\", "/")
    h = re.sub(r"/{2,}", "/", h)
    return quote(urljoin(SITE + "/", h), safe=":/?&=%#()+,;~@!$*'")


def doc_kind(title):
    t = title or ""
    return next((k for k, rx in _DOC_KINDS if re.search(rx, t, re.I)), "other")


def parse_nsq(html):
    """Blacklisted firms (NSQ drug batch): one record per row, with the order PDF."""
    out = []
    for t in H.tables(html):
        head = [x.lower() for x in t.header()]
        if not head or "firm name" not in head:
            continue
        col = {h: i for i, h in enumerate(head)}
        for i, row in enumerate(t.data_rows(), 1):
            c = [x.text for x in row]
            if len(c) < 8:
                continue
            g = lambda name: c[col[name]] if name in col and col[name] < len(c) else ""      # noqa: E731
            particular = g("particular")
            drug = re.sub(r"^\s*Firm Blacklisted for drug\s*[-:]\s*", "", particular, flags=re.I).strip()
            orders = list(dict.fromkeys(url_of(h) for cell in row for h, _ in cell.links if url_of(h)))
            years = H.num(g("duration of blacklisting(in year)"))
            d = {"kind": "blacklist", "list": "nsq", "position": i, "drug": drug, "particular": particular,
                 "firm": g("firm name"), "firm_address": g("firm address"), "reason": g("reason of blacklisting"),
                 "nsq": bool(re.search(r"\bNSQ\b|not of standard", g("reason of blacklisting"), re.I)),
                 "order_no": g("order number"), "date": H.iso_date(g("blacklisting date")), "date_raw": g("blacklisting date"),
                 "years": years, "orders": orders, "source": page_url("nsq")}
            out.append((H.rid("nsq", d["firm"], drug, d["order_no"], d["date_raw"]), d))
    return out


_TR = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
_TD = re.compile(r"<td\b[^>]*>(.*?)</td>", re.S | re.I)
_LI = re.compile(r"<li\b[^>]*>(.*?)</li>", re.S | re.I)


def _text(fragment):
    return H.clean(_html.unescape(re.sub(r"<[^>]+>", " ", fragment)))


def _docs_in(fragment):
    """[{title, url, kind}] of the documents in a cell (each one is an <li> with a title and eye/download links)."""
    out = []
    parts = _LI.findall(fragment) or [fragment]
    for li in parts:
        hrefs = list(dict.fromkeys(re.findall(r'href="(/(?:Corrigendum|Tender|Nsq)Files[^"]+)"', li)))
        if not hrefs:
            continue
        m = re.search(r'data-fulltext="([^"]*)"', li) or re.search(r'class="full-text"[^>]*>(.*?)</span>', li, re.S) or \
            re.search(r'class="preview-text">([^<]*)<', li)
        title = H.clean(_html.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))) if m else _text(li)
        title = re.sub(r"\s*hi\.{3,}\s*$", "", title)
        for h in hrefs:
            u = url_of(h)
            out.append({"title": title, "url": u, "kind": doc_kind(f"{title} {u}")})
    return out


def parse_tenders(html):
    """All tenders: one record per row (number, description, dates, documents with their titles and kinds)."""
    out = []
    seen = {}
    for tr in _TR.findall(html):
        m = re.search(r'tenderDetails\?tenderId=([^"&]+)', tr)
        if not m:
            continue
        tds = _TD.findall(tr)
        if len(tds) < 7:
            continue
        number = _text(tds[1])
        files = _docs_in(tds[5]) + _docs_in(tds[6])
        d = {"kind": "tender", "number": number, "description": _text(tds[2]), "start": H.iso_date(_text(tds[3])),
             "end": H.iso_date(_text(tds[4])), "start_raw": _text(tds[3]), "end_raw": _text(tds[4]),
             "detail_url": url_of("/Home/tenderDetails?tenderId=" + m.group(1)), "files": files,
             "n_files": len(files), "source": page_url("tenders")}
        key = H.rid("tender", number, d["start_raw"], *[f["url"] for f in files])
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:                            # the same row twice on the page: keep both
            key = f"{key}-{seen[key]}"
        out.append((key, d))
    return out


def parse(page, html, arg=None):
    return parse_nsq(html) if page == "nsq" else parse_tenders(html)


def doc_urls(rows):
    """{url: [record ids]}: NSQ order PDFs, and the result documents of tenders (not NITs, bid documents or plain corrigenda)."""
    links = {}
    for r_id, d in rows:
        for u in d.get("orders", []):
            links.setdefault(u, []).append(r_id)
        for f in d.get("files", []):
            if f["kind"] in STORED_KINDS and f["url"].startswith(SITE):
                links.setdefault(f["url"], []).append(r_id)
    return links


# ---- rate lists ("approved items list for L1 and matched L1 bidders") ---------------------------------------------------------

_ANCHOR = re.compile(r"^\s{0,10}\d{1,4}\.?\s{2,}\S")
_HEAD = {"code", "life", "without", "taxes", "value", "value with", "amount", "without tax", "tax rs.", "tax rs", "rs.", "rs",
         "tax", "s. no.", "firm name", "item", "item description", "shelf", "rate", "gst%", "rate with tax", "tender qty.",
         "offered qty.", "contarct", "contract", "pbg", "rc type", "with tax", "contract value"}
_FOOT = re.compile(r"Page \d+ of \d+|Managing Director|^\s*UPMSCL\s*$|^\s*\(.*Director.*\)\s*$", re.I)
_NUMS = (r"(?:(?P<shelf>\d{1,3})\s+)?(?P<rate>\d[\d,]*\.\d+)\s+(?P<gst>\d{1,2}(?:\.\d+)?)\s+(?P<rate_tax>\d[\d,]*\.\d+)\s+"
         r"(?P<tender_qty>[\d,]+)\s+(?P<offered_qty>[\d,]+)\s+(?P<value>[\d,]+(?:\.\d+)?)\s+(?P<value_tax>[\d,]+(?:\.\d+)?)\s+"
         r"(?P<pbg>[\d,]+(?:\.\d+)?)")
_ROW = re.compile(r"^(?P<sl>\d{1,4})\.?\s+(?P<firm>.+?)\s+(?P<code>[A-Z]{1,2}\d{5,7})\s+(?P<desc>.+?)\s+" + _NUMS + r"\s*$")


def _break(line):
    return bool(_FOOT.search(line)) or all(t.lower() in _HEAD for _, t in P.chunks(line))


def parse_rate_list(pages, title=""):
    """Rows of a rate list: firm, item code, item, rates, quantities, contract value, PBG, RC type (Main / Parallel and its share).
    Rows that do not fit the columns are kept with parsed False and their text."""
    out = []
    validity = re.search(r"RC validity is from\s+(\d{1,2}\.\d{1,2}\.\d{4})\s+to\s+(\d{1,2}\.\d{1,2}\.\d{4})", " ".join(pages[:1]))
    tender = re.search(r"UPMSCL\s*/\s*Drugs?\s*-\s*\d+\s*/\s*\d+", title, re.I)
    for cells in P.rows(pages, _ANCHOR.match, "below", _break):
        s = P.joined(cells)
        rc_kind = re.search(r"\b(Main|Parallel)\b", s)
        words = re.sub(r"\b(?:Main|Parallel)\b|\bRC\b", " ", s)
        words = re.sub(r"\s+", " ", words).strip()
        rc_share = re.search(r"RC\s*(\d{1,3}(?:\.\d+)?)\s*%", s) or re.search(r"\b(\d{1,3}(?:\.\d+)?)\s*%\s*$", words)
        core = re.sub(r"\b\d{1,3}(?:\.\d+)?\s*%\s*$", " ", re.sub(r"RC\s*\d{1,3}(?:\.\d+)?\s*%", " ", words))
        core = re.sub(r"\s+", " ", core).strip()
        m = _ROW.match(core)
        sl = re.match(r"^(\d{1,4})", s)
        d = {"kind": "rate-list", "sl": int(sl.group(1)) if sl else None, "text": s, "parsed": bool(m),
             "tender": re.sub(r"\s+", "", tender.group(0)) if tender else None,
             "rc_from": H.iso_date(validity.group(1)) if validity else None, "rc_to": H.iso_date(validity.group(2)) if validity else None,
             "rc_type": rc_kind.group(1) if rc_kind else None,
             "rc_share_pct": float(next(g for g in rc_share.groups() if g)) if rc_share else None}
        if m:
            g = m.groupdict()
            desc, shelf = g["desc"], g["shelf"]
            if shelf is None:                        # the shelf life column fell inside the wrapped description
                sm = list(re.finditer(r"(?<![\d.:/+-])\b(6|12|18|24|30|36|48|60)\b(?![\d.%/])(?!\s*(?:mg|ml|gm|g|mcg|iu|%))", desc,
                                      re.I))
                if sm:
                    shelf = sm[-1].group(1)
                    desc = (desc[:sm[-1].start()] + desc[sm[-1].end():]).strip()
            d.update(firm=g["firm"], code=g["code"], item=re.sub(r"\s+", " ", desc),
                     shelf_life_months=int(shelf) if shelf else None, rate=H.num(g["rate"]),
                     gst_pct=H.num(g["gst"]), rate_with_tax=H.num(g["rate_tax"]), tender_qty=H.num(g["tender_qty"]),
                     offered_qty=H.num(g["offered_qty"]), contract_value=H.num(g["value"]),
                     contract_value_with_tax=H.num(g["value_tax"]), pbg=H.num(g["pbg"]))
            key = H.rid("rate-list", d["tender"], g["code"], g["firm"], d["rc_type"])
        else:
            key = H.rid("rate-list", d["tender"], s)
        out.append((key, d))
    return out


def parse_doc(url, data, txt, link_rows):
    """Records from a rate list PDF with a text layer; [] for other documents (they are only stored)."""
    files = [f for r in link_rows for f in r.get("files", []) if f.get("url") == url]
    if not files or files[0]["kind"] != "rate-list" or not data.startswith(b"%PDF"):
        return []
    rows = parse_rate_list(P.layout_pages(data), files[0]["title"])
    return [(k, {**d, "document_title": files[0]["title"]}) for k, d in rows]
