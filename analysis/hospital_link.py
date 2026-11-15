"""Link medical-corporation tenders to the hospital they are for (ABDM facility registry, HFR).

Input: tenders (corp, tender_id, location, pincode, title) and government HFR facilities (hfr_id, hospital, facility_type,
district, state, pincode), both CSV without header. Output CSV: corp, tender_id, hfr_id, hospital, district, state, method, score.

Rule: the tender's place word (first word of its location, e.g. "Suri" in "Suri Super Speciality Hospital") and at least one
hospital type word (super speciality, district, medical college ...) must appear in the facility name; candidates come
from the same pincode first, then the same state. A location without a type word is not linked. Tenders for the head office or the whole state ("WEST BENGAL", HQ pincodes) are not linked.
shortcut: name rules only, no fuzzy matching; misses spelling variants (Burdwan / Bardhaman), add an alias list when needed.

Usage: python3 analysis/hospital_link.py TENDERS.csv HFR.csv OUT.csv
"""
import csv
import re
import sys
from collections import defaultdict

ABBR = {"ssh": "super speciality hospital", "ssb": "super speciality hospital", "sh": "state hospital",
        "dh": "district hospital", "sdh": "sub divisional hospital", "sgh": "state general hospital",
        "mch": "medical college hospital", "gmch": "government medical college hospital", "rh": "rural hospital",
        "bphc": "block primary health centre", "phc": "primary health centre", "chc": "community health centre",
        "uphc": "urban primary health centre", "sncu": "sick newborn care unit", "ccu": "critical care unit"}
TYPES = {"super", "district", "sub", "divisional", "state", "general", "medical", "college", "rural", "primary", "community",
         "health", "centre", "center", "hospital", "government", "govt", "urban", "block", "and", "of", "the", "in", "at",
         "district", "unit", "care", "speciality", "specialty", "multi", "new", "old", "building", "campus"}
KEYTYPES = {"super", "district", "divisional", "medical", "rural", "primary", "community", "general", "esic", "state"}
STATEWIDE = re.compile(r"^\s*(west bengal|kerala|tamil ?nadu|rajasthan|madhya pradesh|maharashtra|odisha|uttar pradesh|"
                       r"jharkhand|himachal|haryana|bihar|all|various|state)\b", re.I)


def words(s):
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    return [ABBR.get(w, w) for w in s.split()]


def norm(s):
    return " ".join(words(s)).split()


def place(location):
    """The first word that is not a type word: 'Suri Super Speciality Hospital' -> 'suri', 'Kalimpong DH' -> 'kalimpong'."""
    for w in norm(location):
        if w not in TYPES and not w.isdigit() and len(w) > 2:
            return w
    return None


def link(tenders, facilities):
    by_pin, by_state = defaultdict(list), defaultdict(list)
    for f in facilities:
        f["n"] = set(norm(f["hospital"]))
        by_pin[f["pincode"]].append(f)
        by_state[f["state"].lower()].append(f)
    state_of_corp = {"WBMSC": "west bengal", "KMSCL": "kerala", "TNMSC": "tamil nadu", "RMSCL": "rajasthan",
                     "MPPHSCL": "madhya pradesh", "MMGPA": "maharashtra", "HAFFKINE": "maharashtra", "OSMCL": "odisha",
                     "UPMSCL": "uttar pradesh", "JMHIDPCL": "jharkhand", "HPMSCL": "himachal pradesh"}
    for t in tenders:
        loc = t["location"] or ""
        if STATEWIDE.match(loc):
            continue
        p = place(loc)
        if not p:
            continue
        tl = set(norm(loc))
        kinds = KEYTYPES & tl
        if not kinds:                                  # a place without a hospital type ("Parel, Mumbai"): too vague
            continue
        for method, pool in (("pincode", by_pin.get(t["pincode"], [])),
                             ("state", by_state.get(state_of_corp.get(t["corp"], ""), []))):
            hits = [f for f in pool if p in f["n"] and kinds & f["n"]]
            if hits:
                best = max(hits, key=lambda f: len(f["n"] & tl))
                yield t, best, method, len(best["n"] & tl)
                break


def main(tpath, fpath, opath):
    tcols = ["corp", "tender_id", "location", "pincode", "title"]
    fcols = ["hfr_id", "hospital", "facility_type", "ownership", "district", "state", "pincode"]
    tenders = [dict(zip(tcols, r)) for r in csv.reader(open(tpath))]
    facilities = [dict(zip(fcols, r)) for r in csv.reader(open(fpath))]
    n = 0
    with open(opath, "w", newline="") as fh:
        w = csv.writer(fh)
        for t, f, method, score in link(tenders, facilities):
            w.writerow([t["corp"], t["tender_id"], f["hfr_id"], f["hospital"], f["district"], f["state"], method, score])
            n += 1
    print(f"{n} of {len(tenders)} tenders linked")


if __name__ == "__main__":
    assert place("Suri Super Speciality Hospital") == "suri" and place("Kalimpong DH") == "kalimpong"
    assert place("Medical College and Hospital, Kolkata") == "kolkata" and STATEWIDE.match("WEST BENGAL")
    main(*sys.argv[1:4])
