"""Madhya Pradesh Public Health Services Corporation Ltd. (mpphscl.mp.gov.in): pure parsing helpers, no network. Tested on saved
pages.

The site is ASP.NET (IIS). Each list is ONE page with every row, so there is no pagination:
  - TenderALL.aspx: ~1,190 tenders since 2014 (11.5 MB, 2.7 MB of it VIEWSTATE) and ~13,300 linked documents under /Files/PDF/.
    Each tender row has its tender document and a "Corrigendum" cell with every later document: pre-bid answers, technical bid
    opening details, evaluation sheets, comparative statements (bidder, rate, rank), approved rate lists, final status.
    drug.aspx, equipment.aspx and the other category pages are subsets of TenderALL.aspx (same links), so they are not fetched.
  - BlackListFirm.aspx, BlackListProduct.aspx, BlackListLabs.aspx: the corporation's debarments (firm, product, laboratory), with
    the order copy and corrigenda (court stays). Source D04.
The server needs the legacy TLS renegotiation option (OpenSSL 3 refuses it by default): see mpphscl_task.session().
"""
import hashlib
import html
import re
from datetime import datetime
from urllib.parse import quote

SITE = "https://mpphscl.mp.gov.in"
TENDERS = "TenderALL.aspx"
BLACKLISTS = {"firm": "BlackListFirm.aspx", "product": "BlackListProduct.aspx", "lab": "BlackListLabs.aspx"}
PAGES = [TENDERS, *BLACKLISTS.values()]

