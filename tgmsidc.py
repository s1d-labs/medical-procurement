"""Pure parsing of tgmsidc.telangana.gov.in (Telangana Medical Services & Infrastructure Development Corporation): no network.

Pages (checked 2026-11-14):
  drugs-wing     /drugs-wing/: one HTML table of 7 documents (PDF names are hashes and change with each update):
                 rate contracts of medicines (~522 items) and surgical items (~448 items), blacklisted firms and blacklisted
                 products (2017-18 onwards), approved lists of drugs and surgical items, list of central medicine stores.
The rate contract and blacklist PDFs have a text layer; parse_doc() turns them into one record per row.
TGMSIDC has no batch-level NSQ list: the product blacklist (item, firm, dates, remarks) is the NSQ source.
"""
import re
from datetime import datetime
from urllib.parse import urljoin

import htmltables as H
import pdftables as P

SITE = "https://tgmsidc.telangana.gov.in"
_PATHS = {"drugs-wing": "/drugs-wing/"}
PAGES = [("drugs-wing", None)]
DOC_GROUPS = {"lists": [("drugs-wing", None)]}

# document kinds by their title on the drugs-wing page
_KINDS = [("rc-medicines", r"rate contract.*medicine"), ("rc-surgical", r"rate contract.*surgical"),
          ("blacklist-firms", r"blacklisted firms"), ("blacklist-products", r"blacklisted products"),
          ("approved-drugs", r"approved list of drugs"), ("approved-surgical", r"approved list of surgical"),
          ("cms-list", r"central medicine stores")]
_DATE = r"\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{4}"


def page_url(page, arg=None):
    return SITE + _PATHS[page]


def doc_kind(title):
    t = (title or "").lower()
    return next((k for k, rx in _KINDS if re.search(rx, t)), "other")


def _abs(href):
    if not href:
        return None
    u = urljoin(SITE + "/", href.strip())
    return re.sub(r"(?<!:)//+", "/", u)


def parse_list(html):
    """The documents of the drugs-wing page: one record per row (title, kind, url)."""
    out = []
    for t in H.tables(html):
        if "title" not in [x.lower() for x in t.header()]:
            continue
        for row in t.data_rows():
            c = [x.text for x in row]
            links = [_abs(h) for cell in row for h, _ in cell.links if _abs(h)]
            if len(c) < 2 or not links:
                continue
            title = c[1]
            out.append((H.rid("drugs-wing", title), {"kind": "document", "title": title, "doc_kind": doc_kind(title),
                                                      "url": links[0], "position": H.num(c[0]), "source": page_url("drugs-wing")}))
    return out


def parse(page, html, arg=None):
    return parse_list(html)


def doc_urls(rows):
    links = {}
    for r_id, d in rows:
        u = d.get("url")
        if u and u.startswith(SITE):
            links.setdefault(u, []).append(r_id)
    return links


# ---- documents ---------------------------------------------------------------------------------------------------------------

def _clean(s, npages):
    s = re.sub(rf"\b\d{{1,3}}/{npages}\b", " ", s)            # page numbers such as "14/14" in the footer
    return re.sub(r"\s+", " ", s).strip()


_RC_ANCHOR = re.compile(r"^\s{0,10}\d{1,4}\s{2,}\d+(?:\.\d+)?\s{2,}\S")
_RC_HEAD = {"sl no", "s.no", "sl", "no", "drug_code", "drug_name", "category", "rate", "unit", "firm name", "tno", "validity", "item",
            "code", "item name", "group", "s.no.", "item code"}


def _rc_break(line):
    return all(t.lower() in _RC_HEAD for _, t in P.chunks(line))


_TAIL = (r"\s+(?P<rate>\d[\d,]*(?:\.\d+)?)\s+(?P<unit>\S+)\s+(?:\d{1,3}/\d{1,3}\s+)?(?P<firm>.+?)\s+(?:T\.?\s*No\.?\s*)?(?P<tno>\d{1,3}_\d{4})\s+"
         r"(?P<valid>\d{1,2}-[A-Za-z]{3}-\d{2,4})$")
# medicines: category EML / AML (the name itself can hold "IP 100 mg"); surgical items: the last group code before the rate
_RC_FULL = {"rc-medicines": re.compile(r"^(?P<name>.+?)\s+(?P<cat>EML|AML)" + _TAIL),
            "rc-surgical": re.compile(r"^(?P<name>.+)\s+(?P<cat>[A-Z]{2,4})" + _TAIL)}
_RC_NONE = {"rc-medicines": re.compile(r"^(?P<name>.+?)\s+(?P<cat>EML|AML)(?:\s+(?P<unit>\S+))?$"),
            "rc-surgical": re.compile(r"^(?P<name>.+)\s+(?P<cat>[A-Z]{2,4})(?:\s+(?P<unit>\S+))?$")}


