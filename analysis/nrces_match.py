"""Match drug names to NRCeS Common Drug Codes for India (SNOMED CT) Generic Identifiers. Pure functions, no I/O.

nrces_index(tables) -> index;  match_generic(idx, name, pack) -> (gid, method, score) or None
match_brand(idx, product, company) -> (gid, 'brand', score) or None; falls back to match_generic (method exact/fuzzy).
tables = dict of lists of row dicts: GenericMaster, SubstanceMaster, RouteOfAdministrationMaster, DrugFormMaster, BrandMaster, SupplierMaster.
"""
import os, re, sys, difflib
from collections import defaultdict, Counter
from drug_key import generic, strength, form, sigs, STOP  # noqa: E402

SYN = [(r"vitamin[\s-]*d3|colecalciferol", "cholecalciferol"), (r"vitamin[\s-]*b12", "cyanocobalamin"),
       (r"vitamin[\s-]*c\b", "ascorbic acid"), (r"vitamin[\s-]*k1?\b|phytomenadione", "phytonadione"),
       (r"vitamin[\s-]*b1\b", "thiamine"), (r"vitamin[\s-]*b6\b", "pyridoxine"), (r"acetylsalicylic acid", "aspirin"),
       (r"nitroglycerine?", "glyceryl trinitrate"), (r"co-?trimoxazole", "sulfamethoxazole trimethoprim"),
       (r"\bdextrose\b", "glucose"), (r"\bnormal saline\b", "sodium chloride"), (r"\bhyoscine butyl ?bromide", "hyoscine")]
UNITS = [(r"micrograms?", "mcg"), (r"milligrams?", "mg"), (r"\bgrams?\b", "g"), (r"international units?", "iu"),
         (r"\bmillilit(?:re|er)s?\b", "ml")]
FAM = {"powder": "oral_liquid"}                                 # sachet/granules vs 'powder for oral suspension'
ROUTE_FOR = {"solid": "oral", "solid_dt": "oral", "solid_mr": "oral", "oral_liquid": "oral", "injection": "parenteral",
             "eye": "ocular", "eye_oint": "ocular", "ear": "otic", "nasal": "nasal", "inhal": "inhal", "topical": "cutaneous", "supp": "rectvag"}
FORMWORDS = {"tab": "tablet", "tabs": "tablet", "tablets": "tablet", "cap": "capsule", "caps": "capsule", "capsules": "capsule",
             "inj": "injection", "syp": "syrup", "susp": "suspension", "oint": "ointment", "soln": "solution"}
FW = set("tablet capsule injection infusion syrup suspension solution powder cream ointment gel lotion drops spray lozenge suppository".split())
CO = set("ltd limited pvt private pharma pharmaceuticals pharmaceutical laboratories laboratory labs lab india healthcare health care industries inc co company corporation life sciences lifesciences biotech remedies the and m s".split())


def norm_text(t):
    t = (t or "").lower()
    for rx, rep in SYN + UNITS: t = re.sub(rx, rep, t)
    t = re.sub(r"(\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)+)\s*(mg|mcg|g)\b",           # '100/10/500 MG' -> '100 mg + 10 mg + 500 mg'
               lambda m: " + ".join(f"{x} {m.group(2)}" for x in re.split(r"\s*/\s*", m.group(1))), t)
    return t


def route_group(name):
    n = name.lower()
    for g, rx in (("ocular", r"ophthalmic|conjunctival|intraocular|intravitreal|intracameral|subconjunctival|retrobulbar|peribulbar"),
                  ("otic", r"otic|tympanic"), ("nasal", r"^nasal"), ("inhal", r"respiratory|pulmonary|bronch|tracheal"),
                  ("cutaneous", r"cutaneous|transdermal|epilesional|dental|gingival"), ("rectvag", r"rectal|vaginal|urethral"),
                  ("oral", r"^oral|sublingual|buccal|oromucosal|gastro|enteral|oropharyngeal|nasogastric")):
        if re.search(rx, n): return g
    return "parenteral"


def fam(f): return FAM.get(f, f)


def formwords(t): return {FORMWORDS.get(w, w) for w in re.findall(r"[a-z]+", t.lower())} & FW


def subs_key(names): return tuple(sorted({s for n in names for s in generic(norm_text(n))}))


def stem(name):
    """brand stem: words before the first strength, number or form word. 'MAC GD3 TAB' -> 'mac gd3'."""
    out = []
    for w in re.findall(r"[a-z0-9]+", (name or "").lower()):
        if re.fullmatch(r"\d+(?:mg|mcg|ml|g|iu|gm)?", w) or w in STOP or w in FORMWORDS or w in FW: break
        out.append(w)
    return " ".join(out)


def co_tokens(name): return {w for w in re.findall(r"[a-z]+", (name or "").lower()) if w not in CO and len(w) > 1}


