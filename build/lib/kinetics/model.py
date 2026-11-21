"""Substance definitions, the person, parameter building, and interactions."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import pk

DATA_DIR = Path(__file__).resolve().parent / "data"
CONFIG = Path.home() / ".config" / "kinetics" / "person.json"

# Order defines the sidebar; categories group it.
SUBSTANCE_ORDER = [
    "caffeine", "nicotine", "alcohol", "paracetamol",
    "cocaine", "amphetamine", "mdma",
    "heroin", "morphine", "codeine", "methadone", "fentanyl",
    "diazepam", "alprazolam", "ghb",
    "ketamine", "lsd", "psilocybin", "thc",
    "fluoxetine",
]

CATEGORY_ORDER = ["Everyday", "Stimulants", "Opioids", "Depressants",
                  "Dissociatives", "Psychedelics", "Cannabinoids", "Psychiatric"]

SEVERITY_RANK = {"danger": 0, "caution": 1, "note": 2}


# --------------------------------------------------------------- substances

@dataclass
class Substance:
    raw: dict

    def __getattr__(self, key):
        try:
            return self.raw[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    @property
    def category(self) -> str:
        return self.raw.get("category", "Everyday")

    @property
    def unit(self) -> str:
        return self.raw.get("display_unit", "mg/L")

    @property
    def scale(self) -> float:
        """Multiply an internal mg/L concentration by this for display."""
        return self.raw.get("display_scale", 1.0)

    def route(self, name: str) -> dict:
        return self.raw["routes"].get(name) or next(iter(self.raw["routes"].values()))

    @property
    def route_names(self) -> list[str]:
        return list(self.raw["routes"])


def load_substances() -> dict[str, Substance]:
    out = {}
    for sid in SUBSTANCE_ORDER:
        path = DATA_DIR / f"{sid}.json"
        if path.exists():
            out[sid] = Substance(json.loads(path.read_text()))
    return out


def load_tags() -> dict[str, list[str]]:
    return json.loads((DATA_DIR / "tags.json").read_text())["tags"]


def load_interactions() -> list[dict]:
    return json.loads((DATA_DIR / "interactions.json").read_text())["interactions"]


# ------------------------------------------------------------------- person

@dataclass
class Person:
    weight_kg: float = 70.0
    sex: str = "male"
    smoker: bool = False
    chronic_alcohol: bool = False
    oral_contraceptives: bool = False
    cyp2a6: str = "normal"         # slow | normal | fast
    cyp2d6: str = "normal"         # poor | normal | ultrarapid
    urine_ph: str = "normal"       # acidic | normal | alkaline
    renal_impairment: bool = False
    opioid_tolerant: bool = False
    flags: set = field(default_factory=set)

    @classmethod
    def load(cls) -> "Person":
        try:
            raw = json.loads(CONFIG.read_text())
            raw.pop("flags", None)
            known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
            return cls(**known)
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self):
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        data = {k: v for k, v in self.__dict__.items() if k != "flags"}
        CONFIG.write_text(json.dumps(data, indent=2))

    def active_factors(self, sub: Substance) -> list[tuple[str, dict]]:
        """Which of this substance's documented factors apply to this person."""
        avail = sub.raw.get("factors", {})
        picked = []

        def take(key, label):
            if key in avail:
                picked.append((label, avail[key]))

        if self.smoker:
            take("smoker", "Smoker")
        if self.oral_contraceptives:
            take("oral_contraceptives", "Oral contraceptives")
        if self.chronic_alcohol:
            take("chronic_heavy", "Regular heavy drinking")
            take("chronic_alcohol", "Regular heavy drinking")
        if self.sex == "female":
            take("female", "Female body-water fraction")
        if self.cyp2a6 != "normal":
            take(f"cyp2a6_{self.cyp2a6}", f"CYP2A6 {self.cyp2a6} metabolizer")
        if self.cyp2d6 != "normal":
            take(f"cyp2d6_{self.cyp2d6}", f"CYP2D6 {self.cyp2d6} metabolizer")
        if self.urine_ph != "normal":
            take(f"{self.urine_ph}_urine", f"{self.urine_ph.title()} urine")
        return picked


_PARAM_CACHE: dict = {}


