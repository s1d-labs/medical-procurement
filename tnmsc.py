"""Pure parsing of tnmsc.tn.gov.in (Tamil Nadu Medical Services Corporation Ltd.): no network here, tested on saved pages.

Pages (checked 2026-11-14; no pagination, each list is one HTML page):
  blacklist      blacklisted/blacklisted.php: four tables (drug items, drug firms, laboratories, equipment firms); the drug item
                 list holds the NSQ (not of standard quality) blacklistings. TNMSC does not publish a batch-level NSQ list.
  awards         html/tenders.php?action=5&cayear=<year>: contracts awarded (ref no, dates, title, CA<n>.pdf). Years in the form:
                 2014, 2015, 2020-2024. The bidders and prices are in the PDFs.
  notifications  html/tenders.php?action=4&page=1&dt=<year>: tender notifications (NF<n>.pdf). dt=2024 gives 2023-24; on
                 2026-11-14 dt=2025 and dt=2026 gave the 2026-27 list (a fault of the site), so those years are not reachable.
  drugrc         user_pages/drugtender.php?drugcat=<tender>: drug rate contracts, one row per drug (L1 rate, counts) with a nested
                 table of tenderers (firm, tax, L1 or matched, rate, order share).
  equipmentrc    html/ajax4service_tamil.php?action=11&page=1&group=<group>: equipment rate contracts (make, model, rate, valid
                 up to); "Break-up price" rows belong to the item above them.
"""
import re
from urllib.parse import quote, urljoin

import htmltables as H

SITE = "https://tnmsc.tn.gov.in"
AWARD_YEARS = [2024, 2023, 2022, 2021, 2020, 2015, 2014]
NOTIFICATION_YEARS = [2024, 2025, 2026, 2027]
# drugcat values linked from html/Procurement & Tender.php on 2026-11-14 (edl2024, T19062 and t18036 answer "Invalid URL")
DRUG_TENDERS = ["edl2023", "t18033", "t20075", "t20076", "t21083", "t22005", "t22027", "t22057", "t23017", "t23018",
                "t24010", "t25001", "t25031", "t25048", "qct19050"]
EQUIPMENT_GROUPS = ["EQUIPMENT", "FURNITURE", "LINEN", "REAGENTS/KITS/CONSUMABLES"]

BLACKLISTS = {"Blacklisted Item (Drug)": "drug-item", "Blacklisted Firm (Drug)": "drug-firm",
              "Blacklisted Laboratories": "laboratory", "Blacklisted Firm (Equipment)": "equipment-firm"}


def page_url(kind, arg=None):
    return url_of(kind, arg)


def url_of(kind, arg=None):
    if kind == "blacklist":
        return f"{SITE}/blacklisted/blacklisted.php"
    if kind == "awards":
        return f"{SITE}/html/tenders.php?action=5&cayear={arg}"
    if kind == "notifications":
        return f"{SITE}/html/tenders.php?action=4&page=1&dt={arg}"
    if kind == "drugrc":
        return f"{SITE}/user_pages/drugtender.php?drugcat={arg}"
    if kind == "equipmentrc":
        return f"{SITE}/html/ajax4service_tamil.php?action=11&page=1&group={quote(arg, safe='')}"
    raise ValueError(kind)


def _abs(href, base):
    return urljoin(base, href.replace(" ", "%20")) if href else None


def is_nsq(reason):
    r = (reason or "").upper()
    return "STANDARD QUALITY" in r or "SUB-STANDARD" in r or "SUBSTANDARD" in r or "NSQ" in r.split()


