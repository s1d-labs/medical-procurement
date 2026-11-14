"""West Bengal Medical Services Corporation (www.wbmsc.gov.in): pure parsing helpers, no network. Tested on saved pages.

The site is small and flat: each listing (tender.php, notice.php, award-of-work.php, recruitment-notice.php) is ONE page with
every row since 2011 (tender.php: ~7,300 rows, 3 MB), so there is no pagination. Each row links a document named
<section>/wbmsc-<section>-<N>.pdf, where N is a random number from 1 to 9999. The site reuses a number and OVERWRITES the older file:
in Nov 2026, 1,586 file names were shared by two or more different tenders. So:
  - a row's id is a hash of its own text (section, number, date, title), never the file name;
  - a document's id includes the sha256 of its bytes, so every version we ever see is kept;
  - older versions come back from the Wayback Machine (wayback.py).
"""
import hashlib
import html
import re
from datetime import datetime

SITE = "https://www.wbmsc.gov.in"

# section -> listing page; the section is also the folder of its documents (tender/, notice/, award/, recruitment/)
LISTINGS = {"tender": "tender.php", "notice": "notice.php", "award": "award-of-work.php", "recruitment": "recruitment-notice.php"}
OTHER_PAGES = ["index.php", "contact_us.php", "management.php", "organogram.php", "future-plan.php"]

_ROW = re.compile(r"<tr(?![^>]*class=\"head\")[^>]*>(.*?)</tr>", re.S | re.I)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_HREF = re.compile(r"href=[\"']([^\"']+)[\"']", re.I)
_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
GEM_BID = re.compile(r"GEM/(\d{4})/([BR])/(\d+)", re.I)
NIT = re.compile(r"WBMSC?L?\s*/\s*(NIT|NIQ|NIB|EOI|RFP|ITB)\s*[-:#\s]*\s*(\d+)\s*/\s*(\d{4})", re.I)


def text(s):
    return _WS.sub(" ", html.unescape(_TAGS.sub(" ", s))).replace("�", " ").strip()


def iso_date(s):
    """'Friday, November 13, 2026' -> '2026-11-13'; None when the site wrote something else."""
    try:
        return datetime.strptime(s.strip(), "%A, %B %d, %Y").date().isoformat()
    except ValueError:
        return None


def doc_url(href, base=SITE):
    """'./tender/wbmsc-tender-73.pdf ' -> 'https://www.wbmsc.gov.in/tender/wbmsc-tender-73.pdf'. External links stay as they are."""
    href = href.strip()
    if re.match(r"https?://", href, re.I):
        return href
    return base.rstrip("/") + "/" + re.sub(r"^\./", "", href).lstrip("/")


def classify(title, number):
    """What a row is, from its title and number: kind, GeM bid number, normalised NIT number, urgency."""
    t = title.lower()
    if re.match(r"\s*(amendment|corrigendum|addendum|addenda|corrigenda|modification|clarification|pre[- ]?bid)", t):
        kind = "amendment"
    elif re.search(r"\bcancel", t):
        kind = "cancellation"
    elif re.search(r"(date|time)\s*extension|extension of (date|time)|\bextended\b", t):
        kind = "extension"
    elif re.search(r"\bresult|\baward|selection|letter of (acceptance|intent)|\bloa\b|\bloi\b", t):
        kind = "result"
    else:
        kind = "notice"
    out = {"kind": kind, "urgent": bool(re.search(r"urgent|emergency|emergent", t))}
    both = f"{number} {title}"
    if m := GEM_BID.search(both):
        out["gem_bid"] = f"GEM/{m.group(1)}/{m.group(2).upper()}/{m.group(3)}"
    if m := NIT.search(both):
        out["nit"] = f"WBMSCL/{m.group(1).upper()}-{int(m.group(2))}/{m.group(3)}"
    if m := re.search(r"AAES\s*[-:#]?\s*(\d+)", both, re.I):
        out["aaes"] = int(m.group(1))
    return out


def row_id(section, number, date_raw, title, href=""):
    """Stable id of a listing row, from its text and its link. The link alone cannot be the id: the site reuses file names for
    new tenders. The text alone is not unique: one tender can have several rows with the same text, each linking its own file."""
    key = "|".join([section, _WS.sub(" ", number).strip().lower(), date_raw.strip().lower(), _WS.sub(" ", title).strip().lower(),
                    (href or "").strip().lower()])
    return f"{section}:{hashlib.sha1(key.encode()).hexdigest()[:20]}"


def parse_listing(page, section):
    """[(record_id, data)] for every row of one listing page (tender.php, notice.php, ...). Pure.

    Rows are numbered from the top (newest first). A row repeated with the same text and link is stored once; `repeats` counts
    the copies."""
    out, seen = [], {}
    for pos, m in enumerate(_ROW.finditer(page), 1):
        tds = _TD.findall(m.group(1))
        if len(tds) < 4:
            continue
        a = _HREF.search(tds[1])
        sl, title, number, date_raw = text(tds[0]), text(tds[1]), text(tds[2]), text(tds[3])
        if not title and not a:
            continue
        href = a.group(1).strip() if a else None
        rid = row_id(section, number, date_raw, title, href)
        if rid in seen:
            seen[rid]["repeats"] += 1
            continue
        data = {"section": section, "position": pos, "sl": sl, "title": title, "number": number, "date": iso_date(date_raw),
                "date_raw": date_raw, "href": href, "url": doc_url(href) if href else None,
                "file": href.rsplit("/", 1)[-1] if href else None, "repeats": 0, **classify(title, number)}
        seen[rid] = data
        out.append((rid, data))
    return out


def shard_of(key, shards):
    # not htmltables.shard_of: this one hashes 8 hex digits, and WBMSC shard keys are already seeded with it
    return int(hashlib.sha1(key.encode()).hexdigest()[:8], 16) % shards


def doc_urls(rows):
    """{url: [row ids]} for the documents a listing links (one url can serve several rows: amendments, reused names)."""
    out = {}
    for rid, d in rows:
        if d.get("url") and d["url"].startswith(SITE):
            out.setdefault(d["url"], []).append(rid)
    return out
