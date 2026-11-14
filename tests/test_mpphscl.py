"""Parsing tests on saved pages of mpphscl.mp.gov.in (trimmed copies from 2026-11-14: first and last rows of each list): no network."""
from pathlib import Path

import family
import mpphscl

PAGES = Path(__file__).parent / "pages"


def page(name):
    return (PAGES / name).read_text(encoding="utf-8")


def test_tender_rows_and_documents():
    rows = mpphscl.parse_tenders(page("mpphscl-tenderall.html"))
    assert len(rows) == 15 and len({r for r, _ in rows}) == 15
    rid, first = rows[0]
    assert rid.startswith("tender:T-963:") and first["number"] == "T-963"
    assert first["start"] == "2026-10-16" and first["close"] == "2026-10-28" and first["category"] == "Consumables"
    assert first["n_documents"] == 10 and first["documents"][0]["kind"] == "tender_document"
    assert first["documents"][0]["url"] == "https://mpphscl.mp.gov.in/Files/PDF/16102026095320TenderDocumentT963.pdf"
    kinds = [d["kind"] for d in first["documents"]]
    assert "comparative" in kinds and "financial_opening" in kinds and "technical_opening" in kinds
    # spaces in file names are escaped
    assert all(" " not in d["url"] for _, r in rows for d in r["documents"])
    assert rows[-1][1]["number"] == "NIT-045" and rows[-1][1]["start"] == "2015-09-24"


def test_tender_id_stable():
    a = mpphscl.parse_tenders(page("mpphscl-tenderall.html"))
    b = mpphscl.parse_tenders(page("mpphscl-tenderall.html").replace("<td>1</td>", "<td>99</td>", 1))
    assert [r for r, _ in a] == [r for r, _ in b]          # the serial number moves when new tenders arrive; the id does not


def test_doc_kind():
    assert mpphscl.doc_kind("Item wise Comparative Statement") == "comparative"
    assert mpphscl.doc_kind("Approved Rate List") == "rate_list"
    assert mpphscl.doc_kind("Final Status") == "final_status"
    assert mpphscl.doc_kind("Notice for Financial Opening") == "financial_opening"
    assert mpphscl.doc_kind("Technical Bid Opening Detail") == "technical_opening"
    assert mpphscl.doc_kind("Notice for Tender Cancellation") == "cancellation"
    assert mpphscl.doc_kind("Something else") == "other"


def test_blacklist_firm():
    rows = mpphscl.parse_blacklist(page("mpphscl-blacklistfirm.html"), "firm")
    assert len(rows) == 10 and all(r.startswith("blacklist-firm:") for r, _ in rows)
    d = rows[1][1]
    assert d["from"] == "2026-08-31" and d["upto"] == "2028-08-30" and d["quality_failure"] and d["court_stay"]
    assert [x["kind"] for x in d["documents"]] == ["order", "court"]
    assert rows[0][1]["product"] is None and rows[0][1]["remark"] == "Debarred on forgery grounds"


def test_blacklist_product_and_lab():
    rows = mpphscl.parse_blacklist(page("mpphscl-blacklistproduct.html"), "product")
    assert len(rows) == 10
    first, second = rows[0][1], rows[1][1]
    assert first["non_supply"] and not first["quality_failure"] and first["product"].startswith("Albendazole")
    assert second["item_code"] == "120655" and second["quality_failure"]
    assert all(" " not in x["url"] for _, r in rows for x in r["documents"])
    labs = mpphscl.parse_blacklist(page("mpphscl-blacklistlabs.html"), "lab")
    assert len(labs) == 2 and labs[1][1]["upto"] == "2024-07-11"


def test_doc_urls_and_shards():
    rows = mpphscl.parse_tenders(page("mpphscl-tenderall.html"))
    links = mpphscl.doc_urls(rows)
    assert len(links) == sum(r["n_documents"] for _, r in rows)
    assert {mpphscl.shard_of(u, 4) for u in links} == {0, 1, 2, 3}
    assert mpphscl.gepnic_ids("Tender ID 2026_PHSCL_543877_1 and 2026_PHSCL_543877_1") == ["2026_PHSCL_543877_1"]


def test_family_mp_items_and_pilot():
    mp = next(p for p in family.PROJECTS if p["name"] == f"{family.FAMILY}-mpphscl")
    keys = [i["key"] for i in mp["items"]]
    assert len(keys) == len(set(keys)) and all(len(k) <= 200 for k in keys)
    assert sum(1 for i in mp["items"] if i["payload"]["kind"] == "page") == 4
    assert mp["threads"] == 1 and mp["delay_ms"] >= 1000 and mp["max_workers"] <= 2
    q = family.queue(mp)
    assert q and (not family.MP_PILOT or {i["key"] for i in q} == family.MP_PILOT_KEYS)
    assert family.MP_PILOT_KEYS <= set(keys)
