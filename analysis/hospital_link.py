"""Link medical-corporation tenders to the hospital they are for (ABDM facility registry, HFR).

Input: tenders (corp, tender_id, location, pincode, title) and government HFR facilities (hfr_id, hospital, facility_type,
ownership, district, state, pincode), both CSV without header. Output CSV: corp, tender_id, hfr_id, hospital, district,
state, pool, confidence, score.

Both names are normalised first: abbreviations (SSH, DH, SD and SS, MCH ...), hospital acronyms (NRS, MJN ...) and place
spellings (Burdwan = Bardhaman, Midnapore = Medinipur ...). The facility name must contain the first name word of the
location (the hospital's own place or name, e.g. "suri" in "Suri SSH, Birbhum", "nss" in "NSS Kalyani in Nadia"); a first
word that is in many facility names of the state (a district town) needs the same type and only one such facility:
- confidence "exact": the hospital type agrees too (super speciality, district, medical college ...);
- confidence "town": only for a super speciality tender whose town has a district, sub-divisional or state general
  hospital in the registry and no super speciality entry (WBMSC built new super speciality units in such towns, e.g.
  Suri SSH -> Suri District Hospital). Same town, often the same campus; check before treating it as the same facility.
Any other type mismatch is not linked (a medical college is not the town's ESIC or taluk hospital).
Candidates come from the same pincode first, then the same state. Locations without any hospital word, and tenders for
the head office or the whole state, are not linked.

Usage: python3 analysis/hospital_link.py TENDERS.csv HFR.csv OUT.csv
"""
import csv
import re
import sys
from collections import Counter, defaultdict

ABBR = {"ssh": "super speciality hospital", "ssb": "super speciality hospital", "ss": "super speciality",
        "sh": "state hospital", "dh": "district hospital", "sdh": "sub divisional hospital", "sd": "sub divisional",
        "sgh": "state general hospital", "gh": "general hospital", "mch": "medical college hospital",
        "gmch": "government medical college hospital", "gmc": "government medical college", "rh": "rural hospital",
        "bphc": "block primary health centre", "phc": "primary health centre", "chc": "community health centre",
        "uphc": "urban primary health centre", "thq": "taluk headquarters", "thqh": "taluk headquarters hospital",
        # hospitals known by their initials
        "nrs": "nil ratan sircar", "mjn": "maharaja jitendra narayan", "sskm": "seth sukhlal karnani memorial",
        "ipgmer": "seth sukhlal karnani memorial", "cnmc": "calcutta national medical college", "rgkar": "r g kar"}
SPELL = {"burdwan": "bardhaman", "barddhaman": "bardhaman", "midnapore": "medinipur", "midnapur": "medinipur",
         "mursidabad": "murshidabad", "domkol": "domkal", "bongoan": "bongaon", "calcutta": "kolkata", "hugli": "hooghly",
         "srirampur": "serampore", "sreerampur": "serampore", "borjora": "barjora", "berhampore": "baharampur",
         "behrampore": "baharampur", "berhampur": "baharampur", "chinsurah": "chinsura", "darjiling": "darjeeling",
         "puruliya": "purulia", "kanthi": "contai", "krishnanagar": "krishnagar", "coochbehar": "cooch behar",
         "koch": "cooch", "bihar": "behar", "paraganas": "parganas", "pargana": "parganas", "jalpaiguri": "jalpaiguri",
         "trivandrum": "thiruvananthapuram", "calicut": "kozhikode", "alleppey": "alappuzha", "trichur": "thrissur",
         "quilon": "kollam", "cochin": "kochi", "palghat": "palakkad", "cannanore": "kannur", "speciality": "speciality",
         "specialty": "speciality", "centre": "centre", "center": "centre", "govt": "government", "collge": "college", "superspeciality": "super speciality", "superspecialty": "super speciality", "hosptal": "hospital"}