def nrces_index(t):
    sub = {r["Identifier"]: r["Substance Name"] for r in t["SubstanceMaster"]}
    rte = {r["Identifier"]: r["RouteOfAdministration"] for r in t["RouteOfAdministrationMaster"]}
    dfm = {r["Id"]: r["Dose Form"] for r in t["DrugFormMaster"]}
    nbrand = Counter(r["Generic Identifier"] for r in t["BrandMaster"])
    gen, by = {}, defaultdict(list)
    for r in t["GenericMaster"]:
        subs = [sub[s] for s in r["Substance Identifier"].split("+") if s in sub]
        routes = [rte[s] for s in r["Route of Administration"].split("+") if s in rte]
        df = dfm.get(r["Dose Form"], "")
        a, c, _ = strength(norm_text(r["Generic Name"]))
        g = dict(id=r["Identifier"], name=r["Generic Name"], substances="+".join(subs), route="+".join(routes), form=df,
                 skey=subs_key(subs), fam=fam(form(df + " " + " ".join(routes))), rgroups={route_group(x) for x in routes},
                 sigs=sigs(dict(amounts=a, concs=c)), fw=formwords(df), nb=nbrand.get(r["Identifier"], 0))
        gen[g["id"]] = g
        if g["skey"]: by[(g["skey"], g["fam"])].append(g)
    sup = {r["Identifier"]: co_tokens(r["Supplier Name"]) for r in t["SupplierMaster"]}
    brands = defaultdict(list)
    for r in t["BrandMaster"]:
        if r["Generic Identifier"] in gen: brands[stem(r["Brand Name"])].append((r["Generic Identifier"], sup.get(r["Supplier Identifier"], set())))
    byfam = defaultdict(list)
    for (sk, f) in by: byfam[(len(sk), f)].append(sk)
    return dict(gen=gen, by=by, byfam=byfam, brands=brands)


def sig_hit(a, b):
    """strength signatures agree within 2% ('120 mg/1.7 mL' = 70.6 mg/mL ~ '70 mg/mL')."""
    return any(x[0] == y[0] and len(x[1]) == len(y[1]) and all(u1 == u2 and abs(v1 - v2) <= 0.02 * max(v1, v2) for (v1, u1), (v2, u2) in zip(x[1], y[1]))
               for x in a for y in b)


def _pick(cands, k, fws):
    """best candidate: shares a strength signature, route fits the form; then form words, brand count, id."""
    s = sigs(k)
    ok = [g for g in cands if sig_hit(g["sigs"], s) and ROUTE_FOR.get(k["form"], "") in g["rgroups"]]
    if not ok: return None
    return max(ok, key=lambda g: (len(g["fw"] & fws), g["nb"], -int(g["id"])))


def match_generic(idx, name, pack="", fuzzy=True):
    t = norm_text(name)
    a, c, vol = strength(t)
    f = form(t + " " + (pack or "").lower())
    k = dict(amounts=a, concs=c, form=f)
    sk = tuple(sorted(generic(t)))
    if not sk or f == "other" or not (a or c): return None
    fws = formwords(name + " " + (pack or ""))
    g = _pick(idx["by"].get((sk, fam(f)), []), k, fws)
    if g: return g["id"], "exact", 1.0 if (not g["fw"] or g["fw"] & fws) else 0.9
    if fam(f) == "solid":                                         # plain 'tablets' of a drug NRCeS lists only as prolonged-release
        g = _pick(idx["by"].get((sk, "solid_mr"), []), dict(k, form="solid_mr"), fws)
        if g: return g["id"], "fuzzy", 0.8
    if not fuzzy: return None
    best = None                                                   # fuzzy: each substance skeleton close to one in NRCeS
    for sk2 in idx["byfam"].get((len(sk), fam(f)), []):
        r = min(difflib.SequenceMatcher(None, x, y).ratio() for x, y in zip(sk, sk2))
        if r >= 0.8 and (best is None or r > best[0]):
            g = _pick(idx["by"][(sk2, fam(f))], k, fws)
            if g: best = (r, g)
    return (best[1]["id"], "fuzzy", round(best[0] * 0.9, 3)) if best else None


def match_brand(idx, product, company=""):
    t = norm_text(product)
    a, c, _ = strength(t)
    f = form(t)
    s, ct = sigs(dict(amounts=a, concs=c)), co_tokens(company)
    cands = []
    for gid, stoks in idx["brands"].get(stem(t), []):
        g = idx["gen"][gid]
        if f != "other" and fam(f) != g["fam"]: continue
        if s and not sig_hit(g["sigs"], s): continue
        cands.append((gid, bool(ct & stoks)))
    if cands:
        sup = [x for x in cands if x[1]] or cands
        ids = Counter(x[0] for x in sup)
        if s or len(ids) == 1:                                    # no strength in the product: only a single generic is safe
            gid = max(ids, key=lambda i: (ids[i], idx["gen"][i]["nb"]))
            return gid, "brand", (1.0 if s else 0.7) * (1.0 if sup[0][1] else 0.85)
    # fallback on the generic name only, exact substances: fuzzy on brand words gives false hits (CIPTAB -> capecitabine)
    return match_generic(idx, re.sub(r"\([^)]*\)|\s-\s?\S.*$|\s-[a-z].*$", " ", t), fuzzy=False)