def parse_blacklist(html):
    """[(record id, data)] for the four blacklist tables. A full-width note row under an entry goes into that entry's `note`."""
    out = []
    parts = re.split(r'<span class="title eng"[^>]*>([^<]+)</span>', re.sub(r"<!--.*?-->", " ", html, flags=re.S))
    for title, body in zip(parts[1::2], parts[2::2]):
        lst = BLACKLISTS.get(H.clean(title))
        if not lst:
            continue
        tabs = H.tables(body)
        if not tabs:
            continue
        last = None
        for row in tabs[0].data_rows():
            cells = [c.text for c in row]
            if len(cells) == 2 and last is not None:                       # "* BL2223002 - FIRM - note" row
                last["note"] = ((last.get("note") or "") + " " + cells[1].lstrip("* ")).strip()
                continue
            if len(cells) < 9 or not cells[1]:
                continue
            firm, firm_code = H.code_in_parens(cells[2])
            product, product_code = H.code_in_parens(cells[3])
            last = {"kind": "blacklist", "list": lst, "sl": cells[0], "bl_code": cells[1], "firm": firm, "firm_code": firm_code,
                    "product": product or None, "product_code": product_code, "from": H.iso_date(cells[4]),
                    "to": H.iso_date(cells[5]), "from_raw": cells[4], "to_raw": cells[5], "reference": cells[6],
                    "reason": cells[7], "department": cells[8], "nsq": is_nsq(cells[7]), "note": None,
                    "source": url_of("blacklist")}
            out.append((f"blacklist:{lst}:{cells[1]}:{H.rid('x', firm_code or firm, product_code or product, cells[4])[2:12]}",
                        last))
    return out


def _main_table(html, first_header):
    for t in H.tables(html):
        if first_header in t.header()[:3]:
            return t
    return None


def parse_awards(html, year=None):
    """Contracts awarded: one record per row, id 'award:CA<n>' (the site's own record number)."""
    t = _main_table(html, "SNo.")
    out = []
    base = f"{SITE}/html/"
    for row in (t.data_rows() if t else []):
        c = [x.text for x in row]
        if len(c) < 8:
            continue
        link = next((h for x in row for h, _ in x.links), None)
        url = _abs(link, base)
        if url:
            url = re.sub(r"^http://(www\.)?tnmsc\.tn\.gov\.in", SITE, url)
        code = c[7] or (re.search(r"(CA\d+)\.pdf", url or "") or [None, None])[1]
        out.append((f"award:{code}" if code else H.rid("award", *c), {
            "kind": "award", "year": year, "sl": c[0], "uploaded": H.iso_date(c[1]), "ref_no": c[2], "ref_date": H.iso_date(c[3]),
            "po_date": H.iso_date(c[4]), "title": c[5], "url": url, "code": code, "source": url_of("awards", year)}))
    return out


def notifications_period(html):
    m = re.search(r"Notifications \((\d{4}) - (\d{4})\)", html)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def parse_notifications(html, year=None):
    """Tender notifications: one record per row, id 'notification:NF<n>'."""
    t = _main_table(html, "SNo.")
    period = notifications_period(html)
    out = []
    for row in (t.data_rows() if t else []):
        c = [x.text for x in row]
        if len(c) < 7:
            continue
        link = next((h for x in row for h, _ in x.links), None)
        out.append((f"notification:{c[1]}" if c[1] else H.rid("notification", *c), {
            "kind": "notification", "period": period, "sl": c[0], "code": c[1], "ref_no": c[2], "ref_date": H.iso_date(c[3]),
            "title": c[4], "published": H.iso_date(c[5]), "url": _abs(link, f"{SITE}/html/"),
            "source": url_of("notifications", year)}))
    return out


def drug_tender_info(html):
    """(title, tender ref no, tender ref date, tender code) from the heading of a drugtender.php page."""
    text = H.clean(re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)))
    m = re.search(r"Drug List -->\s*(.*?)\s*Tender Ref\. No\.\s*(.*?),\s*Dated\s*([0-9A-Za-z/.-]+)\s*\((\w+)\)", text)
    if not m:                                   # older pages: "Surgical Item - Validity from 02.03.2020 to 01.03.2021"
        m = re.search(r"Drug List -->\s*(.*?)\s*\( Click on drugcode", text)
        return (m.group(1).strip() if m else None), None, None, None
    title = re.sub(r"[஀-௿].*$", "", m.group(1)).strip()          # drop the Tamil copy of the title
    return title, m.group(2).strip(), H.iso_date(m.group(3)), m.group(4)


