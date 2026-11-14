"""Parsing tests on saved pages of www.wbmsc.gov.in (trimmed copies from 2026-11-14) and a Wayback CDX sample: no network."""
import json
from pathlib import Path

import docs
import family
import wayback_task
import wbmsc

PAGES = Path(__file__).parent / "pages"


def page(name):
    return (PAGES / name).read_text(encoding="utf-8")


def test_tender_listing_rows():
    rows = wbmsc.parse_listing(page("wbmsc-tender.html"), "tender")
    assert len(rows) == 55
    rid, first = rows[0]
    assert rid.startswith("tender:") and len(rid) == len("tender:") + 20
    assert first["title"].startswith("Procurement of 2 nos of Anesthesia workstation")
    assert first["number"] == "GEM/2026/B/8133982" and first["gem_bid"] == "GEM/2026/B/8133982"
    assert first["date"] == "2026-11-13" and first["date_raw"] == "Friday, November 13, 2026"
    assert first["url"] == "https://www.wbmsc.gov.in/tender/wbmsc-tender-8356.pdf" and first["file"] == "wbmsc-tender-8356.pdf"
    assert first["position"] == 1 and first["section"] == "tender"
    assert len({r for r, _ in rows}) == len(rows)


def test_oldest_rows_without_class_and_with_spaces_in_href():
    rows = wbmsc.parse_listing(page("wbmsc-tender.html"), "tender")
    last = rows[-1][1]
    assert last["number"] == "WBMSC/PMC/01/2011" and last["date"] == "2011-01-11"
    assert last["url"] == "https://www.wbmsc.gov.in/tender/pmc_01.pdf"


def test_row_id_is_stable_text_and_link():
    a = wbmsc.row_id("tender", "WBMSCL/NIT-41/2019", "Tuesday, June 18, 2019", "Amendment I")
    assert a == wbmsc.row_id("tender", "WBMSCL/NIT-41/2019 ", "Tuesday, June 18, 2019", "Amendment  I")
    assert a != wbmsc.row_id("tender", "WBMSCL/NIT-42/2019", "Tuesday, June 18, 2019", "Amendment I")
    # one tender, several rows with the same text, each with its own file (WBMSCL/NIT 850/2026 has five)
    assert a != wbmsc.row_id("tender", "WBMSCL/NIT-41/2019", "Tuesday, June 18, 2019", "Amendment I", "./tender/x-1.pdf")


def test_classify():
    c = wbmsc.classify("Amendment I: DATE EXTENSION OF OPHTHALMIC EQUIPMENT", "WBMSCL/NIT- 41/2019, Dated-04.06.2019")
    assert c["kind"] == "amendment" and c["nit"] == "WBMSCL/NIT-41/2019"
    assert wbmsc.classify("Urgent Requirement of Split AC", "WBMSCL/NIT-900/2026")["urgent"] is True
    assert wbmsc.classify("Supply of X", "WBMSCL/NIQ-128/2022 dated � 06/04/2022")["nit"] == "WBMSCL/NIQ-128/2022"
    assert wbmsc.classify("NEW AAES-781 Repair works", "Order # WBMSC/AAES-781")["aaes"] == 781
    assert wbmsc.classify("Cancellation of tender", "x")["kind"] == "cancellation"


def test_notice_and_award_listings():
    notices = wbmsc.parse_listing(page("wbmsc-notice.html"), "notice")
    assert len(notices) == 25 and all(d["url"].startswith("https://www.wbmsc.gov.in/notice/") for _, d in notices)
    awards = wbmsc.parse_listing(page("wbmsc-award-of-work.html"), "award")
    assert len(awards) == 3 and awards[1][1]["number"] == "WBMSC/PPP-SDH-Hosp/05/2011"


def test_doc_urls_groups_rows_by_url():
    rows = wbmsc.parse_listing(page("wbmsc-tender.html"), "tender")
    links = wbmsc.doc_urls(rows)
    assert sum(len(v) for v in links.values()) == sum(1 for _, d in rows if d["url"])
    assert all(u.startswith(wbmsc.SITE) for u in links)


def test_shards_cover_everything_once():
    keys = [f"https://www.wbmsc.gov.in/tender/wbmsc-tender-{n}.pdf" for n in range(500)]
    seen = [wbmsc.shard_of(k, 24) for k in keys]
    assert set(seen) == set(range(24))


def test_family_items():
    keys = [i["key"] for p in family.PROJECTS for i in p["items"]]
    assert len(keys) == len(set(keys)) and all(len(k) <= 200 for k in keys)
    wb = family.PROJECTS[0]["items"]
    assert wb[0]["payload"] == {"kind": "page", "page": "award-of-work.php", "round": family.ROUND, "expected": 4}
    assert sum(1 for i in wb if i["payload"]["kind"] == "docs") == 52


def test_docs_kind_and_not_found_page():
    assert docs.kind_of(b"%PDF-1.7 ...") == "pdf"
    assert docs.kind_of(b"PK\x03\x04....", name="a.docx") == "docx"
    nf = (PAGES / "wbmsc-award-of-work.html").read_bytes()[:0] + b"<html><title>Object not found!</title></html>"
    assert docs.kind_of(nf) == "html" and docs.is_not_found_page(nf)


def test_docs_uploads_puts_scans_under_ocr_needed():
    files, fields = docs.uploads({"sha256": "ab" * 32, "type": "pdf", "has_text": False}, b"%PDF-", "", "notice")
    assert files == [(f"ocr-needed/notice/{'ab' * 32}.pdf", b"%PDF-", "application/pdf")] and fields["ocr_needed"]
    files, fields = docs.uploads({"sha256": "cd" * 32, "type": "pdf", "has_text": True}, b"%PDF-", "x" * 300, "tender",
                                 prefix="wayback/")
    assert [f[0] for f in files] == [f"wayback/docs/tender/{'cd' * 32}.pdf", f"wayback/text/{'cd' * 32}.txt.gz"]
    assert fields["text_head"] == "x" * 300


def test_wayback_units():
    rows = json.loads((PAGES / "wayback-cdx.json").read_text())[1:]
    us = wayback_task.units([r + ["text/html"] for r in rows])
    assert ("wbmsc.gov.in/", "2BFAELDWCFBORS7TTBHXHJFAIDAMEKXP") in us
    assert wayback_task.norm_path("http://www.wbmsc.gov.in:80/tender/A.pdf?") == "wbmsc.gov.in/tender/A.pdf"
    assert wayback_task.section_of("wbmsc.gov.in/tender/A.pdf") == "tender"
    assert wayback_task.section_of("wbmsc.gov.in/tender.php") == "pages"
    assert not wayback_task.units([["2020", "http://www.wbmsc.gov.in/images/x.gif", "200", "D", "1", "image/gif"]])


def test_pilot_keys_exist():
    keys = {i["key"] for p in family.PROJECTS for i in p["items"]}
    assert family.PILOT_KEYS <= keys
    assert all(family.queue(p) for p in family.PROJECTS)
