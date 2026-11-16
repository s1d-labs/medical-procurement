"""Drug key: generic name + strength + dosage form + pack -> price per unit. Pure functions, no I/O.

key(name, pack) -> dict(gen, form, amounts, concs, vol, count, pack_ml)
per_unit(rate, k) -> {'unit': price per tablet/vial, 'ml': price per ml or g}
"""
import re

SALTS = set("""hydrochloride hcl hydrobromide hbr sodium potassium calcium magnesium sulphate sulfate phosphate maleate
besylate besilate mesylate mesilate tartrate bitartrate succinate citrate acetate bromide butylbromide butyl fumarate
dihydrate trihydrate monohydrate anhydrous hemihydrate sesquihydrate dihydrochloride dipropionate propionate valerate furoate
gluconate lactate nitrate disodium trometamol tromethamine bisulphate bisulfate dimesylate oxalate hyclate
pamoate embonate xinafoate carbonate chloride bicarbonate oxide hydroxide""".split())
STOP = set("""tablet tablets tab tabs capsule capsules cap caps injection injections inj infusion for ip bp usp ph eur nf
film coated fc sugar uncoated gastro resistant enteric delayed release sustained extended prolonged controlled modified
sr er xr cr mr pr dr xl la cd oral solution suspension syrup liquid drops drop eye ear nasal ophthalmic otic cream
ointment gel lotion application powder granules sachet sachets dispersible dt md odt orally disintegrating chewable each
contains containing contain with and of per in as the a an or to w v ml mg mcg gm g iu units unit u vial vials amp ampoule
ampoules bottle pfs prefilled pre filled syringe single dose doses multi mdv sdv bag ffs bfs glass non plastic pack strip
blister foil tube jar carton sterile wfi diluent schedule therapeutic therapuetic lyophilized lyophilised lyophilized
concentrate concentrated ready use intravenous iv im sc subcutaneous respules inhaler inhalation metered mdi rotacap
rotacaps dpi nebuliser nebulizer nebulisation paediatric pediatric adult base equivalent eq elemental plain bolus
mono monopack normal measuring dropper cap screw spray transdermal patch kit""".split())
SPELL = {"acetaminophen": "paracetamol", "frusemide": "furosemide", "lidocaine": "lignocaine", "epinephrine": "adrenaline",
         "norepinephrine": "noradrenaline", "albuterol": "salbutamol", "glyburide": "glibenclamide", "cotrimoxazole": "sulfamethoxazole trimethoprim",
         "cefalexin": "cephalexin", "metronidazol": "metronidazole", "vit": "vitamin", "levothyroxine": "thyroxine",
         "rifampin": "rifampicin", "saline": "sodium chloride", "clavulanate": "clavulanic", "valproate": "valproic", "carboxymethylcellulose": "carboxymethyl cellulose"}
FORMS = [  # first match wins; order matters
    ("eye", r"\beye\b|ophthalmic|\beye ointment"), ("ear", r"\bear\b|\botic\b"), ("nasal", r"\bnasal\b"),
    ("inhal", r"inhal|respule|rotacap|\bmdi\b|\bdpi\b|nebuli|respirator|metered"),
    ("topical", r"cream|ointment|\bgel\b|lotion|application|topical|\bpaint\b"),
    ("supp", r"suppositor|pessar|vaginal"),
    ("injection", r"\binj|infusion|\bvial|ampoule|\bamp\b|\bpfs\b|prefilled|pre-filled|\biv\b|for injection|intravenous"),
    ("oral_liquid", r"syrup|suspension|oral solution|oral liquid|elixir|\bdrops?\b|linctus|oral emulsion|dry syrup"),
    ("powder", r"sachet|granule|powder|\bors\b"),
    ("solid", r"\btab|\bcap|capsule|caplet|softgel|soft gel|\bdt\b"),
]
MR = r"\b(sr|er|xr|cr|mr|pr|xl|cd|od)\b|sustained|extended|prolonged|controlled|modified release|\bretard"
DT = r"dispersible|\bdt\b|\bmd\b|\bodt\b|orally disintegrating|mouth dissolving"


def skel(w):
    """consonant skeleton: tolerant of vowel and ph/f, y/i spelling variants (levocetrizine = levocetirizine)."""
    w = w.replace("ph", "f").replace("y", "i").replace("th", "t").replace("ck", "k")
    w = re.sub(r"(.)\1+", r"\1", w)
    return w[0] + re.sub(r"[aeiou]", "", w[1:])