def build_params(sub: Substance, person: Person, route: str) -> pk.Params:
    """Turn literature values plus this person's characteristics into model parameters.

    Cached, because fitting ka runs a few dozen short simulations.
    """
    key = (sub.raw["id"], route, repr(sorted(
        (k, v) for k, v in person.__dict__.items() if k != "flags")))
    hit = _PARAM_CACHE.get(key)
    if hit is not None:
        return hit
    out = _build_params(sub, person, route)
    _PARAM_CACHE[key] = out
    return out


def _build_params(sub: Substance, person: Person, route: str) -> pk.Params:
    r = sub.route(route)
    factors = person.active_factors(sub)

    vd_per_kg = sub.raw["vd_per_kg"]
    for _, f in factors:
        vd_per_kg = f.get("vd_per_kg", vd_per_kg)
    vss = vd_per_kg * person.weight_kg

    ke0 = (math.log(2) / sub.raw["ke0_half_life"]
           if sub.raw.get("ke0_half_life") else 0.0)

    # --- saturable (alcohol, GHB)
    if sub.raw.get("saturable"):
        vmax = sub.raw["vmax"]
        for _, f in factors:
            vmax *= f.get("vmax_multiplier", 1.0)
        # With saturable elimination the time to peak depends on the dose, so
        # fitting ka to a nominal tmax would bake one dose into the parameter.
        # Papers report an absorption half-life for these drugs; use it directly
        # and let tmax come out of the model.
        ka = math.log(2) / r["absorption_half_life"]
        return pk.Params(vd=vss, ka=ka, f=r["f"], tlag=r.get("tlag", 0.0),
                         ke0=ke0, saturable=True, vmax=vmax, km=sub.raw["km"])

    half_life = sub.raw["half_life"]
    cl_mult = 1.0
    for _, f in factors:
        cl_mult *= f.get("cl_multiplier", 1.0)

    # --- two compartment (THC, fentanyl, diazepam, ketamine)
    if "two_compartment" in sub.raw:
        cl = sub.raw["cl_per_kg"] * person.weight_kg * cl_mult
        cf = sub.raw["two_compartment"]["central_fraction"]
        v1, v2, cl, q = pk.two_compartment(vss, cl, half_life, cf)
        tmpl = pk.Params(vd=v1, v2=v2, cl=cl, q=q, ka=1.0, f=r["f"], tlag=0.0, ke0=ke0)
        ka = pk.fit_ka(max(r["tmax"], 0.02), tmpl)
        return pk.Params(vd=v1, v2=v2, cl=cl, q=q, ka=ka, f=r["f"],
                         tlag=r.get("tlag", 0.0), ke0=ke0)

    # --- one compartment
    cl = vss * math.log(2) / half_life * cl_mult
    ke = cl / vss
    ka = pk.ka_from_tmax(max(r["tmax"], 0.01), ke)
    return pk.Params(vd=vss, cl=cl, ka=ka, f=r["f"], tlag=r.get("tlag", 0.0), ke0=ke0)


def metabolite_split(sub: Substance, person: Person):
    """Fraction of eliminated drug going down each pathway."""
    paths = sub.raw["metabolism"]["pathways"]
    base = {p["name"]: p["fraction"] for p in paths}
    if not base:
        return None

    napqi_mult = 1.0
    morphine_mult = 1.0
    for _, f in person.active_factors(sub):
        napqi_mult *= f.get("napqi_multiplier", 1.0)
        morphine_mult *= f.get("morphine_multiplier", 1.0)

    def split(_conc):
        out = dict(base)
        for key, mult in ((("NAPQI",), napqi_mult), (("Morphine (via",), morphine_mult)):
            if mult == 1.0:
                continue
            target = next((k for k in out if any(k.startswith(p) for p in key)), None)
            if target is None:
                continue
            extra = out[target] * (mult - 1.0)
            out[target] = max(0.0, out[target] + extra)
            # take it from the bulk inactive routes, which are what shift
            donors = [k for k in out if k != target and out[k] > 0]
            if donors and extra != 0:
                per = extra / len(donors)
                for d in donors:
                    out[d] = max(0.0, out[d] - per)
        total = sum(out.values()) or 1.0
        return {k: v / total for k, v in out.items()}

    return split


# -------------------------------------------------------------- interactions

