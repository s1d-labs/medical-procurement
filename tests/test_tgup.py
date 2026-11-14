"""Parsing tests for TGMSIDC (Telangana) and UPMSCL (Uttar Pradesh) on saved pages and on the layout text of their PDFs
(2026-11-14; lists trimmed, header lines with phones and e-mails removed): no network."""
from pathlib import Path

import corps
import family
import pdftables as P
import tgmsidc
import upmscl

PAGES = Path(__file__).parent / "pages"


def page(name):
    return (PAGES / name).read_text(encoding="utf-8")


def layout(name):
    return page(name).split("\f")


def test_pdftables_chunks_and_rows():
    assert P.chunks("  1    Aceclofenac 100mg Tab   AML") == [(2, "1"), (7, "Aceclofenac 100mg Tab"), (31, "AML")]
    pages = ["  1   Name A        x\n      more A\n  2   Name B        y\n", "      end B\n"]
    rows = P.rows(pages, lambda ln: ln.strip()[:1].isdigit(), "below")
    assert rows == [["1", "Name A more A", "x"], ["2", "Name B end B", "y"]]


def test_tg_list_page():
    rows = tgmsidc.parse("drugs-wing", page("tgmsidc-drugs-wing.html"))
    kinds = {d["doc_kind"] for _, d in rows}
    assert len(rows) == 7 and {"rc-medicines", "rc-surgical", "blacklist-firms", "blacklist-products"} <= kinds
    assert all(d["url"].startswith("https://tgmsidc.telangana.gov.in/admin/files/") and "//admin" not in d["url"] for _, d in rows)
    assert len(tgmsidc.doc_urls(rows)) == 7


def test_tg_rate_contract_medicines():
    rows = tgmsidc.parse_rc(layout("tgmsidc-rc-medicines.txt"), "rc-medicines")
    first = rows[0][1]
    assert first["code"] == "2193" and first["name"] == "Aceclofenac 100mg Tab" and first["category"] == "AML"
    assert first["rate"] == 29.23 and first["unit"] == "100" and first["firm"] == "9M India Limited"
    assert first["tender_no"] == "16_2023" and first["valid_to"] == "2026-09-18" and first["contracted"]
    no_rc = next(d for _, d in rows if d["code"] == "2062")
    assert not no_rc["contracted"] and no_rc["rate"] is None and no_rc["category"] == "EML"
    allo = next(d for _, d in rows if d["code"] == "1734")        # "Tablets IP 100 mg" must not be read as category IP
    assert allo["category"] == "AML" and allo["rate"] == 76.92 and allo["firm"] == "Unicure India Pvt. Ltd."
    assert len({r for r, _ in rows}) == len(rows)


def test_tg_rate_contract_surgical():
    rows = tgmsidc.parse_rc(layout("tgmsidc-rc-surgical.txt"), "rc-surgical")
    d = next(d for _, d in rows if d["code"] == "7108")
    assert d["category"] == "GC" and d["rate"] == 12 and d["unit"] == "1Pack" and d["firm"] == "Unifranco Life Sciences Pvt Ltd"
    last = rows[-1][1]
    assert last["code"] == "6733" and last["firm"] == "Royal Agencies" and last["valid_to"] == "2027-02-04"   # no "14/14"


def test_tg_blacklists():
    firms = tgmsidc.parse_blacklist(layout("tgmsidc-blacklist-firms.txt"), "blacklist-firms")
    assert len(firms) == 11
    assert firms[0][1]["firm"] == "M/s Weismanna Health Care Pvt Ltd" and firms[0][1]["from"] == "2017-08-11"
    court = [d for _, d in firms if d["court_order"]]
    assert court and court[0]["firm"] == "M/s Suzikem Drugs Pvt Ltd"
    prods = tgmsidc.parse_blacklist(layout("tgmsidc-blacklist-products.txt"), "blacklist-products")
    p = next(d for _, d in prods if d["item"] and d["item"].startswith("IFA syrup"))
    assert p["firm"] == "M/s Medipol Pharmaceutical India Pvt Ltd" and p["item_codes"] == ["1713"] and p["till"] == "2020-07-31"
    assert all(d["firm"].lower().startswith("m/s") for _, d in prods)


def test_up_nsq_blacklist():
    rows = upmscl.parse("nsq", page("upmscl-nsq.html"))
    assert len(rows) == 4
    d = rows[0][1]
    assert d["firm"] == "SVP LIFESCIENCE" and d["drug"].startswith("GENTAMICIN SULPHATE") and d["nsq"] and d["years"] == 3
    assert d["date"] == "2026-10-15" and d["order_no"] == "UPMSCL/MD/QC/2026/739"
    assert d["orders"] == ["https://upmsc.in/NsqFiles/7133f018-3220-45b6-9239-0b5cf7e6e630_Office%20order%20SVP%20Gentamicin.pdf"]


def test_up_tenders_and_documents():
    rows = upmscl.parse("tenders", page("upmscl-tenders.html"))
    assert len(rows) == 6 and len({r for r, _ in rows}) == 6               # repeated rows keep their own ids
    t208 = [d for _, d in rows if "Drugs-208" in d["number"]]
    kinds = {f["kind"] for d in t208 for f in d["files"]}
    assert "rate-list" in kinds
    links = upmscl.doc_urls(rows)
    assert links and all("\\" not in u and " " not in u for u in links)
    assert not any(f["kind"] == "other" and f["url"] in links for _, d in rows for f in d["files"])


def test_up_rate_list():
    rows = upmscl.parse_rate_list(layout("upmscl-rate-list.txt"), "APPROVED ITEMS LIST ... UPMSCL/Drugs-208/052 (EDL drugs) Lot-1")
    assert rows and all(d["parsed"] for _, d in rows)
    d = rows[0][1]
    assert d["firm"] == "Abbott India Limited" and d["code"] == "D010006" and d["rate"] == 0.2499 and d["gst_pct"] == 12
    assert d["offered_qty"] == 35437500 and d["contract_value"] == 8855831 and d["rc_type"] == "Parallel" and d["rc_share_pct"] == 15
    assert d["tender"] == "UPMSCL/Drugs-208/052"
    main = [d for _, d in rows if d["rc_type"] == "Main"]
    assert main and all(d["rc_share_pct"] for d in main)


def test_up_parse_doc_only_rate_lists():
    rows = upmscl.parse("tenders", page("upmscl-tenders.html"))
    other = next(f for _, d in rows for f in d["files"] if f["kind"] != "rate-list")
    assert upmscl.parse_doc(other["url"], b"%PDF-1.4", "", [d for _, d in rows]) == []


def test_projects_and_pilots():
    names = {p["name"]: p for p in family.PROJECTS}
    for n in ("medical-procurement-tgmsidc", "medical-procurement-upmscl"):
        p = names[n]
        assert p["proxy"] in ("", "IN") and p["threads"] == 1 and p["delay_ms"] >= 1500
        q = {i["key"] for i in family.queue(p)}
        assert q and q <= {i["key"] for i in p["items"]}
    assert len({p["name"] for p in corps.projects("x", "r")}) == 6
