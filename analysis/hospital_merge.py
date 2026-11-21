"""Merge duplicate registry entries of one hospital and pick the active one (ABDM HFR + HPR doctors).

One hospital often has several HFR IDs (SSKM 3, Deben Mahata MCH 4, Diamond Harbour MCH 3: the college, the hospital, an
old building, a second campus). Two IDs are the same campus when they are within RADIUS_KM of each other (HFR coordinates)
and their names share a distinctive word after hospital_link.norm (abbreviations and spellings resolved: "IPGMER-SSKM" =
"IPGMER and SSKM Hospital"). The canonical ID of a group is the one with the most doctors in the national doctor registry
(HPR workplace IDs), then the most tender links, then the most beds: an ID with no doctors is usually a stub or an old entry.

Inputs (CSV, no header), made with COPY ... TO STDOUT WITH CSV:
  fac.csv   ws_om abdm_hfr_india_facilities, ownership G/PP: hfr_id, hospital, facility_type, state, district, pincode, lat, lon, beds
  doc.csv   ws_om abdm_hpr_doctors_collected: workplace_hfr_ids, count(distinct hpr_id)
  links.csv ws_trideep medproc.tender_hospital: hfr_id, links
  cand.csv  ws_om medproc_missing_hospital_candidates: corp, name_word, tender_mentions, hfr_id, facility_name, evidence
Outputs: master.csv (group, canonical, hfr_id, name, type, state, pincode, km_to_canonical, doctors, beds, links) and
resolution.csv (one row per (corp, name_word) of Om's candidate list: decision, suggested hfr_id, reason).
Usage: python3 analysis/hospital_merge.py DIR   (reads and writes the CSVs in DIR)
"""
import csv
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hospital_link import KEYTYPES, content, norm  # noqa: E402

RADIUS_KM = 1.0
TYPES_OK = {"Hospital", "Medical College"}       # sub-centres, dispensaries, pharmacies, blood banks are other places
GENERIC = {"nagar", "bazar", "road", "ward", "town", "city", "hq", "headquarter", "unit", "block", "nhm", "ayush"}
MARKERS = {"nikshay", "mental", "tb", "nursing", "esi", "esic", "railway", "school", "blood", "dental", "eye", "cancer", "maternity"}


def km(a, b):
    """Great-circle distance in km between (lat, lon) pairs."""
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def level(name):
    """Hospital level words of a name: {'super'} for an SSH, {'divisional'} for an SDH, {'medical'} for a college."""
    return set(norm(name)) & KEYTYPES - {"state", "general"}


def same_campus(f, g):
    """Same place, same kind of hospital, same level, and a shared distinctive name word ("Mal SSH" != "Mal SDH")."""
    if not (f["xy"] and g["xy"] and f["state"] == g["state"] and {f["type"], g["type"]} <= TYPES_OK):
        return False
    lf, lg = level(f["name"]), level(g["name"])
    cf, cg = content(norm(f["name"])) - GENERIC, content(norm(g["name"])) - GENERIC
    mf, mg = set(norm(f["name"])) & MARKERS, set(norm(g["name"])) & MARKERS
    # one name's distinctive words inside the other's ("walsh" in "serampore walsh"), not just a shared town name
    return (km(f["xy"], g["xy"]) <= RADIUS_KM and (lf == lg or not lf or not lg) and mf == mg
            and bool(cf) and bool(cg) and (cf <= cg or cg <= cf))


def load(d):
    fac = {}
    for r in csv.reader(open(f"{d}/fac.csv", encoding="utf-8")):
        hid, name, typ, state, dist, pin, lat, lon, beds = r
        try:
            xy = (float(lat), float(lon)) if lat and lon and abs(float(lat)) > 1 else None
        except ValueError:
            xy = None
        fac[hid] = {"id": hid, "name": name, "type": typ, "state": state, "pin": pin, "xy": xy,
                    "beds": int(beds) if beds.isdigit() else 0}
    doc = {r[0]: int(r[1]) for r in csv.reader(open(f"{d}/doc.csv"))}
    links = {r[0]: int(r[1]) for r in csv.reader(open(f"{d}/links.csv"))}
    cand = list(csv.reader(open(f"{d}/cand.csv", encoding="utf-8")))
    return fac, doc, links, cand


def groups(seeds, fac):
    """Union-find over the seeds and their same-campus neighbours (grid of 0.02 degrees, about 2 km)."""
    cell = defaultdict(list)
    for f in fac.values():
        if f["xy"]:
            cell[(round(f["xy"][0] / 0.02), round(f["xy"][1] / 0.02))].append(f["id"])
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for s in seeds:
        f = fac.get(s)
        find(s)
        if not f or not f["xy"]:
            continue
        cx, cy = round(f["xy"][0] / 0.02), round(f["xy"][1] / 0.02)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for n in cell[(cx + dx, cy + dy)]:
                    if n != s and same_campus(f, fac[n]):
                        parent[find(n)] = find(s)
    out = defaultdict(list)
    for x in parent:
        out[find(x)].append(x)
    return list(out.values())