def find_interactions(substance_ids: list[str]) -> list[dict]:
    """Rules that apply to the set of substances currently on the timeline."""
    tags = load_tags()
    rules = load_interactions()
    present = list(dict.fromkeys(substance_ids))

    def matches(token: str, sid: str) -> bool:
        if token.startswith("tag:"):
            return token[4:] in tags.get(sid, [])
        return token == sid

    hits = []
    for rule in rules:
        a, b = rule["between"]
        pair = None
        for i, s1 in enumerate(present):
            for j, s2 in enumerate(present):
                if i == j and a != b:
                    continue
                if i == j:
                    continue
                if matches(a, s1) and matches(b, s2):
                    pair = (s1, s2)
                    break
            if pair:
                break
        if pair:
            hits.append({**rule, "pair": list(pair)})

    # de-duplicate: the same title can match through several tag routes
    seen, out = set(), []
    for h in sorted(hits, key=lambda r: SEVERITY_RANK.get(r["severity"], 9)):
        if h["title"] in seen:
            continue
        seen.add(h["title"])
        out.append(h)
    return out


# ---------------------------------------------------------- narration text

def describe_phase(curve: pk.Curve, params: pk.Params, sub: Substance,
                   t: float, doses: list[pk.Dose]) -> dict:
    """Plain-language explanation of what is happening at time t."""
    conc = curve.at(t)
    effect = curve.effect_at(t)
    peak_t = curve.tmax
    gut = float(np.interp(t, curve.t, curve.gut))
    total_in = sum(d.amount for d in doses if d.time <= t) * params.f

    first = min((d.time for d in doses), default=0.0) + params.tlag
    if t < first:
        phase, text = "Before", "Nothing taken yet."
    elif gut > 0.02 * max(total_in, 1e-9) and t <= peak_t:
        pct = 100 * (1 - gut / max(total_in, 1e-9))
        phase = "Absorption"
        text = (f"About {pct:.0f}% of what was taken has crossed into the blood. "
                f"Absorption is still outrunning elimination, so the level is climbing.")
    elif abs(t - peak_t) < 0.1:
        phase, text = "Peak", "Absorption and elimination are momentarily equal."
    elif params.saturable:
        rate = params.vmax * conc / (params.km + conc)
        phase = "Elimination"
        text = (f"Falling at roughly {rate * sub.scale:.3g} {sub.unit} per hour. "
                f"The enzyme is saturated, so this rate is nearly flat regardless of "
                f"how high the level is — there is no half-life here.")
    elif params.flip_flop:
        phase = "Elimination"
        text = (f"Falling by half every {params.apparent_half_life:.1f} h — but that is "
                f"the release rate, not the clearance rate. It is still being absorbed; "
                f"the body would clear it in {params.half_life:.1f} h if input stopped.")
    elif params.two_compartment and t < peak_t + params.dist_half_life * 3:
        phase = "Distribution"
        text = (f"Falling fast, but mostly into tissue rather than out of the body — "
                f"the distribution half-life is {params.dist_half_life * 60:.0f} min. "
                f"Once tissue fills, the decline slows to the true "
                f"{params.half_life:.1f} h half-life.")
    else:
        hl = params.half_life
        phase = "Elimination"
        text = (f"Falling by half every {hl:.1f} h. In {hl:.1f} h this will be "
                f"{conc * sub.scale:.3g} → {conc * sub.scale / 2:.3g} {sub.unit}.")

    level = None
    for lv in sub.raw.get("effect_levels", []):
        if conc >= lv["conc"]:
            level = lv["label"]

    lag = ""
    if params.ke0 > 0 and curve.effect_tmax > curve.tmax + 0.05:
        if t < curve.effect_tmax:
            lag = (f"The blood level peaked at +{_hm(curve.tmax)}, but the effect site "
                   f"is still climbing and peaks at +{_hm(curve.effect_tmax)}.")

    return {
        "phase": phase, "text": text, "level": level or "",
        "conc": conc * sub.scale,
        "effect": effect * sub.scale,
        "lagNote": lag,
        "absorbedPct": 100 * (1 - gut / max(total_in, 1e-9)) if total_in else 0.0,
        "inGut": gut,
    }


def _hm(t: float) -> str:
    h, m = divmod(round(t * 60), 60)
    return f"{int(h)}:{int(m):02d}"