if __name__ == "__main__":
    T = dict(SubstanceMaster=[dict(Identifier="1", **{"Substance Name": "Amoxicillin trihydrate"}), dict(Identifier="2", **{"Substance Name": "Clavulanate potassium"}),
                              dict(Identifier="3", **{"Substance Name": "Ondansetron hydrochloride"}), dict(Identifier="4", **{"Substance Name": "Cholecalciferol"})],
             RouteOfAdministrationMaster=[dict(Identifier="10", RouteOfAdministration="Oral route"), dict(Identifier="11", RouteOfAdministration="Intravenous route")],
             DrugFormMaster=[dict(Id="20", **{"Dose Form": "Oral tablet"}), dict(Id="21", **{"Dose Form": "Solution for injection"}), dict(Id="22", **{"Dose Form": "Oral capsule"}),
                             dict(Id="23", **{"Dose Form": "Oral drops"})],
             GenericMaster=[dict(Identifier="100", **{"Generic Name": "Amoxicillin 500 mg and clavulanic acid 125 mg oral tablet", "Substance Identifier": "1+2", "Route of Administration": "10", "Dose Form": "20"}),
                            dict(Identifier="101", **{"Generic Name": "Ondansetron 2 mg/mL solution for injection", "Substance Identifier": "3", "Route of Administration": "11", "Dose Form": "21"}),
                            dict(Identifier="102", **{"Generic Name": "Amoxicillin 500 mg and clavulanic acid 125 mg oral capsule", "Substance Identifier": "1+2", "Route of Administration": "10", "Dose Form": "22"}),
                            dict(Identifier="103", **{"Generic Name": "Cholecalciferol 400 unit/mL oral drops", "Substance Identifier": "4", "Route of Administration": "10", "Dose Form": "23"})],
             BrandMaster=[dict(Identifier="200", **{"Brand Name": "Augmentin 625 Duo oral tablet", "Generic Identifier": "100", "Supplier Identifier": "300"}),
                          dict(Identifier="201", **{"Brand Name": "Emeset 2 mg/mL solution for injection", "Generic Identifier": "101", "Supplier Identifier": "301"})],
             SupplierMaster=[dict(Identifier="300", **{"Supplier Name": "GlaxoSmithKline Pharmaceuticals Limited"}), dict(Identifier="301", **{"Supplier Name": "Cipla Limited"})])
    ix = nrces_index(T)
    assert match_generic(ix, "Amoxycillin 500mg + Clavulanate Potassium 125 mg Tab") == ("100", "exact", 1.0)
    assert match_generic(ix, "Amoxycillin 500mg + Clavulanate Potassium 125 mg Capsules")[0] == "102"
    assert match_generic(ix, "Ondansetron Inj 4mg/2ml", "2 ml amp")[:2] == ("101", "exact")
    assert match_generic(ix, "Ondansetron Tab 4mg") is None                       # strength and form must both fit
    assert match_generic(ix, "Ondansetron Inj 8mg/2ml") is None
    assert match_generic(ix, "Ondasetron Inj 2mg/ml")[:2] == ("101", "fuzzy")     # spelling variant beyond the skeleton
    assert sig_hit({("c", ((70.588, "mg"),))}, {("c", ((70.0, "mg"),))}) and not sig_hit({("a", ((10.0, "mg"),))}, {("a", ((12.5, "mg"),))})
    assert match_generic(ix, "Vitamin D3 drops 400 IU/ml")[0] == "103"
    assert match_brand(ix, "EMESET INJ 2MG/ML", "CIPLA LTD") == ("101", "brand", 1.0)
    assert match_brand(ix, "AUGMENTIN 625 DUO TAB", "GSK")[0] == "100"           # stem 'augmentin', unique generic
    assert match_brand(ix, "ONDASETRON 2 MG/ML INJ", "X") is None                # no fuzzy fallback for brand-list products
    assert match_brand(ix, "ONDANSETRON 4MG/2ML INJ -CIRON DRUGS PVT LTD", "X")[:2] == ("101", "exact")
    assert stem("MAC GD3 TAB") == "mac gd3" and stem("SITACIP DM (100/10/500 MG) TAB") == "sitacip dm"
    assert strength(norm_text("SITACIP DM (100/10/500 MG) TAB"))[0] == ((10.0, "mg"), (100.0, "mg"), (500.0, "mg"))
    print("nrces_match ok")