def parse_drug_rc(html, cat=None):
    """Drug rate contract: one 'drugrc' record per drug, and one 'drugrc-bid' record per tenderer row of that drug."""
    title, ref_no, ref_date, code = drug_tender_info(html)
    t = _main_table(html, "Drug Code")
    out = []
    for row in (t.data_rows() if t else []):
        c = [x.text for x in row]
        if len(c) < 11 or not c[1]:
            continue
        tender = c[8] or code or cat
        bids = []
        for nt in row[10].tables:
            for br in nt.data_rows():
                b = [x.text for x in br]
                if len(b) < 5 or not b[1] or b[0] == "No Records":
                    continue
                firm, firm_code = H.code_in_parens(b[1])
                bids.append({"sl": b[0], "firm": firm, "firm_code": firm_code, "tax_pct": H.num(b[2]), "l1_or_matched": b[3] or None,
                             "rate": H.num(b[4]), "order_pct": H.num(b[5]) if len(b) > 5 else None,
                             "es": (b[6] or None) if len(b) > 6 else None, "es_rate": H.num(b[7]) if len(b) > 7 else None})
        base = {"tender": tender, "tender_title": title, "tender_ref_no": ref_no, "tender_ref_date": ref_date,
                "drug_code": c[1], "drug": c[2], "unit": c[3], "source": url_of("drugrc", cat or tender)}
        out.append((f"drugrc:{tender}:{c[1]}", {"kind": "drugrc", **base, "sl": c[0], "l1_rate": H.num(c[4]), "l1_count": H.num(c[5]),
                                                "match_count": H.num(c[6]), "es_count": H.num(c[7]), "remark": c[9] if c[9] != "-" else None,
                                                "suppliers": len(bids)}))
        for b in bids:
            out.append((f"drugrc-bid:{tender}:{c[1]}:{b['firm_code'] or H.rid('f', b['firm'])[2:14]}", {"kind": "drugrc-bid", **base, **b}))
    return out


def parse_equipment_rc(html, group=None):
    """Equipment rate contract rows. A row without a serial number (a break-up price) points to the item above it."""
    out = []
    t = next((x for x in H.tables(html) if x.attrs.get("id") == "rcres"), None)
    parent, n_sub = None, 0
    for row in (t.rows if t else []):
        c = [x.text for x in row]
        if len(c) < 8 or c[1] in ("Equipment", "") or c[0] == "S.No.":
            continue
        is_item = bool(c[0])
        rec = {"kind": "equipmentrc", "group": group, "sl": c[0] or None, "equipment": c[1], "make": c[2] or None,
               "model": c[3] or None, "rate_ex_gst": H.num(c[4]), "gst_pct": H.num(c[5]), "rate": H.num(c[6]),
               "valid_upto": H.iso_date(c[7]), "valid_upto_raw": c[7], "breakup_of": None if is_item else parent,
               "source": url_of("equipmentrc", group) if group else None}
        n_sub = 0 if is_item else n_sub + 1
        r_id = H.rid("equipmentrc", group, c[0], c[1], c[2], c[3], c[4], c[7], "" if is_item else f"{parent}#{n_sub}")
        if is_item:
            parent = r_id
        out.append((r_id, rec))
    return out


def doc_urls(rows):
    """{document url: [record ids]} for the award and notification rows (PDFs on tnmsc.tn.gov.in)."""
    links = {}
    for r_id, d in rows:
        u = d.get("url")
        if u and u.startswith(SITE) and u.lower().endswith(".pdf"):
            links.setdefault(u, []).append(r_id)
    return links


# ---- what the task needs: pages, their parsers, document groups ----
PAGES = ([("blacklist", None)] + [("drugrc", c) for c in DRUG_TENDERS] + [("equipmentrc", g) for g in EQUIPMENT_GROUPS]
         + [("awards", y) for y in AWARD_YEARS] + [("notifications", y) for y in NOTIFICATION_YEARS])
DOC_GROUPS = {"awards": [("awards", y) for y in AWARD_YEARS], "notifications": [("notifications", y) for y in NOTIFICATION_YEARS]}


def parse(page, html, arg=None):
    return {"blacklist": lambda: parse_blacklist(html), "awards": lambda: parse_awards(html, arg),
            "notifications": lambda: parse_notifications(html, arg), "drugrc": lambda: parse_drug_rc(html, arg),
            "equipmentrc": lambda: parse_equipment_rc(html, arg)}[page]()
