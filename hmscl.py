"""Pure parsing of hmscl.org.in (Haryana Medical Services Corporation Ltd.): no network here, tested on saved pages.

Pages (checked 2026-11-14; an ASP.NET site, robots.txt allows all; use the bare host, www.hmscl.org.in has a bad certificate):
  drugrc       Page.aspx?slug=drugs-surgical-sutures&export=excel: all active drug rate contracts in one HTML table (the "Export
               to Excel" link; the normal page shows 25 rows per page and ignores pageSize). Columns: drug code, drug name (EDL),
               drug name (RC), RC number, RC rate (excl. GST), vendor, valid from, valid till.
  equipmentrc  Page.aspx?slug=equipment-instruments&export=excel: equipment rate contracts (item, RC number, rate, vendor, dates).
  banned       Page.aspx?slug=banned-firms: blacklisted / debarred firms (firm, category, period, order number, reason, order
               PDF at /BlacklistAsset.ashx?key=<id>.pdf).
HMSCL does not publish a batch-level NSQ list; NSQ shows as the reason "Not of Standard Quality" / "Quality Failure" on the ban
list. Tenders and awards run on etenders.hry.nic.in (hub project gepnic-etenders-hry).
"""
import re
from urllib.parse import urljoin

import htmltables as H

SITE = "https://hmscl.org.in"
_PATHS = {
    "drugrc": "Page.aspx?slug=drugs-surgical-sutures&export=excel",
    "equipmentrc": "Page.aspx?slug=equipment-instruments&export=excel",
    "banned": "Page.aspx?slug=banned-firms",
}


def url_of(page):
    return f"{SITE}/{_PATHS[page]}"


def page_url(page, arg=None):
    return url_of(page)


def is_nsq(reason):
    r = (reason or "").upper()
    return bool(re.search(r"NOT OF STANDARD|QUALITY FAIL|\bN\.?S\.?Q\b|SUB-?STANDARD", r))


def _date(s):
    """'19 May 2025' -> '2025-05-19'."""
    s = H.clean(s)
    m = re.search(r"\d{1,2} [A-Za-z]{3,9} \d{4}", s)
    if m:
        from datetime import datetime
        for f in ("%d %b %Y", "%d %B %Y"):
            try:
                return datetime.strptime(m.group(0), f).date().isoformat()
            except ValueError:
                pass
    return H.iso_date(s)


def _table(html, header_word):
    for t in H.tables(html):
        if any(header_word in h.upper() for h in t.header()):
            return t
    return None


def _cols(t):
    return {h.upper(): i for i, h in enumerate(t.header())}


def parse_rc(html, page):
    """Rate contracts: one record per row."""
    t = _table(html, "VENDOR")
    out, seen = [], {}
    if not t:
        return out
    col = _cols(t)

    def g(c, *names):
        for n in names:
            for k, i in col.items():
                if k.startswith(n) and i < len(c):
                    return c[i]
        return ""

    for row in t.data_rows():
        c = [x.text for x in row]
        if page == "drugrc":
            d = {"kind": "rc", "list": "drug", "code": g(c, "DRUG CODE") or None, "item": g(c, "DRUG NAME (EDL)"),
                 "item_rc": g(c, "DRUG NAME (RC)") or None}
        else:
            d = {"kind": "rc", "list": "equipment", "code": None, "item": g(c, "EQUIPMENT"), "item_rc": None}
        rate_raw = g(c, "RC RATE")
        d.update({"rc_number": g(c, "RC NUMBER") or None, "rate": H.num(rate_raw), "rate_raw": rate_raw, "gst_included": False,
                  "vendor": g(c, "VENDOR"), "valid_from": _date(g(c, "VALID FROM")), "valid_to": _date(g(c, "VALID TILL")),
                  "source": url_of(page)})
        if not d["item"] or not d["vendor"]:
            continue
        key = H.rid(f"{page}", d["code"], d["item"], d["rc_number"], d["vendor"], g(c, "VALID FROM"))
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            key = f"{key}-{seen[key]}"
        out.append((key, d))
    return out


def parse_banned(html):
    """Banned / debarred firms: one record per row, with the order PDF."""
    t = _table(html, "REASON")
    out = []
    for i, row in enumerate(t.data_rows() if t else [], 1):
        if len(row) < 5:
            continue
        parts = [H.clean(p) for p in row[1].parts if H.clean(p)]
        firm = re.sub(r"^M/s\.?\s*", "", parts[0], flags=re.I) if parts else ""
        tail = parts[-1] if len(parts) > 1 else ""
        category, _, status = tail.partition("·")
        address = (" ".join(parts[1:-1]) or None) if len(parts) > 2 else None
        period = row[2].text
        m = re.match(r"(.+?)\s+to\s+(.+)", period)
        order_parts = [H.clean(p) for p in row[3].parts if H.clean(p) and H.clean(p) != "—"]
        orders = [{"url": urljoin(SITE + "/", h), "text": txt} for h, txt in (row[5].links if len(row) > 5 else [])
                  if h and "BlacklistAsset" in h]
        reason = row[4].text
        if not firm:
            continue
        out.append((H.rid("banned", firm, period, " ".join(order_parts)), {
            "kind": "ban", "list": "banned", "position": i, "firm": firm, "firm_raw": parts[0] if parts else None,
            "address": address, "category": category.strip() or None, "status": status.strip() or None,
            "from": _date(m.group(1)) if m else None, "to": _date(m.group(2)) if m else None, "period_raw": period,
            "order_number": " ".join(order_parts) or None, "reason": reason, "nsq": is_nsq(reason), "orders": orders,
            "source": url_of("banned")}))
    return out


PAGES = [(p, None) for p in _PATHS]
DOC_GROUPS = {"orders": [("banned", None)]}


def parse(page, html, arg=None):
    if page == "banned":
        return parse_banned(html)
    return parse_rc(html, page)


def doc_urls(rows):
    links = {}
    for r_id, d in rows:
        for f in d.get("orders", []):
            if f["url"].startswith(SITE):
                links.setdefault(f["url"], []).append(r_id)
    return links