TYPES = {"super", "district", "sub", "divisional", "state", "general", "medical", "college", "rural", "primary", "community",
         "health", "centre", "hospital", "hospitals", "government", "urban", "block", "and", "of", "the", "in", "at", "for",
         "unit", "care", "speciality", "multi", "new", "old", "building", "campus", "taluk", "headquarters", "institute",
         "west", "east", "north", "south", "central", "bengal", "office", "principal", "controller", "superintendent", "ms",
         "cmoh", "covid", "colleges", "different", "various", "district", "memorial", "esic", "medicine", "school", "tropical"}
TOWN_TYPES = {"district", "divisional", "general"}   # registry types a new super speciality unit of the same town may sit in
KEYTYPES = {"super", "district", "divisional", "medical", "rural", "primary", "community", "general", "esic", "state", "taluk"}
HOSPITAL_WORDS = KEYTYPES | {"hospital", "college", "institute", "centre"}
STATEWIDE = re.compile(r"^\s*(west bengal|kerala|tamil ?nadu|rajasthan|madhya pradesh|maharashtra|odisha|uttar pradesh|"
                       r"jharkhand|himachal|haryana|bihar|all|various|state)\b", re.I)
STATE_OF_CORP = {"WBMSC": "west bengal", "KMSCL": "kerala", "TNMSC": "tamil nadu", "RMSCL": "rajasthan",
                 "MPPHSCL": "madhya pradesh", "MMGPA": "maharashtra", "HAFFKINE": "maharashtra", "OSMCL": "odisha",
                 "UPMSCL": "uttar pradesh", "JMHIDPCL": "jharkhand", "HPMSCL": "himachal pradesh"}
COMMON = 15          # a word in more government facility names of a state than this is not distinctive (kolkata, udaipur)


def norm(s):
    """Lower-case words with abbreviations and spellings resolved: 'Kalna SD & SS Hosp.' -> [kalna, sub, divisional, ...]."""
    s = (s or "").lower()
    s = re.sub(r"\b(?:[a-z]\.\s?){2,}", lambda m: m.group().replace(".", "").replace(" ", "") + " ", s)  # "r.n.t." -> "rnt"
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    out = []
    for w in s.split():
        out += SPELL.get(ABBR.get(w, w), ABBR.get(w, w)).split()
    return [SPELL.get(w, w) for w in out]


def content(ws):
    return {w for w in ws if w not in TYPES and not w.isdigit() and len(w) > 2}


def parts(loc):
    """'Chanchol SSH, Jangipur SSH, Dumkol SSH' -> three hospitals; 'Suri SSH, Birbhum' stays one (a district name joins the
    hospital before it); 'Debra SSH and Belda SSH' -> two ('and' splits only between two named hospitals)."""
    out = []
    for seg in re.split(r"[,;/]|\band\b", loc, flags=re.I):
        if out and not (set(norm(seg)) & KEYTYPES):
            out[-1] += " " + seg
        elif seg.strip():
            out.append(seg)
    return out or [loc]


def link(tenders, facilities):
    by_pin, by_state, freq = defaultdict(list), defaultdict(list), defaultdict(Counter)
    for f in facilities:
        f["n"] = set(norm(f["hospital"]))
        f["c"] = content(f["n"])
        st = f["state"].lower()
        by_pin[f["pincode"]].append(f)
        by_state[st].append(f)
        freq[st].update(f["c"])
    for t in tenders:
        st = STATE_OF_CORP.get(t["corp"], "")
        for loc in parts(t["location"] or ""):
            tl = set(norm(loc))
            if STATEWIDE.match(loc) or not (tl & HOSPITAL_WORDS):
                continue                               # head office, whole state, or no hospital named
            kinds = KEYTYPES & tl
            names = [w for w in norm(loc) if w in content([w])]
            if not names:
                continue
            first = names[0]                           # the hospital's own place or name: "suri" in "Suri SSH, Birbhum"
            pools = (("pincode", by_pin.get(t["pincode"], [])), ("state", by_state.get(st, [])))
            if freq[st][first] > COMMON:               # a district town in many names: same type, and only one such facility
                same = [f for f in by_state.get(st, []) if first in f["c"] and kinds & f["n"]]
                pools = (("state", same if len(same) == 1 else []),)
            words = set(names)
            for pool_name, pool in pools:
                hits = [f for f in pool if first in f["c"]]
                if hits:
                    best = max(hits, key=lambda f: (bool(kinds & f["n"]), len(words & f["c"]), len(tl & f["n"])))
                    if kinds & best["n"]:
                        conf = "exact"
                    elif "super" in kinds and TOWN_TYPES & best["n"] and "esic" not in best["n"]:
                        conf = "town"
                    else:
                        continue                       # other kind of facility here: try the next pool, else no link
                    yield t, best, pool_name, conf, len(words & best["c"])
                    break

