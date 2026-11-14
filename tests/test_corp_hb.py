"""Parsing tests for HMSCL (Haryana) and BMSICL (Bihar) on saved pages and files (2026-11-14, trimmed): no network."""
from pathlib import Path

import hmscl

PAGES = Path(__file__).parent / "pages"


def page(name):
    return (PAGES / name).read_text(encoding="utf-8")


def test_hmscl_drug_rc():
    rows = hmscl.parse("drugrc", page("hmscl-drugrc.html"))
    assert len(rows) == 10 and len({r for r, _ in rows}) == 10
    d = rows[0][1]
    assert d["code"] == "6.3.68.2" and d["item"] == "Azithromycin Tablet 500 mg" and d["vendor"] == "HEALERS LAB"
    assert d["rate"] == 7.75 and d["rc_number"] == "1319" and d["valid_from"] == "2025-05-19" and d["valid_to"] == "2027-05-18"
    assert all(r.startswith("drugrc:") for r, _ in rows)


def test_hmscl_equipment_rc():
    rows = hmscl.parse("equipmentrc", page("hmscl-equipmentrc.html"))
    d = rows[0][1]
    assert len(rows) == 10 and d["list"] == "equipment" and d["item"] == "150 MA X-RAY MACHINE HF" and d["rate"] == 240000.0
    assert d["vendor"] == "AMRAD MEDICAL EQUIPMENTS" and d["valid_to"] == "2028-09-21"


def test_hmscl_banned():
    rows = hmscl.parse("banned", page("hmscl-banned.html"))
    assert len(rows) == 6
    d = rows[0][1]
    assert d["firm"] == "Nestor Pharmaceuticals Limited" and d["category"] == "Drugs" and d["status"] == "Banned"
    assert d["from"] == "2026-01-27" and d["to"] == "2029-01-26" and d["reason"] == "Quality Failure" and d["nsq"] is True
    assert d["order_number"] == "5714-5725"
    assert sum(x["nsq"] for _, x in rows) == 3
    links = hmscl.doc_urls(rows)
    assert len(links) == 6 and all("BlacklistAsset.ashx?key=" in u for u in links)


import bmsicl  # noqa: E402

MEDIA = "http://bmsicl.gov.in/new/bmsicl_media/2024/09/"


def test_bmsicl_blacklist_posts():
    rows = bmsicl.parse("blacklist", page("bmsicl-blacklist-1.html"), 1)
    assert len(rows) == 10 and len({r for r, _ in rows}) == 10
    d = rows[0][1]
    assert d["firm"] == "Shivalik Remedies Private Limited" and d["action"] == "blacklist" and d["date"] == "2026-10-29"
    revoke = [x for _, x in rows if x["action"] == "revoke"]
    assert revoke and revoke[0]["firm"] == "Kanha Biogenetic"
    last = bmsicl.parse("blacklist", page("bmsicl-blacklist-9.html"), 9)
    assert len(last) == 3 and last[-1][1]["date"] == "2018-01-15"
    eq = bmsicl.parse("equipment-blacklist", page("bmsicl-equipment-blacklist.html"))
    assert len(eq) == 4 and eq[0][1]["list"] == "equipment" and eq[0][1]["action"] == "revoke"
    assert bmsicl.page_url("blacklist", 3).endswith("/drugs/drug-blacklist-debarred/page/3/")
    assert bmsicl.page_url("blacklist", 1).endswith("/drugs/drug-blacklist-debarred/")


def test_bmsicl_post_attachments():
    att = bmsicl.attachments("http://bmsicl.gov.in/new/drug-tenders/x/", page("bmsicl-post.html"))
    assert att == ["http://bmsicl.gov.in/new/module_6/download.php?id=Nzg0OA==&file=MQ=="]


def test_bmsicl_rc_links():
    home = bmsicl.parse("home", page("bmsicl-home.html"))
    status = bmsicl.parse("rc-status", page("bmsicl-rc-status.html"))
    files = {d["file"] for _, d in home + status}
    assert "Rate-Contract-DetailsDrug-Active-04.03.23-1.xlsx" in files and "Equipment-Rate-Contract.xlsx" in files
    assert "Rate-Contract-DetailsDrug-Active-.pdf" in files and "procurement-manual-website.pdf" not in files
    assert set(bmsicl.doc_urls(home + status)) == {d["url"] for _, d in home + status}


def test_bmsicl_rc_xlsx():
    data = (PAGES / "bmsicl-rc-drug.xlsx").read_bytes()
    rows = bmsicl.parse_doc(MEDIA + "Rate-Contract-DetailsDrug-Active-04.03.23-1.xlsx", data, "")
    assert len(rows) == 6
    alt = rows[4][1]
    assert alt["alternate_supplier"] is True and alt["code"] == "D0004" and alt["supplier"] == "Unicure India Ltd"
    d = rows[0][1]
    assert d["code"] == "D0869" and d["supplier"] == "Gentech Healthcare Pvt Ltd" and d["rate"] == 3.76
    assert d["valid_from"] == "2023-10-16" and d["valid_to"] == "2025-10-16" and d["list"] == "drug"
    eq = bmsicl.parse_doc(MEDIA + "Equipment-Rate-Contract.xlsx", (PAGES / "bmsicl-rc-equipment.xlsx").read_bytes(), "")
    e = eq[0][1]
    assert e["list"] == "equipment" and e["rate"] == 711200.0 and e["tax_included"] is True and e["model"] == "ABL 800 Flex"
    assert e["valid_from"] == "2024-02-11" and e["code"] is None
    assert bmsicl.parse_doc(MEDIA + "Notice.pdf", b"%PDF-1.4", "x") == []


def test_bmsicl_rc_pdf_text():
    rows = bmsicl.parse_pdf_text(page("bmsicl-rc-drug-2025.txt"), "Rate-Contract-DetailsDrug-Active-.pdf")
    d = rows[1][1]
    assert d["item"] == "Acetazolamide Tab 250 mg" and d["dosage_form"] == "Tablet" and d["supplier"] == "Modern Laboratories"
    assert d["rate"] == 0.95 and d["serial"] == 2
    alts = [x for _, x in rows if x["item"].startswith("Albendazole Tablets") and x["serial"] is None]
    assert len(alts) >= 2 and all(x["rate"] == 0.95 for x in alts)
    assert sum(x["parsed"] for _, x in rows) >= len(rows) - 1