def generic(name):
    t = name.lower()
    t = re.sub(r"\[[^\]]*\]", " ", t)                       # [NRD-822] codes
    t = re.sub(r"\(\s*[ab]\s*\)", " ", t)                  # (A) (B) markers in NPPA
    t = re.sub(r"\bvitamin[\s-]*([a-z])[\s-]*(\d*)\b", r"vitamin\1\2", t)
    t = re.sub(r"(\w)ic acid\b", r"\1ic", t)
    t = re.sub(r"[^a-z]+", " ", t)
    words = []
    for w in t.split():
        w = SPELL.get(w, w)
        words += w.split()
    words = [w for w in words if len(w) > 1 and w not in STOP]
    act = [w for w in words if w not in SALTS] or words    # 'sodium chloride' keeps both salt words
    return tuple(sorted({skel(w) for w in act}))


NUM = r"(\d+(?:\.\d+)?)"
U = r"(mg|mcg|µg|ug|gm|gms|g|iu|i\.u\.|units?|u|%|lac|lakh)"


def _amt(v, u):
    v = float(v)
    u = u.rstrip(".").lower()
    if u in ("mcg", "µg", "ug"): return round(v / 1000, 6), "mg"
    if u in ("g", "gm", "gms"): return round(v * 1000, 6), "mg"
    if u == "mg": return round(v, 6), "mg"
    if u == "%": return round(v * 10, 6), "mg"            # % w/v -> mg per ml
    return round(v, 6), "iu"


def strength(name):
    t = name.lower().replace(",", " ").replace("µ", "mc")
    t = re.sub(r"(\d),(\d{3})", r"\1\2", t)
    amounts, concs = [], []
    pat = re.compile(NUM + r"\s*" + U + r"(?![a-z])(?:\s*(?:w/v|w/w|v/v))?(?:\s*(?:/|per|in)\s*" + r"(\d+(?:\.\d+)?)?\s*(ml|g|gm)\b)?")
    rest = t
    for m in pat.finditer(t):
        v, u, pv, pu = m.groups()
        a = _amt(v, u)
        if u == "%":
            concs.append(a)
        elif pu:
            concs.append((round(a[0] / float(pv or 1), 6), a[1]))
        else:
            amounts.append(a)
        rest = rest.replace(m.group(0), " ", 1)
    vm = re.search(NUM + r"\s*(ml|ltr|litre|l)\b", rest)
    vol = None
    if vm:
        vol = float(vm.group(1)) * (1000 if vm.group(2) != "ml" else 1)
    if vol and len(amounts) == 1 and not concs:             # 500 mg in 2 ml vial -> 250 mg/ml
        concs.append((round(amounts[0][0] / vol, 6), amounts[0][1]))
    return tuple(sorted(set(amounts))), tuple(sorted(set(concs))), vol


def form(name):
    t = name.lower()
    for f, rx in FORMS:
        if re.search(rx, t):
            if f == "eye" and re.search(r"ointment|gel\b", t): return "eye_oint"
            if f == "solid":
                if re.search(DT, t): return "solid_dt"
                if re.search(MR, t): return "solid_mr"
            return f
    return "other"


def pack(text):
    """pack text -> (count of units, ml or g per unit). '10X10' -> (100, None); '2 ml Amp 25 Ampoules' -> (25, 2.0)."""
    t = (text or "").lower().strip()
    if re.fullmatch(r"\d+", t): return int(t), None        # TGMSIDC unit column
    ml = None
    m = re.search(NUM + r"\s*(ml|gm|gms|g|ltr|l)\b", t)
    if m:
        ml = float(m.group(1)) * (1000 if m.group(2) in ("ltr", "l") else 1)
        t = t[:m.start()] + " " + t[m.end():]
    m = re.search(r"\d+(?:\s*[x\*×]\s*\d+)+", t)
    if m:                                                    # '10X3X3' -> 90
        n = 1
        for d in re.findall(r"\d+", m.group()): n *= int(d)
        return n, ml
    m = re.search(r"(\d+)\s*'?s\b", t) or re.search(
        r"(\d+)\s*(?:tabs?|tablets?|caps?|capsules?|amp\w*|vials?|nos?\b|sachets?|pfs|bottles?|units?|pieces?|bolus|strips?|foils?|syringes?|pairs?|cartridges?|pens?|respules?)", t)
    return (int(m.group(1)) if m else 1), ml


