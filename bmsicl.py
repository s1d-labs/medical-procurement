"""Pure parsing of bmsicl.gov.in (Bihar Medical Services and Infrastructure Corporation Ltd.): no network here, tested on saved
pages and files.

The site (checked 2026-11-14) is WordPress under http://bmsicl.gov.in/new/ and answers on HTTP only (HTTPS does not connect).
  blacklist            drugs/drug-blacklist-debarred/[page/<n>/]: posts, 10 per page (9 pages, 2018-2026): title (firm, or
                       "Revoking of blacklisting order of <firm>"), date, post link. Each post page links its order through
                       module_6/download.php?id=<base64 post id>&file=<base64 n> (mostly scans: product, period and reason are
                       only in the scan, so they wait for OCR).
  equipment-blacklist  equipments/equipment-blacklist-debarred/: the same for equipment firms (4 posts).
  home, rc-status      the home page and drugs/drug-procurement-status/ link the rate contract files (XLSX, and a text PDF from
                       2025). File names change with each update, so the links are read from these pages.
Rate contract files (parse_rc_file): XLSX sheets with a header row (drug name with code, code, strength, dosage form, supplier,
rate per unit, valid from, valid up to), and the 2025 drug list as a text PDF (drug, dosage form, supplier, rate). BMSICL does
not publish a batch-level NSQ list.
"""
import io
import re
from datetime import date, datetime
from urllib.parse import urljoin

import htmltables as H

SITE = "http://bmsicl.gov.in/new"
BLACKLIST_PAGES = 9          # 2026-11-14: 83 posts
_PATHS = {"home": "/", "rc-status": "/drugs/drug-procurement-status/", "blacklist": "/drugs/drug-blacklist-debarred/",
          "equipment-blacklist": "/equipments/equipment-blacklist-debarred/"}
_RC_FILE = re.compile(r"/bmsicl_media/\d{4}/\d{2}/[^\"'<> ]*(?:Rate-Contract|Rate_Contract|RateContract)[^\"'<> ]*\.(?:xlsx|pdf)$", re.I)


def page_url(page, arg=None):
    url = SITE + _PATHS[page]
    if page == "blacklist" and arg and int(arg) > 1:
        url += f"page/{int(arg)}/"
    return url


