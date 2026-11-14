"""Projects of the corporations served by corp_task.py: TNMSC (Tamil Nadu) and RMSC (Rajasthan). family.py adds them to PROJECTS.

Each project has its own pilot list ("pilot"): while it is a set, Setup seeds only those keys. Set it to None after the first pool
run looks right on scrape.s1d.me -> Runs, then run Setup again.
"""
import rmsc
import tnmsc
from htmltables import page_name

# rows and documents seen on 2026-11-14 (progress and ETAs only)
TN_ROWS = {"blacklist": 93, "awards": 28, "notifications": 40, "drugrc": 560, "equipmentrc": 200}
TN_DOCS = {"awards": (191, 2), "notifications": (150, 2)}
RJ_ROWS = {"drugrc": 2070, "banned-company": 8, "banned-product": 101, "drug-tenders": 1368, "equipment-tenders": 2588,
           "finance-tenders": 148}
RJ_DOCS = {"bans": (118, 2), "drug-tenders": (1356, 14), "equipment-tenders": (2565, 26), "finance-tenders": (146, 2)}


def _items(site, mod, rows, docs_, rnd):
    items = [{"key": f"{rnd}/page/{page_name(p, a)}",
              "payload": {"kind": "page", "site": site, "page": p, "arg": a, "round": rnd, "expected": rows.get(p, 1) + 1}}
             for p, a in mod.PAGES]
    for group, (n, shards) in docs_.items():
        items += [{"key": f"{rnd}/docs/{group}-{k:02d}-of-{shards}",
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
    ]


def probes(family):
    return [
        {"name": f"{family}:tnmsc.tn.gov.in", "url": tnmsc.url_of("notifications", 2027),
         "expect": "Tamil Nadu Medical Services Corporation"},
        {"name": f"{family}:rmsc.health.rajasthan.gov.in", "url": f"{rmsc.BASE}/home.html",
         "expect": "Rajasthan Medical Services Corporation"},
    ]