def key(name, pack_text=""):
    amounts, concs, vol = strength(name)
    count, pml = pack(pack_text)
    f = form(name + " " + (pack_text or ""))
    if f == "injection" and not (pml or vol):              # 'RITUXIMAB INJ 600MG/60ML' with pack 'VIAL': the vial holds 60 ml
        m = re.search(r"(?:/|per)\s*(\d+(?:\.\d+)?)\s*ml", name.lower())
        vol = float(m.group(1)) if m else None
    doses = None
    if f in ("inhal", "nasal"):                              # MDI price per container; NPPA price per dose
        m = re.search(r"(\d+)\s*(?:-|\s)?(?:md\b|mdi|metered|doses?\b|actuation|puffs?)", (name + " " + (pack_text or "")).lower())
        doses = int(m.group(1)) if m else (1 if re.search(r"cap|respule", (name + " " + (pack_text or "")).lower()) else None)  # rotacap/respule = 1 dose
    return dict(gen=generic(name), form=f, amounts=amounts, concs=concs, vol=pml or vol, count=count, doses=doses)


def sigs(k):
    """strength signatures that two records must share to match."""
    s = set()
    if k["amounts"]: s.add(("a", k["amounts"]))
    if k["concs"]: s.add(("c", k["concs"]))
    return s


def per_unit(rate, k):
    """rate for the whole pack -> price per unit (tablet/vial/bottle) and per ml (or g) when the volume is known."""
    if rate is None or not k["count"]: return {}
    unit = rate / k["count"]
    out = {"unit": unit}
    if k["vol"] and k["form"] not in ("solid", "solid_mr", "solid_dt"):
        out["ml"] = unit / k["vol"]
    if k.get("doses"):
        out["dose"] = unit / k["doses"]
    return out


if __name__ == "__main__":
    assert generic("Levocetrizine Syrup") == generic("LEVOCETIRIZINE DIHYDROCHLORIDE SYRUP IP")
    assert generic("Amoxycillin 500mg + Clavulanate Potassium 125 mg Tab") == generic("Amoxicillin and Clavulanic Acid Tablets IP")
    assert generic("Metformin Hydrochloride Tablets IP 500 mg") == generic("METFORMIN TAB 500MG")
    assert generic("Sodium Chloride Injection 0.9%") == generic("Normal Saline (Sodium Chloride) inj") == ("chlrd", "sdm")
    assert generic("Frusemide Inj") == generic("Furosemide Injection")
    assert generic("Meropenam 500 mg Injection") == generic("Meropenem for Injection IP")
    assert strength("Amoxicillin 500mg + Clavulanic 125 mg")[0] == ((125.0, "mg"), (500.0, "mg"))
    assert strength("Ambroxal Syrup 60ml 30mg/5ml") == ((), ((6.0, "mg"),), 60.0)
    assert strength("Amikacin Injection 500mg, 2ml vial")[1] == ((250.0, "mg"),)
    assert strength("Lignocaine Injection 2%")[1] == ((20.0, "mg"),)
    assert strength("Fentanyl Injection 50 mcg/ml, 2ml ampoule")[1] == ((0.05, "mg"),)
    assert strength("Ceftriaxone Inj 1 g")[0] == ((1000.0, "mg"),)
    assert form("Desvenlafaxine 50mg CR/PR/SR/ER Tablet") == "solid_mr" and form("Azithromycin Dispersible Tablets 100mg") == "solid_dt"
    assert form("Olopatadine 0.1% Eye Drops 5 ml") == "eye" and form("Domperidone Oral Drops IP") == "oral_liquid"
    assert pack("10X10 Tablets") == (100, None) and pack("1 X 14 TABS") == (14, None) and pack("10's") == (10, None)
    assert pack("2 ml Amp 25 Ampoules") == (25, 2.0) and pack("3 ml Amp (10 Amp)") == (10, 3.0) and pack("Vial") == (1, None)
    assert pack("10X3X3 Tab strip/Blister") == (90, None) and key("Cisplatin Injection IP 10 mg per10ml", "Vial")["vol"] == 10.0
    assert pack("100 Ml Bottle") == (1, 100.0) and pack("100") == (100, None)
    k = key("Pheniramine Inj IP 22.75mg /ml [45]", "2 ml Amp 25 Ampoules")
    assert abs(per_unit(37.0, k)["ml"] - 37 / 25 / 2) < 1e-9
    assert key("RITUXIMAB INJ - 600MG/60ML", "VIAL")["vol"] == 60.0
    assert key("Salbutamol Inhalation 100 mcg /dose [371]", "200metered dose container")["doses"] == 200
    print("drug_key ok")
