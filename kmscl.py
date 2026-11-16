"""Pure parsing of kmscl.kerala.gov.in (Kerala Medical Services Corporation Ltd.): no network here, tested on saved pages.

Pages (checked 2026-11-16; a CodeIgniter site on Apache/Windows; no robots.txt; HTTP on port 80 times out, HTTPS answers):
  home         index.php/ckmscl/index/22: the menu (on every page) links the documents of the "lists" group: the ED blacklist
               of firms, the QC blacklist of NSQ products, the Karunya (KCP) medicine price list and the no-bidder items list.
  contracts    index.php/ckmscl/contractslist/8/54/<department>: the equipment division's running (rate) contracts, one page per
               department (39 pages, 653 PDFs). Each PDF is a TCPDF "Running Contract Details" sheet: equipment, valid till,
               tender ref, supplier, GST no and the item-wise prices; a few are scanned letters (stored under ocr-needed/).
  warehouses   index.php/ckmscl/warehouselist/37: the district drug warehouses (17).
Not scraped: the QC pages (menucontentview/30 answers 0 bytes, /62 "QC Tenders & Notices" has an empty list, /68 is text only);
ED and EP tenders run on etenders.kerala.gov.in (hub project gepnic-etenders-kerala); DDMS (ddms.kmscl.kerala.gov.in) is a
login form with a captcha.
"""
import re
from urllib.parse import urljoin

import htmltables as H
import pdftables as P

SITE = "https://kmscl.kerala.gov.in/KMSCL"
# contract list pages (department id -> name), from the menu on 2026-11-16
DEPTS = {65: "Rental Reagent Contract & Reagent Contract", 9: "Anaesthesia", 72: "Animal House Dept", 69: "Biochemistry",
         12: "Blood Bank", 13: "Cardiology", 67: "Cardiovascular and Thoracic Surgery [CVTS]", 15: "Dental", 16: "Dermatology",
         17: "ENT", 18: "Forensic Medicine", 19: "Gastroenterology", 20: "General", 68: "General Surgery", 22: "Gynaecology",
         23: "Hospital Furniture", 24: "Laboratory - General", 25: "Laboratory - Specialty", 26: "Microbiology",
         70: "Molecular Diagnosis", 27: "Neonatology", 28: "Nephrology", 29: "Neurology", 30: "Neurosurgery", 71: "Oncology",
         31: "Operation Theatre Equipments", 32: "Ophthalmology", 33: "Orthopedics", 34: "Paediatrics", 35: "Pathology",
         36: "Physical Medicine & Rehabilitation", 73: "Physiology", 66: "Pulmonary Medicine", 38: "Radiodiagnosis",
         39: "Radiology", 63: "REAGENTS", 40: "Respiratory Medicine Equipments", 41: "Skill Lab", 42: "Urology"}
_PATHS = {"home": "index.php/ckmscl/index/22", "warehouses": "index.php/ckmscl/warehouselist/37"}
PAGES = [("home", None), ("warehouses", None)] + [("contracts", d) for d in DEPTS]
DOC_GROUPS = {"lists": [("home", None)], "contracts": [("contracts", d) for d in DEPTS]}

# menu documents by their link text
_KINDS = [("blacklist-firms", r"blacklisted firms"), ("blacklist-nsq", r"blacklisted items"), ("price-list", r"medicine price"),
          ("no-bidder", r"no bidder")]


def page_url(page, arg=None):
    if page == "contracts":
        return f"{SITE}/index.php/ckmscl/contractslist/8/54/{arg}"
    return f"{SITE}/{_PATHS[page]}"


def _abs(href):
    """Absolute https URL (the menu links http://, which does not answer)."""
    return re.sub(r"^http://", "https://", urljoin(SITE + "/", (href or "").strip()))


def _text(s):
    return H.clean(re.sub(r"<[^>]+>", " ", s))


def parse_home(html):
    """The documents linked from the menu: one record per document (title, kind, url)."""
    out = []
    for href, label in re.findall(r'<a[^>]*href="([^"]*/uploads/[^"]+)"[^>]*>(.*?)</a>', html, flags=re.S):
        title = _text(label)
        kind = next((k for k, rx in _KINDS if re.search(rx, title, re.I)), None)
        if kind:
            out.append((H.rid("menu", title), {"kind": "document", "title": title, "doc_kind": kind, "url": _abs(href),
                                               "source": page_url("home")}))
    return out


def parse_contracts(html, dept):
    """One record per contract PDF on a department page (title, url)."""
    out = []
    for title, href in re.findall(r'<h6>(.*?)</h6>.*?<a href="([^"]*)"', html.split("list-box", 1)[-1], flags=re.S):
        url = _abs(href)
        if not url.lower().endswith(".pdf"):           # five rows link the bare folder uploads/contract/
            continue
        out.append((H.rid("contract-link", dept, url), {"kind": "contract-link", "dept_id": dept, "dept": DEPTS.get(dept),
                                                         "title": _text(title), "url": url, "doc_kind": "contract",
                                                         "source": page_url("contracts", dept)}))
    return out


