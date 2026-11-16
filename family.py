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
import os
from pathlib import Path

import corps

FAMILY = json.loads((Path(__file__).parent / "scrape.json").read_text())["family"]
ROUND = os.environ.get("ROUND") or "2026-11"   # the weekly setup run sets ROUND=<ISO week>
SINCE = os.environ.get("SINCE")                 # HTTP date of the previous round: document items skip files not changed since

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


MPPHSCL = "https://mpphscl.mp.gov.in"
# documents linked on 2026-11-14 and their shards (about 110 per shard): tender list 13,321; the three blacklists 378
MP_DOCS = {"blacklist": (378, 4), "tender": (13321, 120)}
MP_ROWS = {"TenderALL.aspx": 1187, "BlackListFirm.aspx": 140, "BlackListProduct.aspx": 236, "BlackListLabs.aspx": 2}


def mpphscl_items():
    items = [{"key": f"{ROUND}/page/{p}", "payload": {"kind": "page", "page": p, "round": ROUND, "expected": n + 1}}
             for p, n in MP_ROWS.items()]
    for group, (n, shards) in MP_DOCS.items():
        items += [{"key": f"{ROUND}/docs/{group}-{k:03d}-of-{shards}",
                   "payload": {"kind": "docs", "group": group, "shard": k, "shards": shards, "round": ROUND,
                               "expected": max(1, round(n / shards))}} for k in range(shards)]
    return items


WAYBACK_SHARDS = 24       # ~5,100 distinct archived contents of wbmsc.gov.in (CDX, 2026-11-14)
# Shards that ran past the 60-minute assignment again and again (15 Nov). Each is split in 3: shard k of 24 is shards k,
# k+24, k+48 of 72 (the same hash). The task completes the old key at once; the three small keys do the work.
WAYBACK_SPLIT = (2, 4, 11, 21)

PROJECTS = [
    {
        "name": f"{FAMILY}-wbmsc",
        "title": "WBMSC (West Bengal Medical Services Corporation): tenders, notices, documents",
        "task": "wbmsc",
        "target": "www.wbmsc.gov.in",
        "env": {"SITE": WBMSC},
        # no health check while the site's certificate is expired (15 Nov 2026): the hub's probe refuses it and would hold
        # the work. The task accepts it (taskrun.EXPIRED_CERT_HOSTS). Put the probe back when the site renews the certificate.
        "probe": None,
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
        "threads": 1, "delay_ms": 1500, "max_workers": 1,   # 1: leaves a web.archive.org slot to ppp-india-wayback
        "proxy": "",
        "items": [{"key": f"wbmsc/{k:02d}-of-{WAYBACK_SHARDS}",
                   "payload": {"prefix": "wbmsc.gov.in/*", "site": "wbmsc", "shard": k, "shards": WAYBACK_SHARDS, "expected": 210}}
                  for k in range(WAYBACK_SHARDS)] +
                 [{"key": f"wbmsc/{j:02d}-of-{3 * WAYBACK_SHARDS}",
                   "payload": {"prefix": "wbmsc.gov.in/*", "site": "wbmsc", "shard": j, "shards": 3 * WAYBACK_SHARDS, "expected": 70}}
                  for k in WAYBACK_SPLIT for j in (k, k + WAYBACK_SHARDS, k + 2 * WAYBACK_SHARDS)],
    },
    {
        "name": f"{FAMILY}-mpphscl",
        "title": "MPPHSCL (Madhya Pradesh Public Health Services Corporation): tenders, documents, blacklists",
        "task": "mpphscl",
        "target": "mpphscl.mp.gov.in",
        "env": {"SITE": MPPHSCL},
        # no health check: the server needs legacy TLS renegotiation, which a standard probe client refuses, so a probe would
        # report the site down and hold the work. The task fails its items when the site does not answer.
        "probe": None,
        "unit_label": "page or document shard", "record_label": "tender, blacklist entry or document",
        "threads": 1, "delay_ms": 1500, "max_workers": 2,
        # India only: GitHub's runners got no answer (check workflow, 2026-11-14: both items timed out); the box in Mumbai and an
        # Indian proxy reached it. The task's TLS context also works through HTTPS_PROXY.
        "proxy": "IN",
        "pool": False,        # out of the pool: the site answers 403 / nothing since 14 Nov; set True again when it answers
        "items": mpphscl_items(),
    },
]

PROJECTS += corps.projects(FAMILY, ROUND)       # TNMSC and RMSC (corp_task.py)

# First pool run (scraper guide): seed only these items, watch scrape.s1d.me -> Runs, then set the flag to False and run Setup
# again. Each site has its own flag, so one site can leave its pilot while another stays in it.
PILOT = False   # pilot of 2026-11-14 passed: rows, documents, missing links and Wayback records looked right
PILOT_KEYS = {f"{ROUND}/page/tender.php", f"{ROUND}/page/notice.php", f"{ROUND}/docs/award-00-of-1", f"{ROUND}/docs/tender-00-of-48",
              "wbmsc/00-of-24", "wbmsc/01-of-24"}


MP_PILOT = True
MP_PILOT_KEYS = {f"{ROUND}/page/TenderALL.aspx", f"{ROUND}/page/BlackListFirm.aspx", f"{ROUND}/page/BlackListProduct.aspx",
                 f"{ROUND}/docs/blacklist-000-of-4", f"{ROUND}/docs/tender-000-of-120"}


def pilot_keys(project):
    """The pilot keys of a project while its pilot is on, else None (seed everything). TNMSC and RMSC keep theirs in the
    project itself ("pilot" in corps.py)."""
    if "pilot" in project:
        return project["pilot"]
    if project["name"].endswith("-mpphscl"):
        return MP_PILOT_KEYS if MP_PILOT else None
    return PILOT_KEYS if PILOT else None


def queue(project):
    """The items Setup seeds for a project now (all of them, or the pilot ones)."""
    keys = pilot_keys(project)
    items = [i for i in project["items"] if keys is None or i["key"] in keys]
    if SINCE:
        items = [{**i, "payload": {**i["payload"], "since": SINCE}} if i["payload"].get("kind") == "docs" else i for i in items]
    return items


# health checks the hub runs every minute; a project's work holds while its probe fails. Light pages only.
PROBES = [
    {"name": f"{FAMILY}:web.archive.org", "url": "https://web.archive.org/", "expect": "Wayback Machine"},
] + corps.probes(FAMILY)
