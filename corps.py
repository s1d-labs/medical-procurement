"""Projects of the corporations served by corp_task.py: TNMSC (Tamil Nadu), RMSC (Rajasthan), HMSCL (Haryana), BMSICL (Bihar),
TGMSIDC (Telangana) and UPMSCL (Uttar Pradesh). family.py adds them to PROJECTS.

Each project has its own pilot list ("pilot"): while it is a set, Setup seeds only those keys. Set it to None after the first pool
run looks right on scrape.s1d.me -> Runs, then run Setup again.
"""
import bmsicl
import hmscl
import rmsc
import tgmsidc
import tnmsc
import upmscl
from htmltables import page_name

# rows and documents seen on 2026-11-14 (progress and ETAs only)
TN_ROWS = {"blacklist": 93, "awards": 28, "notifications": 40, "drugrc": 560, "equipmentrc": 200}
TN_DOCS = {"awards": (191, 2), "notifications": (150, 2)}
RJ_ROWS = {"drugrc": 2070, "banned-company": 8, "banned-product": 101, "drug-tenders": 1368, "equipment-tenders": 2588,
           "finance-tenders": 148}
RJ_DOCS = {"bans": (118, 2), "drug-tenders": (1356, 14), "equipment-tenders": (2565, 26), "finance-tenders": (146, 2)}
HR_ROWS = {"drugrc": 428, "equipmentrc": 58, "banned": 6}
HR_DOCS = {"orders": (6, 1)}
BR_ROWS = {"home": 4, "rc-status": 2, "equipment-blacklist": 4, "blacklist": 10}
BR_DOCS = {"rc": (6, 1), "orders": (87, 2)}         # rc: 6 rate contract files (about 1,600 rows); orders: 87 blacklist posts
# Telangana: one list page of 7 PDFs; the rate contract and blacklist PDFs give ~1,040 rows (522 medicines, 446 surgical items,
# 11 firms, 57 products). Uttar Pradesh: 41 NSQ blacklist rows, 858 tender rows; 535 documents (41 order scans, 494 results).
TG_ROWS = {"drugs-wing": 7}
TG_DOCS = {"lists": (7 + 1036, 1)}
UP_ROWS = {"nsq": 41, "tenders": 858}
UP_DOCS = {"nsq-orders": (41, 1), "results": (494, 5)}


# 2026-11-14: neither site answered GitHub's runners (check workflow: no answer in 40 s). HMSCL answers through the Indian
# proxies (myproxy scrape-check passed). BMSICL refused in-05 (191.219.x, 6 tries) and in-07 (91.124.42.x) but answered 3 of
# 3 other tries whose label was not shown, most likely 95.134.119.x (in-08 .. in-10): the pilot checks this.
HMSCL_PROXY = "IN"
BMSICL_PROXY = "IN"
BMSICL_PROXY_ONLY = ["95.134.119."]


def _items(site, mod, rows, docs_, rnd, prefix=""):
    """Queue items; `prefix` keeps keys unique across projects for sites added later (TNMSC and RMSC keys have none)."""
    items = [{"key": f"{rnd}/{prefix}page/{page_name(p, a)}",
              "payload": {"kind": "page", "site": site, "page": p, "arg": a, "round": rnd, "expected": rows.get(p, 1) + 1}}
             for p, a in mod.PAGES]
    for group, (n, shards) in docs_.items():
        items += [{"key": f"{rnd}/{prefix}docs/{group}-{k:02d}-of-{shards}",
                   "payload": {"kind": "docs", "site": site, "group": group, "shard": k, "shards": shards, "round": rnd,
                               "expected": max(1, round(n / shards))}} for k in range(shards)]
    return items