def parse_warehouses(html):
    out = []
    for code, body in re.findall(r'<div class="tl-circ">(.*?)</div>(.*?)</li>', html, flags=re.S):
        name = _text((re.search(r"<h4>(.*?)</h4>", body, re.S) or [None, ""])[1])
        addr = _text(re.sub(r"<br\s*/?>", ", ", (re.search(r"<strong>(.*?)</strong>", body, re.S) or [None, ""])[1]))
        labels = [_text(x) for x in re.findall(r"<label>(.*?)</label>", body, re.S)]
        pin = re.search(r"\b6\d{5}\b", addr)
        out.append((H.rid("warehouse", code, addr), {
            "kind": "warehouse", "district_code": _text(code), "name": name, "address": addr, "pincode": pin.group(0) if pin else None,
            "phones": [x for x in labels if "@" not in x and x.upper() != "NOT AVAILABLE"],
            "email": next((x for x in labels if "@" in x), None), "source": page_url("warehouses")}))
    return out


def parse(page, html, arg=None):
    if page == "contracts":
        return parse_contracts(html, arg)
    if page == "warehouses":
        return parse_warehouses(html)
    return parse_home(html)


def doc_urls(rows):
    links = {}
    for r_id, d in rows:
        u = d.get("url")
        if u and u.startswith(SITE):
            links.setdefault(u, []).append(r_id)
    return links


# ---- documents ---------------------------------------------------------------------------------------------------------------

def _firm(s):
    return re.sub(r"^M\s*/\s*s\.?\s*", "", s or "", flags=re.I).strip()


_HEAD = {"Equipment Name": "item", "Running Contract Valid Till": "valid_to_raw", "Tender Ref No": "tender_ref",
         "Tendered Quantity": "quantity_raw", "Supplier Name": "firm_raw", "GST No": "gst_no",
         "Installation & Delivery Period": "delivery", "Up-time / PM vist": "uptime_pm", "Warranty period": "warranty"}
_NUM = r"\d[\d,]*(?:\.\d+)?"
_ITEM = re.compile(rf"^\s{{0,8}}(?P<sl>\d{{1,3}})\s{{2,}}(?P<name>\S.*?)\s{{2,}}(?:(?P<qty>\d[\d,]*)\s{{2,}})?(?P<rate>{_NUM})\s{{2,}}"
                   rf"(?P<svc>{_NUM})\s{{2,}}(?P<total>{_NUM})\s*$")


def parse_contract(pages):
    """A "Running Contract Details" PDF: one record with the contract's terms and its item-wise prices; [] for other layouts
    (letters, scans)."""
    text = "\n".join(pages)
    head = {}
    for ln in text.splitlines()[:40]:
        m = re.match(r"^\s*(.+?)\s{2,}(\S.*?)\s*$", ln)
        if m and m.group(1) in _HEAD:
            head[_HEAD[m.group(1)]] = m.group(2)
    if "item" not in head or "firm_raw" not in head:
        return []
    start = text.find("Item-wise Price Details")
    stop = min([i for i in (text.find(w, start) for w in ("Annual / Comprehensive", "Other terms", "Technical Specification"))
                if i > 0] or [len(text)])
    items, last = [], None
    for ln in text[start:stop].splitlines()[1:] if start >= 0 else []:
        if "Running Contract Notice" in ln:              # page footer
            continue
        ln = ln.replace("Item-wise Price Details", "")    # the next page's title can share a line with a wrapped cell
        m = _ITEM.match(ln)
        if m:
            items.append({"sl": int(m.group("sl")), "item": m.group("name"), "make": None,
                          "qty": H.num(m.group("qty") or ""), "rate": H.num(m.group("rate")), "service_charge": H.num(m.group("svc")),
                          "total": H.num(m.group("total")), "gst_pct": None})
            last = "item"
            continue
        if not items:
            continue
        g = re.search(r"Incl\.\s*GST\s*:\s*(\d+(?:\.\d+)?)\s*%", ln)
        if g:
            items[-1]["gst_pct"] = float(g.group(1))
        rest = H.clean(re.sub(r"Incl\.\s*GST\s*:\s*[\d.]+\s*%", " ", ln))
        if not rest or re.fullmatch(rf"(?:{_NUM}\s*)+", rest):    # blank, or the totals line
            continue
        mk = re.match(r"Model & Make\s*:\s*(.*)$", rest)
        if mk:
            items[-1]["make"], last = mk.group(1) or None, "make"
        elif last == "make":
            items[-1]["make"] = f"{items[-1]['make'] or ''} {rest}".strip()
        else:
            items[-1]["item"] = f"{items[-1]['item']} {rest}"
    d = {"kind": "contract", **head, "firm": _firm(head["firm_raw"]), "valid_to": H.iso_date(head.get("valid_to_raw", "")),
         "items": items, "n_items": len(items), "rate": items[0]["rate"] if len(items) == 1 else None}
    return [(H.rid("contract", head.get("tender_ref"), head["item"], d["firm"]), d)]