_TBODY = re.compile(r"<table[^>]*id=\"(tblTender|tblBlackList)\"[^>]*>.*?<tbody>(.*?)</tbody>", re.S | re.I)
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_A = re.compile(r"<a[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
GEPNIC_ID = re.compile(r"\b(20\d\d_PHSCL_\d+_\d+)\b")


def text(s):
    return _WS.sub(" ", html.unescape(_TAGS.sub(" ", s))).strip().strip(",").strip()


def iso_date(s):
    """'16-Oct-2026' -> '2026-10-16'; None for anything else."""
    try:
        return datetime.strptime(s.strip(), "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def doc_url(href):
    """'/Files/PDF/63928_T-963 Prebid.pdf' -> absolute URL with the spaces escaped. External links stay as they are."""
    href = html.unescape(href.strip())
    if re.match(r"https?://", href, re.I):
        return href
    return SITE + "/" + quote(href.lstrip("/"), safe="/%()-_.~,'")


def file_of(url):
    return url.rsplit("/", 1)[-1]


def doc_kind(label):
    """A short class for a document label, so analysis finds the rate and bidder documents without reading all 13,000."""
    t = label.lower()
    for kind, pat in (("comparative", r"comparative"), ("rate_list", r"rate\s*list|approved\s*rate|rates?\b|price"),
                      ("approved_items", r"approved\s*item"), ("final_status", r"final\s*status"),
                      ("financial_opening", r"financial"), ("technical_opening", r"technical\s*bid\s*opening|tbo\b"),
                      ("evaluation", r"evaluat|responsive|tce\b|techno"), ("prebid", r"pre[\s-]*bid|quer"),
                      ("corrigendum", r"corr?i[ge]+ndum|amend|addend"), ("minutes", r"minute"), ("items", r"item\s*list"),
                      ("court", r"court|stay|\bwp[-\s]?\d"), ("cancellation", r"cancel"), ("make_model", r"make\s*(&|and)\s*model"),
                      ("shortfall", r"shortfall"), ("specification", r"annex|annxure|specification")):
        if re.search(pat, t):
            return kind
    return "other"


def _tbody(page):
    m = _TBODY.search(page)
    return m.group(2) if m else ""


def _links(cell):
    return [{"label": text(t) or "document", "url": doc_url(h)} for h, t in _A.findall(cell) if not h.lower().startswith(("#", "javascript"))]


def row_hash(*parts):
    return hashlib.sha1("|".join(_WS.sub(" ", p or "").strip().lower() for p in parts).encode()).hexdigest()[:16]


def parse_tenders(page):
    """[(record id, data)] for each tender row of TenderALL.aspx. Id: 'tender:<number>:<hash of number, start date, text>'
    (old tenders reuse numbers like NIT-001, so the number alone is not unique)."""
    out = []
    for pos, tr in enumerate(_ROW.findall(_tbody(page)), 1):
        tds = _TD.findall(tr)
        if len(tds) < 9:
            continue
        sr, number, desc, cat, typ, start, close = (text(c) for c in tds[:7])
        docs = [dict(d, kind="tender_document") for d in _links(tds[7])]
        docs += [dict(d, kind=doc_kind(d["label"])) for d in _links(tds[8])]
        slug = re.sub(r"[^A-Za-z0-9-]+", "_", number).strip("_")[:40] or "x"
        rid = f"tender:{slug}:{row_hash(number, start, desc)}"
        out.append((rid, {"kind": "tender", "position": pos, "sr": sr, "number": number, "title": desc, "category": cat,
                          "type": typ, "start_raw": start, "start": iso_date(start), "close_raw": close, "close": iso_date(close),
                          "documents": docs, "n_documents": len(docs),
                          "doc_kinds": sorted({d["kind"] for d in docs})}))
    return out


def parse_blacklist(page, which):
    """[(record id, data)] for each row of a blacklist page (which: firm, product, lab). Firm names and addresses are as the site
    gives them; no contact columns exist on these pages."""
    out = []
    for pos, tr in enumerate(_ROW.findall(_tbody(page)), 1):
        tds = _TD.findall(tr)
        if which == "product":
            if len(tds) < 11:
                continue
            sr, cat, product, company, frm, upto, order, reason, remark = (text(c) for c in tds[:9])
            doc_cell, corr_cell = tds[9], tds[10]
        else:
            if len(tds) < 10:
                continue
            sr, cat, company, frm, upto, order, reason, remark = (text(c) for c in tds[:8])
            product = ""
            doc_cell, corr_cell = tds[8], tds[9]
        orders = [dict(d, kind="order") for d in _links(doc_cell)]
        corr = [dict(d, kind=doc_kind(d["label"])) for d in _links(corr_cell)]
        code = re.search(r"\[(\w+)\]\s*$", product)
        # same firm, order and date can appear twice with different order copies or end dates: they are separate rows
        rid = f"blacklist-{which}:{row_hash(which, company, product, order, frm, upto, *(d['url'] for d in orders))}"
        stayed = any(re.search(r"\bstay|stayed|quash|set aside|revok|withdraw", d["label"], re.I) for d in corr)
        out.append((rid, {"kind": "blacklist", "list": which, "position": pos, "sr": sr, "category": cat, "company": company,
                          "product": product or None, "item_code": code.group(1) if code else None,
                          "from_raw": frm, "from": iso_date(frm), "upto_raw": upto, "upto": iso_date(upto), "order_no": order,
                          "reason": reason, "remark": remark,
                          "quality_failure": bool(re.search(r"quality|nsq|not of standard|substandard|spurious", f"{reason} {remark}", re.I)),
                          "non_supply": bool(re.search(r"non[\s-]*supply|not supplied|failure to supply", f"{reason} {remark}", re.I)),
                          "court_stay": stayed, "documents": orders + corr}))
    return out


def doc_urls(rows):
    """{url: [{"id": record id, "label": ..., "kind": ...}]} over the documents of parsed rows (one URL may serve several rows)."""
    out = {}
    for rid, d in rows:
        for doc in d.get("documents", []):
            out.setdefault(doc["url"], []).append({"id": rid, "label": doc["label"], "kind": doc["kind"]})
    return out


def shard_of(key, shards):
    return int(hashlib.sha1(key.encode()).hexdigest(), 16) % shards


def gepnic_ids(txt):
    """GePNIC tender ids (mptenders.gov.in) found in a document's text, e.g. 2026_PHSCL_543877_1."""
    return sorted(set(GEPNIC_ID.findall(txt or "")))
