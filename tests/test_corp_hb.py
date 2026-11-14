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