_DMY = r"\d{1,2}\.\d{1,2}\.\d{4}"


def _blacklist_id(lst, firm, product, to_raw, ref):
    return H.rid(f"blacklist:{lst}", firm, product, to_raw, ref)


def parse_blacklist_firms(pages):
    """ED division's list of blacklisted firms: firm (with address), from, order no & date, valid upto, reason."""
    out = []
    rows = P.rows(pages, lambda ln: bool(re.match(rf"^\s*\d{{1,3}}\.\s.*{_DMY}", ln)), "nearest",
                  start=lambda ln: "valid upto" in ln.lower())
    for c in rows:
        if len(c) < 6:
            continue
        firm_raw = c[1]
        firm = _firm(re.split(r",", firm_raw, 1)[0])
        ref = re.sub(r"([/-]) ", r"\1", c[3])             # an order number wrapped after "-" or "/"
        out.append((_blacklist_id("drug-firm", firm, None, c[4], ref), {
            "kind": "blacklist", "list": "drug-firm", "sl": c[0].rstrip("."), "firm": firm, "firm_raw": firm_raw, "product": None,
            "from": H.iso_date(c[2]), "to": H.iso_date(c[4]), "from_raw": c[2], "to_raw": c[4], "reference": ref,
            "order_date": H.iso_date((re.findall(_DMY, ref) or [""])[-1]), "reason": c[5], "nsq": False, "tender_year": None}))
    return out


def parse_blacklist_nsq(pages):
    """QC division's list of products blacklisted for NSQ: product, firm (with address), tender year, valid upto, order."""
    out = []
    # shortcut: a row starts at its "M/s" line (it can sit above the serial number); columns come from the fullest such line.
    # Upgrade to anchors on the serial line if a new version of the list parses wrong (the test checks the 3 rows).
    rows = P.rows(pages, lambda ln: bool(re.search(r"\bM/s\b", ln)), "below", start=lambda ln: "Black Listing Order" in ln)
    for c in rows:
        if len(c) < 6:
            continue
        product, firm_raw, ref = c[1], c[2], c[5]
        firm = _firm(re.split(r",|\s+[A-Z]-?\d", firm_raw, 1)[0])
        out.append((_blacklist_id("drug-item", firm, product, c[4], ref), {
            "kind": "blacklist", "list": "drug-item", "sl": c[0].rstrip("."), "firm": firm, "firm_raw": firm_raw, "product": product,
            "from": None, "to": H.iso_date(c[4]), "from_raw": None, "to_raw": c[4], "reference": ref,
            "order_date": H.iso_date((re.findall(_DMY, ref) or [""])[-1]), "reason": "Not of Standard Quality (NSQ)", "nsq": True,
            "tender_year": c[3] or None}))
    return out


_PRICE = re.compile(r"^\s*(?P<sl>\d{1,5})\s+(?P<product>.+?)\s*(?P<unit>NUMBERS|VIAL|UNITS?|ML|STRIPS)\s+(?P<price>\d[\d,]*\.\d+)\s+"
                    r"(?P<mrp>\d[\d,]*\.\d+)\s*$")


def parse_price_list(pages):
    """Karunya community pharmacies' price list: one record per product (company, unit, KCP selling price, MRP)."""
    out, seen, company = [], {}, None
    date = re.search(r"Report Date:\s*(\d{2}/\d{2}/\d{4})", pages[0] if pages else "")
    report_date = H.iso_date(date.group(1)) if date else None
    for ln in "\n".join(pages).splitlines():
        c = re.match(r"^\s*Company:\s*(.+?)\s*$", ln)
        if c:
            company = c.group(1)
            continue
        m = _PRICE.match(ln)
        if not m:
            continue
        d = {"kind": "price", "sl": int(m.group("sl")), "company": company, "product": H.clean(m.group("product")),
             "unit": m.group("unit"), "kcp_price": H.num(m.group("price")), "mrp": H.num(m.group("mrp")), "report_date": report_date}
        key = H.rid("price", company, d["product"], d["unit"])
        seen[key] = seen.get(key, 0) + 1
        out.append((key if seen[key] == 1 else f"{key}-{seen[key]}", d))
    return out


_DOC_PARSERS = {"contract": parse_contract, "blacklist-firms": parse_blacklist_firms, "blacklist-nsq": parse_blacklist_nsq,
                "price-list": parse_price_list}


def parse_doc(url, data, txt, link_rows):
    """Records from a linked document, by the kind of the row that links it; [] for kinds that are only stored and for scans."""
    kind = next((r.get("doc_kind") for r in link_rows if r.get("doc_kind")), None)
    if kind not in _DOC_PARSERS or not data.startswith(b"%PDF"):
        return []
    return _DOC_PARSERS[kind](P.layout_pages(data))
