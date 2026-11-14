"""Pure parsing of rmsc.health.rajasthan.gov.in (Rajasthan Medical Services Corporation Ltd.): no network, tested on saved pages.

Pages (checked 2026-11-14; an Adobe AEM site, each list is one HTML page, no pagination):
  drugrc            Approved-Rate-Lists/DrugsRC.html: approved rate contracts (drug, code, tender no, supplier, unit, rate, GST,
                    level L1/L2.., contract from/to). The SUPPLIER CONTACT column holds names, phones and e-mails of
                    persons: it is NOT stored (personal data).
  banned-company    library/Banned-firms0/Banned_Company.html: debarred firms (product, reason, up to, order PDFs).
  banned-product    library/Banned-firms0/Banned_Product.html: banned products of a firm (reason such as NOSQ, up to, order PDFs).
  drug-tenders, equipment-tenders, finance-tenders
                    Tenders/<kind>.html: notices, corrigenda, bidder lists (responsive / non-responsive) with their PDFs.
RMSC does not publish a batch-level NSQ list; NSQ results show as the reason "NOSQ" in the two ban lists.
"""
import re
from urllib.parse import quote, urljoin

import htmltables as H

SITE = "https://rmsc.health.rajasthan.gov.in"
BASE = f"{SITE}/content/raj/medical/rajasthan-medical-services-corporation-ltd-/en"
_PATHS = {
    "drugrc": "Approved-Rate-Lists/DrugsRC.html",
    "banned-company": "library/Banned-firms0/Banned_Company.html",
    "banned-product": "library/Banned-firms0/Banned_Product.html",
    "drug-tenders": "Tenders/Drug-Tenders.html",
    "equipment-tenders": "Tenders/Equipment-Instrument-Tenders.html",
    "finance-tenders": "Tenders/Finance-Tenders.html",
}


def url_of(page):
    return f"{BASE}/{_PATHS[page]}"


def _abs(href, page):
    if not href or href.startswith(("javascript:", "#", "mailto:")):
        return None
    return quote(urljoin(url_of(page), href.strip()), safe=":/?&=%#()+,;~@!$*'")


def _table(html, first):
    for t in H.tables(html):
        h = [x.upper() for x in t.header()]
        if h and first in h[:3]:
            return t
    return None


def is_nsq(reason):
    r = (reason or "").upper()
    return bool(re.search(r"\bN\.?O?\.?S\.?Q\b|NOT OF STANDARD|SUB-?STANDARD", r))


def parse_drugrc(html):
    """Approved rate contracts: one record per row, without the supplier contact column."""
    t = _table(html, "DRUG NAME")
    out = []
    if not t:
        return out
    head = [x.upper() for x in t.header()]
    col = {name: head.index(name) for name in head if name}
    seen = {}
    for row in t.data_rows():
        c = [x.text for x in row]
        if len(c) < 11:
            continue
        g = lambda k: c[col[k]] if k in col and col[k] < len(c) else ""          # noqa: E731
        d = {"kind": "drugrc", "drug": g("DRUG NAME"), "code": g("CODE"), "tender_no": g("TENDER NO"), "supplier": g("SUPPLIER"),
             "unit": g("UNIT"), "rate": H.num(g("RATE")), "rate_raw": g("RATE"), "gst_pct": H.num(g("GST RATE")),
             "level": g("LEVEL") or None, "contract_from": H.iso_date(g("CONTRACT FROM DATE")),
             "contract_to": H.iso_date(g("CONTRACT TO DATE")), "source": url_of("drugrc")}
        key = H.rid("drugrc", d["code"], d["tender_no"], d["supplier"], d["level"], g("CONTRACT FROM DATE"))
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:                        # the same row twice on the page: keep both, as rows
            key = f"{key}-{seen[key]}"
        out.append((key, d))
    return out


def _links(cell, page):
    return [{"url": _abs(h, page), "text": txt} for h, txt in cell.links if _abs(h, page)]


