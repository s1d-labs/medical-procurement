"""Parsing tests for KMSCL (Kerala) on saved pages and on the layout text of its PDFs (2026-11-16; suppliers' contact persons,
phones and e-mails removed from the contract sheets; the price list cut to 3 of 303 pages): no network."""
from pathlib import Path

import corps
import family
import kmscl

PAGES = Path(__file__).parent / "pages"


def page(name):
    return (PAGES / name).read_text(encoding="utf-8")


def layout(name):
    return page(name).split("\f")


def test_menu_documents_use_https():
    rows = kmscl.parse("home", page("kmscl-contracts-65.html"))        # the menu is the same on every page
    kinds = {d["doc_kind"]: d["url"] for _, d in rows}
    assert set(kinds) == {"blacklist-firms", "blacklist-nsq", "price-list", "no-bidder"}
    assert kinds["blacklist-nsq"] == "https://kmscl.kerala.gov.in/KMSCL/uploads/blacklisting/QCblacklisting.pdf"
    assert len(kmscl.doc_urls(rows)) == 4


def test_contract_list_page():
    rows = kmscl.parse("contracts", page("kmscl-contracts-65.html"), 65)
    assert len(rows) == 13 and all(d["url"].endswith(".pdf") and d["doc_kind"] == "contract" for _, d in rows)
    assert rows[0][1]["title"] == "Computerized Radiography Model B- Rate for CR Films" and rows[0][1]["dept"].startswith("Rental")
    assert len(kmscl.doc_urls(rows)) == 13


def test_warehouses():
    rows = kmscl.parse("warehouses", page("kmscl-warehouses.html"))
    assert len(rows) == 17 and len({r for r, _ in rows}) == 17
    tvm = rows[0][1]
    assert tvm["district_code"] == "TVM" and tvm["pincode"] == "695037" and tvm["email"] == "mgrtvm.kmscl@kerala.gov.in"
    assert "NOT AVAILABLE" not in rows[1][1]["phones"]


def test_contract_one_item():
    (rid, d), = kmscl.parse_contract(layout("kmscl-rc-static-cycle.txt"))
    assert d["item"] == "Static Cycle" and d["firm"] == "Bharat Medical System" and d["tender_ref"] == "KMSCL/EP/T484/343/2022"
    assert d["valid_to"] == "2026-12-31" and d["gst_no"] == "33AEXPJ4035M1Z2" and d["rate"] == 26550
    assert d["items"] == [{"sl": 1, "item": "Static Cycle", "make": "Bharath Medical Systems", "qty": None, "rate": 26550,
                           "service_charge": 1858.5, "total": 28408.5, "gst_pct": 18}]


def test_contract_many_items_across_pages():
    d = kmscl.parse_contract(layout("kmscl-rc-cardiac-set.txt"))[0][1]
    assert d["n_items"] == 43 and [i["sl"] for i in d["items"]] == list(range(1, 44)) and d["rate"] is None
    first, eighth = d["items"][0], d["items"][7]
    assert first["qty"] == 15 and first["rate"] == 14000 and first["make"] == "H191-150-05/Hermann Medizintechnik Gmbh"
    assert eighth["item"] == "MICS stabilizer with interchangeable tips- plastic" and eighth["gst_pct"] == 12
    glued = [p.replace("          plastic", "          plastic                     Item-wise Price Details", 1)
             for p in layout("kmscl-rc-cardiac-set.txt")]          # seen live: the next page's title on a wrapped cell's line
    assert kmscl.parse_contract(glued)[0][1]["items"][7]["item"] == "MICS stabilizer with interchangeable tips- plastic"
    cot = kmscl.parse_contract(layout("kmscl-rc-labour-cot.txt"))[0][1]
    assert [(i["item"], i["qty"], i["rate"]) for i in cot["items"]] == [("Multifunctional Labour Cot Type I", 186, 65637.5),
                                                                        ("Multifunctional Labour Cot Type II", 186, 62687.5)]
    reag = kmscl.parse_contract(layout("kmscl-rc-reagents.txt"))[0][1]
    assert reag["n_items"] == 27 and reag["items"][1]["item"] == "Urea U.V 4 x 30 / 2 x 16 mL" and reag["items"][1]["rate"] == 747.04


