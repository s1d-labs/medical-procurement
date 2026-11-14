"""Projects of the corporations served by corp_task.py: TNMSC (Tamil Nadu), RMSC (Rajasthan), HMSCL (Haryana) and BMSICL (Bihar).
family.py adds them to PROJECTS.

Each project has its own pilot list ("pilot"): while it is a set, Setup seeds only those keys. Set it to None after the first pool
run looks right on scrape.s1d.me -> Runs, then run Setup again.
"""
import bmsicl
import hmscl
import rmsc
import tnmsc
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
            "pilot": {f"{rnd}/page/drugrc", f"{rnd}/page/banned-product", f"{rnd}/page/banned-company", f"{rnd}/docs/bans-00-of-2"},
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
            "pilot": {f"{rnd}/hmscl/page/drugrc", f"{rnd}/hmscl/page/banned", f"{rnd}/hmscl/docs/orders-00-of-1"},
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
            "items": _items("bmsicl", bmsicl, BR_ROWS, BR_DOCS, rnd, "bmsicl/"),
            "pilot": {f"{rnd}/bmsicl/page/blacklist-1", f"{rnd}/bmsicl/page/rc-status", f"{rnd}/bmsicl/docs/rc-00-of-1"},
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
    ]