def projects(family, rnd):
    return [
        {
            "name": f"{family}-tnmsc",
            "title": "TNMSC (Tamil Nadu Medical Services Corporation): blacklists, rate contracts, contracts awarded, notifications",
            "task": "tnmsc",
            "target": "tnmsc.tn.gov.in",
            "env": {"SITE": tnmsc.SITE},
            "probe": f"{family}:tnmsc.tn.gov.in",
            "unit_label": "page or document shard", "record_label": "row or document",
            "threads": 1, "delay_ms": 1500, "max_workers": 2,
            "proxy": "IN",        # the site did not answer GitHub's runners (check workflow, 2026-11-14); it answers from India
            "items": _items("tnmsc", tnmsc, TN_ROWS, TN_DOCS, rnd),
            "pilot": None,        # pilot of 2026-11-14 passed: 93 blacklist entries, 552 RC rows, 488 bid rows, award PDFs
        },
        {
            "name": f"{family}-rmsc",
            "title": "RMSC (Rajasthan Medical Services Corporation): drug rate contracts, ban lists, tenders",
            "task": "rmsc",
            "target": "rmsc.health.rajasthan.gov.in",
            "env": {"SITE": rmsc.SITE},
            "probe": f"{family}:rmsc.health.rajasthan.gov.in",
            "unit_label": "page or document shard", "record_label": "row or document",
            "threads": 1, "delay_ms": 1500, "max_workers": 2,
            "proxy": "IN",        # the site did not answer GitHub's runners (check workflow, 2026-11-14); it answers from India
            "items": _items("rmsc", rmsc, RJ_ROWS, RJ_DOCS, rnd),
            "pilot": None,        # pilot of 2026-11-14 passed: 2,070 RC rows, 109 ban entries, 65 documents; site answers 304
        },
        {
            "name": f"{family}-hmscl",
            "title": "HMSCL (Haryana Medical Services Corporation): drug and equipment rate contracts, banned firms",
            "task": "hmscl",
            "target": "hmscl.org.in",
            "env": {"SITE": hmscl.SITE},
            "probe": f"{family}:hmscl.org.in",
            "unit_label": "page or document shard", "record_label": "row or document",
            "threads": 1, "delay_ms": 1500, "max_workers": 1,
            "proxy": HMSCL_PROXY,
            "items": _items("hmscl", hmscl, HR_ROWS, HR_DOCS, rnd, "hmscl/"),
            "pilot": None,        # pilot of 2026-11-15 passed: 428 drug RCs, 6 bans, 6 order PDFs
        },
        {
            "name": f"{family}-bmsicl",
            "title": "BMSICL (Bihar Medical Services and Infrastructure Corporation): rate contract files, blacklist orders",
            "task": "bmsicl",
            "target": "bmsicl.gov.in",
            "env": {"SITE": bmsicl.SITE},
            "probe": f"{family}:bmsicl.gov.in",
            "unit_label": "page or document shard", "record_label": "row or document",
            "threads": 1, "delay_ms": 2000, "max_workers": 1,
            "proxy": BMSICL_PROXY, "proxy_only": BMSICL_PROXY_ONLY,
            "pool": False,        # out of the pool: 40 tries through proxies, "page did not load" (2026-11-15); the box reaches it
            "items": _items("bmsicl", bmsicl, BR_ROWS, BR_DOCS, rnd, "bmsicl/"),
            "pilot": {f"{rnd}/bmsicl/page/blacklist-1", f"{rnd}/bmsicl/page/rc-status", f"{rnd}/bmsicl/docs/rc-00-of-1"},
        },
        {
            "name": f"{family}-tgmsidc",
            "title": "TGMSIDC (Telangana Medical Services & Infrastructure Development Corporation): rate contracts, blacklists",
            "task": "tgmsidc",
            "target": "tgmsidc.telangana.gov.in",
            "env": {"SITE": tgmsidc.SITE},
            "probe": f"{family}:tgmsidc.telangana.gov.in",
            "unit_label": "page or document shard", "record_label": "row or document",
            "threads": 1, "delay_ms": 1500, "max_workers": 1,
            "proxy": "",          # direct: GitHub's runners got HTTP 200 in 2.4 s and scrape-check passed (check workflow, 2026-11-14)
            "items": _items("tgmsidc", tgmsidc, TG_ROWS, TG_DOCS, rnd),
            "pilot": None,        # pilot of 2026-11-15 passed: 522 medicine RCs, 446 surgical RCs, 57 product blacklist rows
        },
        {
            "name": f"{family}-upmscl",
            "title": "UPMSCL (Uttar Pradesh Medical Supplies Corporation): NSQ blacklist, tenders, results and rate lists",
            "task": "upmscl",
            "target": "upmsc.in",
            "env": {"SITE": upmscl.SITE},
            "probe": f"{family}:upmsc.in",
            "unit_label": "page or document shard", "record_label": "row or document",
            "threads": 1, "delay_ms": 1500, "max_workers": 2,
            # GitHub's runners got no answer in 30 s (check workflow, 2026-11-14). The team box (Indian IP) gets HTTP 200, but the
            # proxy in-07 (91.124.42.x) gets "CONNECT 504": lend only the other two ranges (not tested yet; see Runs after setup).
            "proxy": "IN", "proxy_only": ["191.219.", "95.134.119."],
            "pool": False,        # out of the pool: 40 tries through proxies, "page did not load" (2026-11-15); the box reaches it
            "items": _items("upmscl", upmscl, UP_ROWS, UP_DOCS, rnd),
            "pilot": {f"{rnd}/page/nsq", f"{rnd}/page/tenders", f"{rnd}/docs/nsq-orders-00-of-1", f"{rnd}/docs/results-00-of-5"},
        },
    ]


def probes(family):
    return [
        {"name": f"{family}:tnmsc.tn.gov.in", "url": tnmsc.url_of("notifications", 2027),
         "expect": "Tamil Nadu Medical Services Corporation"},
        {"name": f"{family}:rmsc.health.rajasthan.gov.in", "url": f"{rmsc.BASE}/home.html",
         "expect": "Rajasthan Medical Services Corporation"},
        {"name": f"{family}:hmscl.org.in", "url": hmscl.url_of("banned"), "expect": "Haryana Medical Services Corporation"},
        {"name": f"{family}:bmsicl.gov.in", "url": bmsicl.page_url("rc-status"), "expect": "BMSICL"},
        {"name": f"{family}:tgmsidc.telangana.gov.in", "url": tgmsidc.page_url("drugs-wing"), "expect": "Rate Contract"},
        {"name": f"{family}:upmsc.in", "url": upmscl.page_url("nsq"), "expect": "Blacklist"},
    ]