def _dmy(s):
    """'18-Sep-26' or '18-Sep-2026' -> '2026-09-18'."""
    for fmt in ("%d-%b-%y", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except (TypeError, ValueError):
            pass
    return None


def parse_rc(pages, kind):
    """Rate contract PDF (medicines or surgical items): one record per item; items without a rate have rate None."""
    out = []
    n = len(pages)
    for cells in P.rows(pages, _RC_ANCHOR.match, "below", _rc_break):
        s = _clean(P.joined(cells), n)
        m = re.match(r"^(?P<sl>\d{1,4})\s+(?P<code>\d+(?:\.\d+)?)\s+(?P<rest>.+)$", s)
        if not m:
            continue
        rest = m.group("rest")
        f = _RC_FULL[kind].match(rest)
        d = {"kind": kind, "sl": int(m.group("sl")), "code": m.group("code"), "text": s}
        if f:
            d.update(name=f.group("name"), category=f.group("cat"), rate=H.num(f.group("rate")), unit=f.group("unit"),
                     firm=f.group("firm"), tender_no=f.group("tno"), valid_to=_dmy(f.group("valid")), valid_to_raw=f.group("valid"),
                     contracted=True)
        else:
            e = _RC_NONE[kind].match(rest)
            d.update(name=e.group("name") if e else rest, category=e.group("cat") if e else None,
                     unit=e.group("unit") if e else None, rate=None, firm=None, tender_no=None, valid_to=None, contracted=False)
        key = H.rid(kind, d["code"], d.get("firm"), d.get("tender_no"), d["sl"])
        out.append((key, d))
    return out


def _two_dates(line):
    return len(re.findall(_DATE, line)) >= 2


_BL_BREAK = re.compile(r"Statement Showing|^\s*S\s*No\b|Name Of The|TELANGANA MEDICAL|DEVELOPMENT CORPORATION|ENTERPRISE OF GOVERNMENT|"
                       r"Floor|ISO 9001|Hyderabad\s*[-–]|^\s*(Date|Till Dt\.?|Period|Remarks)(\s+\S+){0,3}\s*$", re.I)
_YEAR = re.compile(r"Blacklisted in (?:the Year )?(\d{4}-\d{2})", re.I)


def _date(s):
    return H.iso_date(re.sub(r"\s+", "", s).replace("-", ".", 2).replace("/", ".")) if s else None


def parse_blacklist(pages, kind):
    """Blacklisted firms or products: one record per row with dates, period and remarks (court orders are often in remarks)."""
    out = []
    rows = P.rows(pages, _two_dates, "nearest", lambda ln: bool(_BL_BREAK.search(ln)))
    for cells in rows:
        s = re.sub(r"\b(?:till\s+)?Date\b", " ", P.joined(cells), flags=re.I)
        s = re.sub(r"\s+", " ", s).strip()
        dates = list(re.finditer(_DATE, s))
        if len(dates) < 2:
            continue
        head, tail = s[:dates[0].start()].strip(), s[dates[1].end():].strip()
        m = re.match(r"^(?P<sl>\d{1,3})\s+(?P<body>.+)$", head)
        sl, body = (int(m.group("sl")), m.group("body")) if m else (None, head)
        pm = re.match(r"^(?P<period>\d+\s*(?:years?|months?))\s*(?P<rest>.*)$", tail, re.I)
        period, remarks = (pm.group("period"), pm.group("rest")) if pm else (None, tail)
        if kind == "blacklist-products":
            fm = re.search(r"\bM\s*/\s*s\.?\s", body)
            item, firm_raw = (body[:fm.start()].strip(), body[fm.start():].strip()) if fm else (body, "")
        else:
            item, firm_raw = None, body
        firm_raw = re.sub(r"^(?:Firm|Name)\s+", "", firm_raw).strip()
        remarks = re.sub(r"^(?:Period\s+\d+\s*years?\s*-?\s*|Remarks\s*)", "", remarks or "", flags=re.I).strip()
        if not period:
            pm2 = re.search(r"\b(\d+\s*years?)\b", tail, re.I)
            period = pm2.group(1) if pm2 else None
        firm = re.split(r",", firm_raw, 1)[0].strip()
        d = {"kind": kind, "sl": sl, "item": item or None, "item_codes": re.findall(r"\[(\d+(?:\.\d+)?)\]", item or ""),
             "firm": firm, "firm_raw": firm_raw, "from": _date(dates[0].group(0)), "till": _date(dates[1].group(0)),
             "from_raw": dates[0].group(0), "till_raw": dates[1].group(0), "period": period, "remarks": remarks or None,
             "court_order": bool(re.search(r"high court|W\.?P\.?\s*No|stay|set aside", remarks or "", re.I)),
             "nsq": bool(re.search(r"\bN\.?S\.?Q\b|not of standard|sub-?standard", (remarks or "") + " " + (item or ""), re.I)),
             "text": s}
        out.append((H.rid(kind, firm, item, d["from_raw"], d["till_raw"]), d))
    return out


def parse_doc(url, data, link_rows):
    """Records from a linked document (bytes), by the kind of the row that links it. [] for kinds that are only stored."""
    kind = next((r.get("doc_kind") for r in link_rows if r.get("doc_kind")), "other")
    if kind not in ("rc-medicines", "rc-surgical", "blacklist-firms", "blacklist-products") or not data.startswith(b"%PDF"):
        return []
    pages = P.layout_pages(data)
    if kind.startswith("rc-"):
        return parse_rc(pages, kind)
    return parse_blacklist(pages, kind)
