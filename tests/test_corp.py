"""Parsing tests for TNMSC and RMSC on saved pages (2026-11-14; long lists trimmed, contact column removed): no network."""
from pathlib import Path

import corps
import family
import htmltables as H
import rmsc
import tnmsc

PAGES = Path(__file__).parent / "pages"


def page(name):
    return (PAGES / name).read_text(encoding="utf-8")


def test_tn_blacklist():
    rows = tnmsc.parse_blacklist(page("tnmsc-blacklist.html"))
    assert len(rows) == 93 and len({r for r, _ in rows}) == 93
    lists = {d["list"] for _, d in rows}
    assert lists == {"drug-item", "drug-firm", "equipment-firm"}
    first = rows[0][1]
    assert first["bl_code"] == "BL2425020" and first["firm"] == "SAI PARENTERALS LTD" and first["firm_code"] == "U0810"
    assert first["product"] == "MEROPENEM INJECTION IP - 500MG" and first["product_code"] == "749"
    assert first["from"] == "2024-11-25" and first["to"] == "2026-11-24" and first["nsq"] is True
    abbott = next(d for _, d in rows if d["bl_code"] == "BL2223002")
    assert abbott["list"] == "drug-firm" and abbott["product"] is None and "Pharmaceutical division" in abbott["note"]
    assert sum(d["nsq"] for _, d in rows) == 50


def test_tn_awards_and_notifications():
    aw = tnmsc.parse_awards(page("tnmsc-awards-2014.html"), 2014)
    assert len(aw) == 51 and aw[0][0] == "award:CA1"
    assert aw[0][1]["url"] == "https://tnmsc.tn.gov.in/linkfiles/contracts_awarded/CA1.pdf" and aw[0][1]["ref_date"] == "2009-05-21"
    nf = tnmsc.parse_notifications(page("tnmsc-notifications-2027.html"), 2027)
    assert [r for r, _ in nf] == ["notification:NF1808", "notification:NF1807", "notification:NF1806"]
    assert nf[0][1]["period"] == "2026-2027" and nf[0][1]["url"].endswith("/linkfiles/tender_notifications/NF1808.pdf")
    assert len(tnmsc.doc_urls(aw + nf)) == 54


def test_tn_drug_rate_contract_with_tenderers():
    rows = tnmsc.parse_drug_rc(page("tnmsc-drugrc-t25048.html"), "t25048")
    drugs = [d for _, d in rows if d["kind"] == "drugrc"]
    bids = [d for _, d in rows if d["kind"] == "drugrc-bid"]
    assert len(drugs) == 12 and len(rows) == len({r for r, _ in rows})
    assert drugs[0]["tender"] == "T25048" and drugs[0]["tender_ref_no"] == "E-022/M(P)/SPL-DRUGS/TNMSC/2025"
    assert drugs[0]["tender_title"] == "Speciality Drug Rate Contract Details"
    b = next(d for d in bids if d["drug_code"] == "G6")
    assert b["firm"] == "NIXI LABORATORIES PVT LTD" and b["firm_code"] == "U1565" and b["rate"] == 12.65 and b["order_pct"] == 100.0
    old = tnmsc.parse_drug_rc(page("tnmsc-drugrc-t18033.html"), "t18033")
    assert len(old) == 3 and old[0][1]["tender_title"].startswith("Surgical Item - Validity from")


def test_tn_equipment_rate_contract_breakups():
    rows = tnmsc.parse_equipment_rc(page("tnmsc-equipmentrc.html"), "EQUIPMENT")
    assert len(rows) == len({r for r, _ in rows})
    first = rows[0][1]
    assert (first["equipment"], first["make"], first["rate_ex_gst"], first["rate"], first["valid_upto"]) == \
        ("Dissection Microscope", "Kwality Micro Scientific", 1280.0, 1510.4, "2026-09-24")
    item4 = rows[3][0]
    assert rows[4][1]["breakup_of"] == item4 and rows[4][1]["sl"] is None


def test_rmsc_rate_contracts_without_contacts():
    rows = rmsc.parse_drugrc(page("rmsc-drugrc.html"))
    assert len(rows) == 30 and len({r for r, _ in rows}) == 30
    d = rows[0][1]
    assert d["code"] == "S119" and d["supplier"] == "Sterimed Medical Devices Pvt Ltd" and d["rate"] == 5.0 and d["level"] == "L1"
    assert d["contract_from"] == "2026-10-26" and d["contract_to"] == "2028-05-30"
    assert all("contact" not in k for _, x in rows for k in x)


def test_rmsc_bans():
    co = rmsc.parse_bans(page("rmsc-banned-company.html"), "banned-company")
    assert len(co) == 8 and all(d["nsq"] for _, d in co)
    assert co[1][1]["firm"] == "Agron Remedie" and co[1][1]["product_codes"] == ["512", "NRD-482"] and len(co[1][1]["orders"]) == 2
    assert co[0][1]["orders"][0]["url"].endswith("/Banned%20pdf/Debar%20Order1825.pdf") and co[0][1]["upto"] == "2030-11-06"
    pr = rmsc.parse_bans(page("rmsc-banned-product.html"), "banned-product")
    assert len(pr) == 20 and pr[0][1]["product_codes"] == ["103"] and pr[0][1]["nsq"] is False
    assert len(rmsc.doc_urls(co + pr)) >= 28


def test_rmsc_tenders():
    rows = rmsc.parse_tenders(page("rmsc-drug-tenders.html"), "drug-tenders")
    assert len(rows) == 25 and len({r for r, _ in rows}) == 25
    d = rows[0][1]
    assert d["to"] == "2016-03-09" and d["uploaded"] == "2016-02-02" and d["files"][0]["url"].endswith("/DRUG_TENDERS/NIB_02_01_02_2016.pdf")
    assert rmsc.nib_of("Final list of bidders for NIB-11") == "NIB-11" and rmsc.nib_of("nib 730") == "NIB-730"


def test_helpers():
    assert H.iso_date("Wed Mar 09 13:30:00 IST 2016") == "2016-03-09" and H.iso_date("26-OCT-2026") == "2026-10-26"
    assert H.num("2,37,000.00") == 237000.0 and H.num("-") is None
    assert H.page_name("equipmentrc", "REAGENTS/KITS/CONSUMABLES") == "equipmentrc-reagents-kits-consumables"
    assert tnmsc.page_url("equipmentrc", "REAGENTS/KITS/CONSUMABLES").endswith("group=REAGENTS%2FKITS%2FCONSUMABLES")


def test_corp_projects_and_pilots():
    ps = {p["name"]: p for p in family.PROJECTS}
    for name in ("medical-procurement-tnmsc", "medical-procurement-rmsc"):
        p = ps[name]
        keys = [i["key"] for i in p["items"]]
        assert len(keys) == len(set(keys)) and p["pilot"] <= set(keys)
        assert {i["key"] for i in family.queue(p)} == p["pilot"]
        assert p["probe"] in {x["name"] for x in family.PROBES}
        assert p["proxy"] == "IN"                  # neither site answers GitHub's runners
    assert len(ps["medical-procurement-rmsc"]["items"]) == 6 + sum(n for _, n in corps.RJ_DOCS.values())
