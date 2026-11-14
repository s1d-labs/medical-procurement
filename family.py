"""What this family scrapes: state medical services corporations' tenders, notices, documents and their old versions (P17, D04).

FAMILY equals the repo name (s1d-labs/medical-procurement). One project per site and per kind of work. After a change here, run the
Setup workflow (Actions -> setup). seed_queue keeps existing keys, so to fetch a site again (new tenders, changed documents) raise
ROUND: the new round's keys are new items, and the old round's records stay.

Who won WBMSC's tenders is NOT on www.wbmsc.gov.in (its award page has 3 notices from 2011). It is already in the hub:
  - e-tenders on wbtenders.gov.in: project gepnic-wbtenders (sarthak's gepnic family): bidders, bid status, winners;
  - GeM bids (GEM/<year>/B/<n>): the team's `gem` database (silver.tenders, silver.bid_evaluations).
This family stores what only the corporation's own site has, and joins the rest in analysis (ws_trideep).
"""
import json
from pathlib import Path

FAMILY = json.loads((Path(__file__).parent / "scrape.json").read_text())["family"]
ROUND = "2026-11"

WBMSC = "https://www.wbmsc.gov.in"
# documents linked from each listing on 2026-11-14, and the shards they are split into (about 110 documents per shard, ~15 minutes on a runner)
WBMSC_DOCS = {"award": (3, 1), "recruitment": (70, 1), "notice": (376, 2), "tender": (5259, 48)}
WBMSC_ROWS = {"award-of-work.php": 3, "recruitment-notice.php": 70, "notice.php": 384, "tender.php": 7276}
WBMSC_PAGES = ["award-of-work.php", "recruitment-notice.php", "notice.php", "tender.php",
               "index.php", "contact_us.php", "management.php", "organogram.php", "future-plan.php"]


def wbmsc_items():
    items = [{"key": f"{ROUND}/page/{p}", "payload": {"kind": "page", "page": p, "round": ROUND,
                                                      "expected": WBMSC_ROWS.get(p, 0) + 1}} for p in WBMSC_PAGES]
    for section, (n, shards) in WBMSC_DOCS.items():
        items += [{"key": f"{ROUND}/docs/{section}-{k:02d}-of-{shards}",
                   "payload": {"kind": "docs", "section": section, "shard": k, "shards": shards, "round": ROUND,
                               "expected": max(1, round(n / shards))}} for k in range(shards)]
    return items


WAYBACK_SHARDS = 24       # ~5,100 distinct archived contents of wbmsc.gov.in (CDX, 2026-11-14)

PROJECTS = [
    {
        "name": f"{FAMILY}-wbmsc",
        "title": "WBMSC (West Bengal Medical Services Corporation): tenders, notices, documents",
        "task": "wbmsc",
        "target": "www.wbmsc.gov.in",
        "env": {"SITE": WBMSC},
        "probe": f"{FAMILY}:www.wbmsc.gov.in",
        "unit_label": "page or document shard", "record_label": "row or document",
        "threads": 1, "delay_ms": 1000, "max_workers": 4,
        "proxy": "",          # direct: GitHub's runners reached the site (check workflow, 2026-11-14, 1.2 s per request)
        "items": wbmsc_items(),
    },
    {
        "name": f"{FAMILY}-wbmsc-wayback",
        "title": "WBMSC: old versions of pages and documents from the Wayback Machine",
        "task": "wayback",
        "target": "web.archive.org",
        "env": {},
        "probe": f"{FAMILY}:web.archive.org",
        "unit_label": "capture shard", "record_label": "archived content",
        "threads": 1, "delay_ms": 1500, "max_workers": 2,
        "proxy": "",
        "items": [{"key": f"wbmsc/{k:02d}-of-{WAYBACK_SHARDS}",
                   "payload": {"prefix": "wbmsc.gov.in/*", "site": "wbmsc", "shard": k, "shards": WAYBACK_SHARDS, "expected": 210}}
                  for k in range(WAYBACK_SHARDS)],
    },
]

# First pool run (scraper guide): seed only these items, watch scrape.s1d.me -> Runs, then set PILOT = False and run Setup again.
PILOT = True
PILOT_KEYS = {f"{ROUND}/page/tender.php", f"{ROUND}/page/notice.php", f"{ROUND}/docs/award-00-of-1", f"{ROUND}/docs/tender-00-of-48",
              "wbmsc/00-of-24", "wbmsc/01-of-24"}


def queue(project):
    """The items Setup seeds for a project now (all of them, or the pilot ones)."""
    return [i for i in project["items"] if not PILOT or i["key"] in PILOT_KEYS]


# health checks the hub runs every minute; a project's work holds while its probe fails. Light pages only.
PROBES = [
    {"name": f"{FAMILY}:www.wbmsc.gov.in", "url": f"{WBMSC}/award-of-work.php", "expect": "West Bengal Medical Services Corporation"},
    {"name": f"{FAMILY}:web.archive.org", "url": "https://web.archive.org/", "expect": "Wayback Machine"},
]