def canonical(ids, fac, doc, links):
    return max(ids, key=lambda i: (doc.get(i, 0), links.get(i, 0), fac.get(i, {}).get("beds", 0), i))


def resolve(cand, gid_of, canon_of, doc):
    """Om's candidate list -> one decision per (corp, name_word)."""
    by = defaultdict(list)
    for corp, word, mentions, hid, name, ev in cand:
        by[(corp, word, mentions)].append((hid, name))
    out = []
    for (corp, word, mentions), cs in sorted(by.items()):
        gids = {gid_of.get(h, h) for h, _ in cs}
        ranked = sorted(cs, key=lambda c: -doc.get(c[0], 0))
        top, second = doc.get(ranked[0][0], 0), (doc.get(ranked[1][0], 0) if len(ranked) > 1 else 0)
        if len(cs) == 1:
            best = ranked[0][0]
            dec, why = ("single, active" if top else "single, no doctors"), f"one candidate ID; {top} doctors in HPR"
        elif len(gids) == 1:
            best = canon_of[gid_of.get(ranked[0][0], ranked[0][0])]
            dec, why = "one campus", f"{len(cs)} candidate ID(s) are one campus; canonical by doctors"
        elif top >= 5 and top >= 3 * second:
            best, dec, why = ranked[0][0], "suggest", f"{top} doctors vs {second} at the next candidate"
        else:
            best, dec, why = "", "open", "candidates are different places with similar doctor counts"
        out.append([corp, word, mentions, dec, best, why, ";".join(f"{h}:{doc.get(h, 0)}" for h, _ in ranked)])
    return out


def main(d):
    fac, doc, links, cand = load(d)
    seeds = set(links) | {r[3] for r in cand}
    gs = groups(seeds, fac)
    gid_of, canon_of, rows = {}, {}, []
    for n, ids in enumerate(sorted(gs, key=lambda g: sorted(g)[0]), 1):
        c = canonical(ids, fac, doc, links)
        for i in ids:
            gid_of[i] = n
        canon_of[n] = c
        for i in sorted(ids):
            f = fac.get(i, {"name": "", "type": "", "state": "", "pin": "", "xy": None, "beds": 0})
            dist = round(km(f["xy"], fac[c]["xy"]), 2) if f["xy"] and c in fac and fac[c]["xy"] else ""
            rows.append([n, c, i, f["name"], f["type"], f["state"], f["pin"], dist, doc.get(i, 0), f["beds"], links.get(i, 0)])
    with open(f"{d}/master.csv", "w", newline="", encoding="utf-8") as o:
        w = csv.writer(o)
        w.writerow(["grp", "canonical", "hfr_id", "name", "type", "state", "pincode", "km_to_canonical", "doctors", "beds", "links"])
        w.writerows(rows)
    res = resolve(cand, gid_of, canon_of, doc)
    with open(f"{d}/resolution.csv", "w", newline="", encoding="utf-8") as o:
        w = csv.writer(o)
        w.writerow(["corp", "name_word", "tender_mentions", "decision", "hfr_id", "reason", "candidates_doctors"])
        w.writerows(res)
    multi = sum(1 for g in gs if len(g) > 1)
    moved = sum(1 for i in links if canon_of[gid_of[i]] != i)
    print(f"{len(gs)} groups, {multi} with 2+ IDs; {moved} linked IDs are not the canonical ID of their campus;",
          {k: sum(1 for r in res if r[3] == k) for k in ("single, active", "single, no doctors", "one campus", "suggest", "open")})


def _selfcheck():
    assert round(km((22.5411, 88.3550), (22.5420, 88.3560)), 2) == 0.14
    fac = {"A": {"id": "A", "name": "IPGMER-SSKM HOSPITAL", "type": "Medical College", "state": "WB", "pin": "", "xy": (22.541, 88.355), "beds": 0},
           "B": {"id": "B", "name": "IPGMER and SSKM Hospital", "type": "Hospital", "state": "WB", "pin": "", "xy": (22.542, 88.356), "beds": 900},
           "C": {"id": "C", "name": "Shambhunath Pandit Hospital", "type": "Hospital", "state": "WB", "pin": "", "xy": (22.540, 88.354), "beds": 0},
           "D": {"id": "D", "name": "Mal Super Speciality Hospital", "type": "Hospital", "state": "WB", "pin": "", "xy": (26.86, 88.74), "beds": 0},
           "E": {"id": "E", "name": "Mal Sub Divisional Hospital", "type": "Hospital", "state": "WB", "pin": "", "xy": (26.861, 88.741), "beds": 0}}
    gs = groups({"A", "D"}, fac)
    assert sorted(map(sorted, gs)) == [["A", "B"], ["D"]], gs       # C is near but another hospital; an SSH is not the SDH
    assert not same_campus(fac["A"], {**fac["B"], "name": "Nikshay IPGMER-SSKM"})   # a TB programme entry is not the hospital
    assert canonical(["A", "B"], fac, {"A": 3, "B": 50}, {}) == "B"


if __name__ == "__main__":
    _selfcheck()
    main(sys.argv[1])