def main(tpath, fpath, opath):
    tcols = ["corp", "tender_id", "location", "pincode", "title"]
    fcols = ["hfr_id", "hospital", "facility_type", "ownership", "district", "state", "pincode"]
    tenders = [dict(zip(tcols, r)) for r in csv.reader(open(tpath))]
    facilities = [dict(zip(fcols, r)) for r in csv.reader(open(fpath))]
    n = Counter()
    with open(opath, "w", newline="") as fh:
        w = csv.writer(fh)
        for t, f, pool, conf, score in link(tenders, facilities):
            w.writerow([t["corp"], t["tender_id"], f["hfr_id"], f["hospital"], f["district"], f["state"], pool, conf, score])
            n[conf] += 1
    print(f"{sum(n.values())} of {len(tenders)} tenders linked: {dict(n)}")


def _selfcheck():
    fac = [dict(hfr_id=str(i), hospital=h, district=d, state="West Bengal", pincode=p) for i, (h, d, p) in enumerate([
        ("Kalna SD and SS Hospital", "Purba Bardhaman", "713409"), ("Suri District Hospital", "Birbhum", "731101"),
        ("Bardhaman Medical College and Hospital", "Purba Bardhaman", "713104"),
        ("Nil Ratan Sircar Medical College", "Kolkata", "700014"), ("ESIC Hospital Udaipur", "Udaipur", "313001"),
        ("Taluk Head Quarters Hospital Konni", "Pathanamthitta", "689691"), ("Nadia District Hospital", "Nadia", "741101")])]
    fac += [dict(hfr_id=f"k{i}", hospital=f"Kolkata Clinic {i}", district="Kolkata", state="West Bengal", pincode="700001")
            for i in range(COMMON + 1)]
    ten = [dict(corp="WBMSC", tender_id=k, location=loc, pincode=pin, title="") for k, loc, pin in [
        ("a", "kalna SSH", "713409"), ("b", "Suri SSH, Birbhum", "731101"), ("c", "Burdwan Medical College", "713101"),
        ("d", "NRS MCH, Kolkata", "700014"), ("e", "MCH, KOLKATA", "700001"), ("f", "WEST BENGAL", "700091"),
        ("g", "Parel, Mumbai", "400012"), ("j", "MCH, Kolkata", "700014"), ("h", "RNT Medical College, Udaipur", "313001"),
        ("i", "Govt. Medical College Konni", "689691"), ("k", "NSS Kalyani in Nadia District", "741235")]]
    got = {t["tender_id"]: (f["hfr_id"], conf) for t, f, _, conf, _ in link(ten, fac)}
    assert [p.strip() for p in parts("Chanchol SSH, Jangipur SSH, Dumkol SSH")] == ["Chanchol SSH", "Jangipur SSH", "Dumkol SSH"]
    assert len(parts("Suri SSH, Birbhum")) == 1 and len(parts("Debra SSH and Belda SSH")) == 2
    assert len(parts("Medical College and Hospital, Kolkata")) == 1
    assert norm("R.N.T. Medical College")[0] == "rnt" and norm("M.R. Bangur SSH")[:2] == ["mr", "bangur"]
    assert got == {"a": ("0", "exact"), "b": ("1", "town"), "c": ("2", "exact"), "d": ("3", "exact")}  # "MCH, Kolkata" names no hospital, got


if __name__ == "__main__":
    _selfcheck()
    if len(sys.argv) == 4:
        main(*sys.argv[1:4])