def parse_bans(html, page):
    """Banned / debarred firms or products: one record per row, with the order PDFs as links."""
    t = _table(html, "NAME OF FIRM / COMPANY" if page == "banned-company" else "COMPANY NAME")
    out = []
    for i, row in enumerate(t.data_rows() if t else [], 1):
        c = [x.text for x in row]
        if page == "banned-company" and len(c) >= 7:
            firm, product, action, reason, upto, orders = c[1], c[2], c[3], c[4], c[5], _links(row[6], page)
        elif page == "banned-product" and len(c) >= 6:
            firm, product, action, reason, upto, orders = c[1], c[2], None, c[3], c[4], _links(row[5], page)
        else:
            continue
        if not firm:
            continue
        out.append((H.rid(page, firm, product, upto, c[-1]), {
            "kind": "ban", "list": page, "position": i, "firm": firm, "product": product or None,
            "product_codes": product_codes(product),
            "action": action, "reason": reason, "nsq": is_nsq(reason), "upto": H.iso_date(upto), "upto_raw": upto,
            "orders": orders, "order_refs": c[-1], "source": url_of(page)}))
    return out


def product_codes(text):
    """RMSC drug codes in a product cell: '[NRD-482]', '[622]', or a leading '103 (' / 'NRD-71 ('."""
    codes = re.findall(r"\[([A-Z]{0,4}-?\d+)\]", text or "")
    codes += re.findall(r"(?:^|\s|,)((?:[A-Z]{1,4}-)?\d{1,4})\s*\(", text or "")
    return list(dict.fromkeys(codes))


def parse_tenders(html, page):
    """Tender notices: one record per row (name, from, to, description, files, upload date)."""
    t = _table(html, "NAME")
    out = []
    seen = {}
    for i, row in enumerate(t.data_rows() if t else [], 1):
        c = [x.text for x in row]
        if len(c) < 6:
            continue
        files = _links(row[4], page)
        detail = _links(row[0], page)
        d = {"kind": "tender", "list": page, "position": i, "name": c[0], "detail_url": detail[0]["url"] if detail else None,
             "from": H.iso_date(c[1]), "to": H.iso_date(c[2]), "from_raw": c[1] or None, "to_raw": c[2] or None,
             "description": c[3], "files": files, "uploaded": H.iso_date(c[5]), "uploaded_raw": c[5] or None,
             "nib": nib_of(" ".join([c[0], c[3]] + [f["text"] for f in files])), "source": url_of(page)}
        key = H.rid(page, c[0], c[5], *[f["url"] for f in files])
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            key = f"{key}-{seen[key]}"
        out.append((key, d))
    return out


_NIB = re.compile(r"\bNIB[\s_-]*(?:No\.?\s*)?(\d{1,4})\b", re.I)


def nib_of(text):
    m = _NIB.search(text or "")
    return f"NIB-{int(m.group(1))}" if m else None


PAGES = [(p, None) for p in _PATHS]
DOC_GROUPS = {"bans": [("banned-company", None), ("banned-product", None)], "drug-tenders": [("drug-tenders", None)],
              "equipment-tenders": [("equipment-tenders", None)], "finance-tenders": [("finance-tenders", None)]}


def page_url(page, arg=None):
    return url_of(page)


def parse(page, html, arg=None):
    if page == "drugrc":
        return parse_drugrc(html)
    if page in ("banned-company", "banned-product"):
        return parse_bans(html, page)
    return parse_tenders(html, page)


def doc_urls(rows):
    """{document url: [record ids]} for files on rmsc.health.rajasthan.gov.in linked from ban and tender rows."""
    links = {}
    for r_id, d in rows:
        for f in d.get("orders", []) + d.get("files", []):
            u = f["url"]
            if u and u.startswith(SITE) and "/content/dam/" in u:
                links.setdefault(u, []).append(r_id)
    return links