def test_contract_other_layout_gives_nothing():
    assert kmscl.parse_contract(["Letter of acceptance\nSome text"]) == []
    assert kmscl.parse_doc("u", b"<html>", "", [{"doc_kind": "contract"}]) == []
    assert kmscl.parse_doc("u", b"%PDF-1.4", "", [{"doc_kind": "no-bidder"}]) == []


def test_blacklist_firms():
    rows = kmscl.parse_blacklist_firms(layout("kmscl-blacklist-firms.txt"))
    assert [d["firm"] for _, d in rows] == ["Sangrose Laboratories Pvt. Ltd.", "Vysali Pharmaceuticals Ltd."]
    d = rows[1][1]
    assert d["kind"] == "blacklist" and d["list"] == "drug-firm" and not d["nsq"]
    assert (d["from"], d["to"], d["order_date"]) == ("2023-04-27", "2025-04-26", "2023-04-27")
    assert d["reference"] == "KMSCL/ED/I&II/293-VPL/2021 dt. 27.04.2023"
    assert d["reason"] == "Non-execution of Agreement & withdrawal from the tender"


def test_blacklist_nsq_products():
    rows = kmscl.parse_blacklist_nsq(layout("kmscl-blacklist-nsq.txt"))
    got = [(d["product"], d["firm"], d["tender_year"], d["to"]) for _, d in rows]
    assert got == [("Paracetamol Tab IP 500mg", "Healers Lab", "2023-24", "2028-07-30"),
                   ("Oseltamivir Cap IP 75mg", "Unicure India Limited", "2020-21", "2027-07-21"),
                   ("Isosorbide dinitrate Tab IP 10mg", "Unicure India Limited", "2023-24", "2027-07-19")]
    assert all(d["nsq"] and d["list"] == "drug-item" for _, d in rows)
    assert rows[1][1]["reference"] == "KMSCL/QC/13919/2022 dated 22.05.2026." and rows[1][1]["order_date"] == "2026-05-22"
    assert len({r for r, _ in rows}) == 3 and all(r.startswith("blacklist:drug-item:") for r, _ in rows)


def test_price_list():
    rows = kmscl.parse_price_list(layout("kmscl-price-list.txt"))
    assert len(rows) == 95 and len({r for r, _ in rows}) == 95
    d = rows[0][1]
    assert d == {"kind": "price", "sl": 1, "company": "3M INDIA LTD ( SURGICAL )", "product": "CREPE BANDAGE 15 CMX 4 MT(3M INDIA)",
                 "unit": "NUMBERS", "kcp_price": 188.48, "mrp": 330.0, "report_date": "2025-12-03"}
    glued = next(d for _, d in rows if d["sl"] == 6805)            # "... - EDNUMBERS": the unit is glued to the product name
    assert glued["unit"] == "NUMBERS" and glued["product"].endswith("KRITIKA - ED") and glued["mrp"] == 4.7


def test_project_is_a_proxy_pilot():
    p = next(p for p in family.PROJECTS if p["name"] == "medical-procurement-kmscl")
    keys = {i["key"] for i in p["items"]}
    assert len(keys) == len(p["items"]) == 2 + len(kmscl.DEPTS) + sum(n for _, n in corps.KL_DOCS.values())
    assert p["pilot"] <= keys and {i["key"] for i in family.queue(p)} == p["pilot"] and len(p["pilot"]) <= 5
    assert p["proxy"] == "IN" and p["threads"] == 1 and p["delay_ms"] >= 1000
    assert p["probe"] in {x["name"] for x in family.PROBES}