def _date(s):
    try:
        return datetime.strptime(H.clean(s), "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


_ITEM = re.compile(r'<div class="cplp-title"><a href="([^"]+)"[^>]*>(.*?)</a></div>\s*<div class="cplp-meta">'
                   r'\s*<span class="cplp-date">([^<]*)</span>', re.S)
_REVOKE = re.compile(r"revok", re.I)
_FIRM = re.compile(r"(?:.*?\b(?:of|to)\s+)?M/s\.?\s*(.+)$", re.I)


def firm_of(title):
    t = H.clean(title)
    m = _FIRM.match(t)
    firm = m.group(1) if m else t
    return firm.strip(" .") or None


def parse_posts(html, page, arg=None):
    """Blacklist posts: one record per post (title, firm, action, date, post link)."""
    out = []
    for i, (href, title, d) in enumerate(_ITEM.findall(html), 1):
        title = H.clean(re.sub(r"<[^>]+>", " ", title))
        url = urljoin(SITE + "/", href)
        out.append((H.rid(page, url), {
            "kind": "ban_post", "list": "equipment" if page == "equipment-blacklist" else "drug", "page_no": int(arg or 1),
            "position": i, "title": title, "firm": firm_of(title),
            "action": "revoke" if _REVOKE.search(title) else "blacklist", "date": _date(d), "date_raw": H.clean(d),
            "post_url": url, "source": page_url(page, arg)}))
    return out


def parse_rc_links(html, page):
    """Rate contract files linked from a page: one record per file link."""
    out, seen = [], set()
    for href, text in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        url = urljoin(SITE + "/", href.strip())
        if not _RC_FILE.search(url) or url in seen:
            continue
        seen.add(url)
        out.append((H.rid("rcfile", url), {"kind": "rc_file", "url": url, "file": url.rsplit("/", 1)[-1],
                                            "text": H.clean(re.sub(r"<[^>]+>", " ", text)) or None, "source": page_url(page)}))
    return out


def attachments(post_url, html):
    """Order files linked from a blacklist post page (module_6/download.php)."""
    out = []
    for href in re.findall(r'href="([^"]*module_6/download\.php\?[^"]+)"', html):
        u = urljoin(post_url, href.replace("&#038;", "&").replace("&amp;", "&"))
        if u not in out:
            out.append(u)
    return out


# ---- rate contract files ----

def _cell(v):
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v.date().isoformat() if isinstance(v, datetime) else v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return H.clean(str(v))


def _day(v):
    s = _cell(v)
    return s if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else H.iso_date(s)


_HEAD = {"drug name": "item", "equipment name": "item", "code": "code", "strength": "strength", "dosages": "dosage_form",
         "supplier name": "supplier", "rate(per unit)": "rate", "rate (per unit)": "rate", "unit rate": "rate",
         "valid from": "valid_from", "valid upto": "valid_to", "rc period": "period", "rc no": "rc_number",
         "model name": "model", "rwh active stock": "stock_active", "rwh qc stock": "stock_qc"}


def _list_of(file):
    f = file.lower()
    return next((k for k in ("drug", "reagent", "surgical", "equipment") if k in f), None)


def _code(item):
    """'3 Layer Mask [S0238][ EDL ]' -> 'S0238'."""
    m = re.search(r"\[([A-Z]{1,2}\d{3,6})\]", item or "")
    return m.group(1) if m else None


def parse_xlsx(data, file):
    """Rows of every sheet that has a 'Supplier Name' header row."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out, seen = [], {}
    for ws in wb.worksheets:
        col, item_type, rate_head, last = None, None, "", None
        for row in ws.iter_rows(values_only=True):
            cells = [_cell(v) for v in row]
            low = [c.lower().strip() for c in cells]
            joined = " ".join(low)
            if "item type" in joined:
                item_type = re.sub(r".*item type\s*:?-?\s*", "", joined).strip() or None
            if col is None:
                if "supplier name" in low:
                    col = {}
                    for i, h in enumerate(low):
                        k = next((v for name, v in _HEAD.items() if h == name or h.startswith(name + " ")), None)
                        if k and k not in col:
                            col[k] = i
                    rate_head = next((cells[i] for i, h in enumerate(low) if "rate" in h), "")
                continue
            g = lambda k: cells[col[k]] if k in col and col[k] < len(cells) else ""      # noqa: E731
            if not g("supplier"):
                continue
            alt = not g("item")                  # another supplier of the drug above (merged cells in the sheet)
            if alt and last is None:
                continue
            if not alt:
                last = (g("item"), g("code"))
            rate_raw = g("rate")
            period = g("period")
            m = re.match(r"(.+?)\s+to\s+(.+)", period) if period else None
            d = {"kind": "rc", "list": item_type or _list_of(file), "file": file,
                 "item": last[0], "code": last[1] or _code(last[0]), "alternate_supplier": alt, "strength": g("strength") or None,
                 "dosage_form": g("dosage_form") or None, "model": g("model") or None, "rc_number": g("rc_number") or None,
                 "supplier": re.sub(r"^M/s\.?\s*", "", g("supplier"), flags=re.I), "rate": H.num(rate_raw), "rate_raw": rate_raw,
                 "tax_included": "inclusive of tax" in rate_head.lower() or None, "valid_from": _day(g("valid_from")) if "valid_from" in col else (H.iso_date(m.group(1)) if m else None),
                 "valid_to": _day(g("valid_to")) if "valid_to" in col else (H.iso_date(m.group(2)) if m else None),
                 "stock_active": H.num(g("stock_active")), "stock_qc": H.num(g("stock_qc"))}
            key = H.rid("rc", file, d["item"], d["code"], d["supplier"], d["valid_from"], d["model"])
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 1:
                key = f"{key}-{seen[key]}"
            out.append((key, d))
    return out


# dosage forms in the BMSICL lists (longest first, so "Oral Liquid" wins over "Liquid")
DOSAGE_FORMS = sorted(["Tablet", "Capsule", "Injection", "Ointment", "Cream", "Gel", "Suspension", "Oral Liquid", "Syrup", "Drops",
                       "Eye Drops", "Ear Drops", "Lotion", "Powder", "Solution", "Inhaler", "Inhalation", "Suppository",
                       "Infusion", "Vaccine", "Dry Syrup", "Respules", "Spray", "Granules", "Sachet", "Pessary", "Lozenges",
                       "Liquid", "Emulsion", "Paste", "Mouthwash", "Shampoo", "Soap", "Jelly", "Patch", "Kit", "Dusting Powder",
                       "Drop", "Eye/ Ear Drop", "Eye/Ear Drop", "Nasal Drop", "Pessaries", "Pessary"],
                      key=len, reverse=True)
_FORM = re.compile(r"\b(" + "|".join(re.escape(f) for f in DOSAGE_FORMS) + r")\b(?!.*\b(?:" +
                   "|".join(re.escape(f) for f in DOSAGE_FORMS) + r")\b)\s+(.+)$", re.I)
_LINE_END = re.compile(r"\s(\d+(?:\.\d+)?)$")


def parse_pdf_text(text, file):
    """The 2025 drug list (text PDF): 'S.No Drug Name Dosages Supplier Name RATE'. A row ends at a line that ends with the
    rate; alternative suppliers of the same drug come without a serial number. Best effort: rows that do not split are kept
    with parsed=False."""
    out, buf, seen = [], [], {}
    for line in (text or "").splitlines():
        line = H.clean(line)
        if not line or line.lower().startswith("s.no"):
            continue
        buf.append(line)
        m = _LINE_END.search(line)
        if not m:
            continue
        joined = H.clean(" ".join(buf))
        buf = []
        rate = float(m.group(1))
        body = joined[:-len(m.group(0))].strip()
        sn = re.match(r"^(\d{1,4})\s+(.*)$", body)
        serial, body = (int(sn.group(1)), sn.group(2)) if sn else (None, body)
        f = _FORM.search(body)
        if f:
            item, form, supplier = body[:f.start()].strip(" -"), f.group(1), f.group(2).strip()
        else:
            item, form, supplier = body, None, None
        d = {"kind": "rc", "list": "drug", "file": file, "serial": serial, "item": item, "dosage_form": form,
             "supplier": supplier, "rate": rate, "parsed": bool(f and supplier and item), "line": joined[:300]}
        key = H.rid("rc", file, item, supplier, rate)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            key = f"{key}-{seen[key]}"
        out.append((key, d))
    return out


def parse_doc(url, data, text):
    """Rows from a downloaded rate contract file (XLSX or text PDF); other files give no rows."""
    file = url.rsplit("/", 1)[-1]
    if not _RC_FILE.search(url):
        return []
    if data[:2] == b"PK":
        return parse_xlsx(data, file)
    if data[:5] == b"%PDF-":
        return parse_pdf_text(text, file)
    return []


PAGES = ([("home", None), ("rc-status", None), ("equipment-blacklist", None)] +
         [("blacklist", n) for n in range(1, BLACKLIST_PAGES + 1)])
DOC_GROUPS = {"rc": [("home", None), ("rc-status", None)],
              "orders": [("blacklist", n) for n in range(1, BLACKLIST_PAGES + 1)] + [("equipment-blacklist", None)]}


def parse(page, html, arg=None):
    if page in ("blacklist", "equipment-blacklist"):
        return parse_posts(html, page, arg)
    return parse_rc_links(html, page)


def doc_urls(rows):
    """{url: [record ids]}: rate contract files, and blacklist post pages (their order files come through attachments())."""
    links = {}
    for r_id, d in rows:
        u = d.get("url") or d.get("post_url")
        if u and u.startswith(SITE):
            links.setdefault(u, []).append(r_id)
    return links
