"""Substance definitions, the person, and the QObject that QML talks to."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PySide6.QtCore import Property, QObject, Signal, Slot

from . import pk

DATA_DIR = Path(__file__).resolve().parent / "data"
CONFIG = Path.home() / ".config" / "kinetics" / "person.json"

SUBSTANCE_ORDER = ["caffeine", "nicotine", "alcohol", "paracetamol"]


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
        out[sid] = Substance(json.loads((DATA_DIR / f"{sid}.json").read_text()))
    return out


# ------------------------------------------------------------------- person

@dataclass
class Person:
    weight_kg: float = 70.0
    sex: str = "male"              # affects body water for alcohol
    smoker: bool = False
    chronic_alcohol: bool = False
    oral_contraceptives: bool = False
    cyp2a6: str = "normal"         # slow | normal | fast
    flags: set = field(default_factory=set)

    @classmethod
    def load(cls) -> "Person":
        try:
            raw = json.loads(CONFIG.read_text())
            raw.pop("flags", None)
            return cls(**raw)
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self):
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        data = {k: v for k, v in self.__dict__.items() if k != "flags"}
        CONFIG.write_text(json.dumps(data, indent=2))

    def active_factors(self, sub: Substance) -> list[tuple[str, dict]]:
        """Which of the substance's documented factors apply to this person."""
        avail = sub.raw.get("factors", {})
        picked = []
        if self.smoker and "smoker" in avail:
            picked.append(("Smoker", avail["smoker"]))
        if self.oral_contraceptives and "oral_contraceptives" in avail:
            picked.append(("Oral contraceptives", avail["oral_contraceptives"]))
        if self.chronic_alcohol and "chronic_heavy" in avail:
            picked.append(("Regular heavy drinking", avail["chronic_heavy"]))
        if self.chronic_alcohol and "chronic_alcohol" in avail:
            picked.append(("Regular heavy drinking", avail["chronic_alcohol"]))
        if self.sex == "female" and "female" in avail:
            picked.append(("Female body-water fraction", avail["female"]))
        if self.cyp2a6 != "normal" and f"cyp2a6_{self.cyp2a6}" in avail:
            picked.append((f"CYP2A6 {self.cyp2a6} metabolizer",
                           avail[f"cyp2a6_{self.cyp2a6}"]))
        return picked


def build_params(sub: Substance, person: Person, route: str) -> pk.Params:
    """Turn literature values plus this person's characteristics into model parameters."""
    r = sub.route(route)
    vd_per_kg = sub.raw["vd_per_kg"]
    for _, f in person.active_factors(sub):
        vd_per_kg = f.get("vd_per_kg", vd_per_kg)
    vd = vd_per_kg * person.weight_kg

    if sub.raw.get("saturable"):
        vmax = sub.raw["vmax"]
        for _, f in person.active_factors(sub):
            vmax *= f.get("vmax_multiplier", 1.0)
        # absorption still first-order
        ka = math.log(2) / max(r["tmax"] / 3.0, 0.05)
        return pk.Params(vd=vd, ka=ka, f=r["f"], tlag=r.get("tlag", 0.0),
                         saturable=True, vmax=vmax, km=sub.raw["km"])

    cl = vd * math.log(2) / sub.raw["half_life"]
    for _, f in person.active_factors(sub):
        cl *= f.get("cl_multiplier", 1.0)
    ke = cl / vd
    ka = pk.ka_from_tmax(max(r["tmax"], 0.01), ke)
    return pk.Params(vd=vd, cl=cl, ka=ka, f=r["f"], tlag=r.get("tlag", 0.0))


def napqi_split(sub: Substance, person: Person):
    """Fraction of eliminated drug going down each pathway (paracetamol)."""
    paths = sub.raw["metabolism"]["pathways"]
    base = {p["name"]: p["fraction"] for p in paths}
    mult = 1.0
    for _, f in person.active_factors(sub):
        mult *= f.get("napqi_multiplier", 1.0)

    def split(_conc):
        out = dict(base)
        napqi_key = next(k for k in out if "NAPQI" in k)
        extra = out[napqi_key] * (mult - 1.0)
        out[napqi_key] += extra
        # take the extra out of the conjugation routes, which are what saturate
        for k in ("Glucuronide", "Sulfate"):
            if k in out:
                out[k] = max(0.0, out[k] - extra / 2)
        total = sum(out.values())
        return {k: v / total for k, v in out.items()}

    return split


# ----------------------------------------------------------- narration text

def describe_phase(curve: pk.Curve, params: pk.Params, sub: Substance,
                   t: float, doses: list[pk.Dose]) -> dict:
    """Plain-language explanation of what is happening at time t."""
    conc = curve.at(t)
    peak_t = curve.tmax
    gut = float(np.interp(t, curve.t, curve.gut))
    absorbed = float(np.interp(t, curve.t, curve.absorbed))
    total_in = sum(d.amount for d in doses if d.time <= t) * params.f

    if t < min(d.time for d in doses) + params.tlag:
        phase, text = "Before", "Nothing taken yet."
    elif gut > 0.02 * max(total_in, 1e-9) and t <= peak_t:
        pct = 100 * (1 - gut / max(total_in, 1e-9))
        phase = "Absorption"
        text = (f"About {pct:.0f}% of what was taken has crossed into the blood. "
                f"Absorption is still outrunning elimination, so the level is climbing.")
    elif abs(t - peak_t) < 0.1:
        phase, text = "Peak", "Absorption and elimination are momentarily equal. This is the peak."
    else:
        phase = "Elimination"
        if params.saturable:
            rate = params.vmax * conc / (params.km + conc)
            text = (f"Falling at roughly {rate * sub.scale:.3f} {sub.unit} per hour. "
                    f"The enzyme is saturated, so this rate is nearly flat "
                    f"regardless of how high the level is — there is no half-life here.")
        elif params.flip_flop:
            hl = params.apparent_half_life
            text = (f"Falling by half every {hl:.1f} h — but that is the release rate, "
                    f"not the clearance rate. The substance is still being absorbed; "
                    f"the body itself would clear it in {params.half_life:.1f} h "
                    f"if the input stopped.")
        else:
            hl = params.half_life
            text = (f"Falling by half every {hl:.1f} h. "
                    f"In {hl:.1f} h this will be {conc * sub.scale / 2:.3g} {sub.unit}, "
                    f"and in {hl * 2:.1f} h, {conc * sub.scale / 4:.3g} {sub.unit}.")

    # nearest named effect level at or below the current concentration
    level = None
    for lv in sub.raw.get("effect_levels", []):
        if conc >= lv["conc"]:
            level = lv["label"]
    return {
        "phase": phase, "text": text, "level": level or "",
        "conc": conc * sub.scale,
        "absorbedPct": 100 * absorbed / max(total_in, 1e-9) if total_in else 0.0,
        "inGut": gut,
    }
