"""The QObject bridge: holds the timeline of substances and exposes it to QML.

A *track* is one substance with its own route and list of intakes. The timeline
can hold several at once, which is the point: the combinations are where the
real risk lives, and they only become visible when two curves are drawn against
the same clock.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from PySide6.QtCore import Property, QObject, Signal, Slot

from . import model, pk

TRACK_COLORS = ["#e0455a", "#6fb3d9", "#d9a441", "#7fc47f", "#b08fd9", "#e8945a"]


@dataclass
class Track:
    sid: str
    route: str
    doses: list = field(default_factory=list)
    curve: pk.Curve | None = None
    params: pk.Params | None = None


class Session(QObject):
    curveChanged = Signal()
    tracksChanged = Signal()
    substanceChanged = Signal()
    personChanged = Signal()
    cursorChanged = Signal()

    def __init__(self):
        super().__init__()
        self._subs = model.load_substances()
        self._person = model.Person.load()
        self._hours = 24.0
        self._cursor = 0.0
        self._active = 0
        self._show_effect = True
        self._tracks: list[Track] = []
        self._add_track("caffeine")

    # ------------------------------------------------------------ internals
    @property
    def _t(self) -> Track:
        return self._tracks[min(self._active, len(self._tracks) - 1)]

    @property
    def sub(self) -> model.Substance:
        return self._subs[self._t.sid]

    def _add_track(self, sid: str):
        s = self._subs[sid]
        label = s.raw["presets"][0]["label"] if s.raw.get("presets") else ""
        t = Track(sid=sid, route=s.default_route,
                  doses=[pk.Dose(0.0, s.raw["default_dose"], s.default_route, label)])
        self._tracks.append(t)
        self._active = len(self._tracks) - 1
        self._recompute()

    def _recompute(self):
        for t in self._tracks:
            s = self._subs[t.sid]
            t.params = model.build_params(s, self._person, t.route)
            split = model.metabolite_split(s, self._person)
            doses = t.doses or [pk.Dose(0.0, 0.0, t.route)]
            t.curve = pk.simulate(doses, t.params, hours=self._hours,
                                  metabolite_split=split)
        self.curveChanged.emit()
        self.cursorChanged.emit()
        self.tracksChanged.emit()

    # ------------------------------------------------------------- the plot
    @Property("QVariantList", notify=curveChanged)
    def series(self):
        """One entry per track. `points` are in display units; `rel` is 0..1 of
        that track's own peak, used when several substances share the plot."""
        out = []
        for i, t in enumerate(self._tracks):
            s = self._subs[t.sid]
            c = t.curve
            n = len(c.t)
            step = max(1, n // 650)
            peak = c.cmax or 1.0
            pts, rel, eff = [], [], []
            for k in range(0, n, step):
                pts.append([float(c.t[k]), float(c.conc[k] * s.scale)])
                rel.append([float(c.t[k]), float(c.conc[k] / peak)])
                eff.append([float(c.t[k]), float(c.effect[k] / peak)])
            out.append({
                "index": i, "name": s.name, "sid": t.sid,
                "color": TRACK_COLORS[i % len(TRACK_COLORS)],
                "unit": s.unit, "points": pts, "rel": rel, "effect": eff,
                "active": i == self._active,
                "hasEffectLag": t.params.ke0 > 0 and c.effect_tmax > c.tmax + 0.05,
            })
        return out

    @Property(bool, notify=tracksChanged)
    def mixed(self):
        return len(self._tracks) > 1

    @Property(bool, notify=curveChanged)
    def showEffect(self):
        return self._show_effect

    @Slot(bool)
    def setShowEffect(self, v):
        self._show_effect = bool(v)
        self.curveChanged.emit()

    @Property("QVariantList", notify=curveChanged)
    def effectLevels(self):
        if len(self._tracks) > 1:
            return []
        s = self.sub
        return [{"y": lv["conc"] * s.scale, "label": lv["label"]}
                for lv in s.raw.get("effect_levels", [])]

    # ---------------------------------------------------------- the numbers
    @Property("QVariantMap", notify=curveChanged)
    def stats(self):
        t = self._t
        c, p, sub = t.curve, t.params, self.sub
        total = sum(d.amount for d in t.doses)
        out = {
            "cmax": f"{c.cmax * sub.scale:.4g} {sub.unit}",
            "tmax": self.clock(c.tmax),
            "auc": f"{c.auc() * sub.scale:.4g} {sub.unit}·h",
            "totalDose": f"{total:.6g} mg",
            "absorbedMg": f"{total * p.f:.4g} mg of {total:.4g} mg ({p.f * 100:.0f}%)",
            "vd": f"{p.vss:.1f} L" + (f" (central {p.vd:.1f} L)" if p.two_compartment else ""),
            "unit": sub.unit,
            "saturable": p.saturable,
            "twoCompartment": p.two_compartment,
        }
        if p.saturable:
            peak = c.cmax
            rate = p.vmax * peak / (p.km + peak) if peak else 0.0
            out["halfLife"] = "no half-life — saturated elimination"
            out["clearRate"] = f"{rate * sub.scale:.3g} {sub.unit}/h at the peak (roughly constant)"
            zero = c.crossing(max(peak * 0.02, 1e-9), after=c.tmax)
            out["backToZero"] = self.clock(zero) if zero else "beyond the window"
        else:
            if p.flip_flop:
                out["halfLife"] = (f"{p.apparent_half_life:.2f} h apparent "
                                   f"(true: {p.half_life:.2f} h)")
                out["flipFlop"] = (
                    "Flip-flop kinetics: this formulation releases the substance more "
                    "slowly than the body clears it, so the slope of the tail is the "
                    "release rate, not the elimination rate. The level stays up because "
                    "it is still arriving, not because it is lingering.")
            else:
                out["halfLife"] = f"{p.half_life:.2f} h"
            out["clearRate"] = f"ke = {p.ke:.3g} /h"
            if p.two_compartment:
                out["distHalfLife"] = (f"{p.dist_half_life * 60:.0f} min "
                                       f"(into tissue, not out of the body)")
            half = c.crossing(c.cmax / 2, after=c.tmax)
            out["halfGone"] = self.clock(half) if half else "beyond the window"
            out["practicallyGone"] = (f"{p.half_life * 5:.1f} h after the last dose "
                                      f"(5 half-lives, about 3% left)")
        if p.ke0 > 0:
            out["effectPeak"] = self.clock(c.effect_tmax)
            out["effectLag"] = f"{p.effect_lag_half_life * 60:.0f} min to half-equilibrate"
        return out

    @Property("QVariantMap", notify=cursorChanged)
    def cursorInfo(self):
        t = self._t
        return model.describe_phase(t.curve, t.params, self.sub, self._cursor,
                                    t.doses or [pk.Dose(0, 0)])

    @Property("QVariantMap", notify=cursorChanged)
    def bodyState(self):
        """Where the substance is at the cursor — drives the body figure."""
        t = self._t
        c, p = t.curve, t.params
        cur = self._cursor
        total = max(sum(d.amount for d in t.doses) * p.f, 1e-9)
        gut = float(np.interp(cur, c.t, c.gut))
        blood = float(np.interp(cur, c.t, c.conc)) * p.vd
        periph = float(np.interp(cur, c.t, c.peripheral))
        gone = float(np.interp(cur, c.t, c.eliminated))
        eff = float(np.interp(cur, c.t, c.effect))
        peak_eff = max(float(c.effect.max()), 1e-12)
        mets = {k: float(np.interp(cur, c.t, v)) for k, v in c.metabolites.items()}
        paths = self.sub.raw["metabolism"]["pathways"]
        active = {q["name"] for q in paths if q.get("active")}
        danger = {q["name"] for q in paths if q.get("danger")}
        return {
            "gut": gut / total, "blood": blood / total,
            "peripheral": periph / total, "eliminated": gone / total,
            "brain": eff / peak_eff,
            "gutMg": gut, "bloodMg": blood, "peripheralMg": periph,
            "eliminatedMg": gone,
            "twoCompartment": p.two_compartment,
            "route": t.route,
            "color": TRACK_COLORS[self._active % len(TRACK_COLORS)],
            "enzyme": self.sub.raw["metabolism"]["primary_enzyme"],
            "firstPassPct": round((1 - p.f) * 100),
            "metabolites": [{"name": k, "mg": v, "frac": v / total,
                             "active": k in active, "danger": k in danger}
                            for k, v in mets.items()],
        }

    # ------------------------------------------------------------- the info
    @Property("QVariantList", constant=True)
    def substances(self):
        out = []
        for cat in model.CATEGORY_ORDER:
            for s in self._subs.values():
                if s.category == cat:
                    out.append({"id": s.raw["id"], "name": s.name, "color": s.color,
                                "class": s.raw["class"], "category": cat})
        return out

    @Property("QVariantList", constant=True)
    def categories(self):
        present = {s.category for s in self._subs.values()}
        return [c for c in model.CATEGORY_ORDER if c in present]

    @Property("QVariantMap", notify=substanceChanged)
    def info(self):
        sub, t = self.sub, self._t
        r = sub.route(t.route)
        return {
            "id": sub.raw["id"], "name": sub.name, "formula": sub.formula,
            "class": sub.raw["class"], "color": sub.color, "category": sub.category,
            "summary": sub.summary, "mechanism": sub.mechanism,
            "routeNote": r["note"], "unit": sub.unit,
            "bioavailability": r["f"],
            "modelNote": sub.raw.get("model_note", ""),
            "uncertainty": sub.raw.get("uncertainty", ""),
            "nonlinear": sub.raw.get("nonlinear", {}).get("note", ""),
            "vdNote": sub.raw.get("vd_note", ""),
            "twoCompartmentNote": sub.raw.get("two_compartment", {}).get("note", ""),
            "eliminationNote": sub.raw.get("elimination_note", ""),
            "enzyme": sub.raw["metabolism"]["primary_enzyme"],
            "pathways": sub.raw["metabolism"]["pathways"],
            "sources": sub.raw["sources"],
            "presets": sub.raw["presets"],
            "risk": sub.raw.get("risk", []),
            "routes": sub.route_names,
            "route": t.route,
        }

    @Property("QVariantList", notify=personChanged)
    def activeFactors(self):
        return [{"name": n, "note": f.get("note", "")}
                for n, f in self._person.active_factors(self.sub)]

    @Property("QVariantList", notify=tracksChanged)
    def interactions(self):
        hits = model.find_interactions([t.sid for t in self._tracks])
        names = {sid: s.name for sid, s in self._subs.items()}
        return [{"severity": h["severity"], "title": h["title"], "text": h["text"],
                 "action": h.get("what_to_do", ""),
                 "pair": " + ".join(names.get(p, p) for p in h["pair"])}
                for h in hits]

    # ------------------------------------------------------------ the tracks
    @Property("QVariantList", notify=tracksChanged)
    def tracks(self):
        out = []
        for i, t in enumerate(self._tracks):
            s = self._subs[t.sid]
            out.append({
                "index": i, "sid": t.sid, "name": s.name,
                "color": TRACK_COLORS[i % len(TRACK_COLORS)],
                "route": t.route, "active": i == self._active,
                "doseCount": len(t.doses),
            })
        return out

    @Property(int, notify=tracksChanged)
    def activeTrack(self):
        return self._active

    def _announce(self):
        self.substanceChanged.emit()
        self.personChanged.emit()

    @Slot(int)
    def selectTrack(self, i):
        if 0 <= i < len(self._tracks):
            self._active = i
            self.tracksChanged.emit()
            self.curveChanged.emit()
            self.cursorChanged.emit()
            self._announce()

    @Slot(str)
    def addTrack(self, sid):
        if sid in self._subs and len(self._tracks) < 6:
            self._add_track(sid)
            self._announce()

    @Slot(int)
    def removeTrack(self, i):
        if 0 <= i < len(self._tracks) and len(self._tracks) > 1:
            del self._tracks[i]
            self._active = min(self._active, len(self._tracks) - 1)
            self._recompute()
            self._announce()

    @Slot(str)
    def selectSubstance(self, sid):
        """Replace the active track's substance."""
        if sid not in self._subs:
            return
        s = self._subs[sid]
        t = self._t
        label = s.raw["presets"][0]["label"] if s.raw.get("presets") else ""
        t.sid = sid
        t.route = s.default_route
        t.doses = [pk.Dose(0.0, s.raw["default_dose"], s.default_route, label)]
        self._recompute()
        self._announce()

    @Slot(str)
    def setRoute(self, route):
        t = self._t
        if route in self._subs[t.sid].raw["routes"]:
            t.route = route
            t.doses = [pk.Dose(d.time, d.amount, route, d.label) for d in t.doses]
            self._recompute()
            self.substanceChanged.emit()

    # -------------------------------------------------------------- the doses
    @Property("QVariantList", notify=tracksChanged)
    def doses(self):
        return [{"index": i, "time": d.time, "amount": d.amount,
                 "label": d.label or f"{d.amount:g} mg",
                 "clock": self.clock(d.time)}
                for i, d in enumerate(self._t.doses)]

    @Slot(float, float, str)
    def addDose(self, time, amount, label):
        t = self._t
        t.doses.append(pk.Dose(float(time), float(amount), t.route, label))
        t.doses.sort(key=lambda d: d.time)
        self._recompute()

    @Slot(int)
    def removeDose(self, index):
        t = self._t
        if 0 <= index < len(t.doses):
            del t.doses[index]
            self._recompute()

    @Slot()
    def clearDoses(self):
        self._t.doses = []
        self._recompute()

    @Slot(float, int, float)
    def repeatDose(self, every_h, times, amount):
        """Add a repeating schedule — the fastest way to see accumulation."""
        t = self._t
        s = self._subs[t.sid]
        amt = amount if amount > 0 else s.raw["default_dose"]
        start = max((d.time for d in t.doses), default=-every_h) + every_h
        for k in range(int(times)):
            t.doses.append(pk.Dose(start + k * every_h, amt, t.route, "repeat"))
        t.doses.sort(key=lambda d: d.time)
        self._recompute()

    # -------------------------------------------------------- window, cursor
    @Property(float, notify=curveChanged)
    def hours(self):
        return self._hours

    @Slot(float)
    def setHours(self, h):
        self._hours = max(2.0, min(720.0, float(h)))
        self._cursor = min(self._cursor, self._hours)
        self._recompute()

    @Property(float, notify=cursorChanged)
    def cursor(self):
        return self._cursor

    @Slot(float)
    def setCursor(self, t):
        self._cursor = max(0.0, min(self._hours, float(t)))
        self.cursorChanged.emit()

    @Slot(float, result=str)
    def clock(self, t):
        if t is None or (isinstance(t, float) and math.isnan(t)):
            return "—"
        h, m = divmod(round(t * 60), 60)
        if h < 24:
            return f"{int(h)}:{int(m):02d}"
        return f"d{int(h // 24) + 1} {int(h % 24)}:{int(m):02d}"

    # --------------------------------------------------------------- person
    @Property("QVariantMap", notify=personChanged)
    def person(self):
        p = self._person
        return {"weight": p.weight_kg, "sex": p.sex, "smoker": p.smoker,
                "chronicAlcohol": p.chronic_alcohol,
                "oralContraceptives": p.oral_contraceptives,
                "cyp2a6": p.cyp2a6, "cyp2d6": p.cyp2d6, "urinePh": p.urine_ph}

    @Slot(str, "QVariant")
    def setPersonField(self, key, value):
        mapping = {"weight": "weight_kg", "sex": "sex", "smoker": "smoker",
                   "chronicAlcohol": "chronic_alcohol",
                   "oralContraceptives": "oral_contraceptives",
                   "cyp2a6": "cyp2a6", "cyp2d6": "cyp2d6", "urinePh": "urine_ph"}
        attr = mapping.get(key)
        if not attr:
            return
        if attr == "weight_kg":
            value = max(30.0, min(200.0, float(value)))
        setattr(self._person, attr, value)
        self._person.save()
        model._PARAM_CACHE.clear()
        self._recompute()
        self.personChanged.emit()

    # ------------------------------------------------------------ comparison
    @Slot(result="QVariantList")
    def compareRoutes(self):
        """The same dose by every available route."""
        t = self._t
        sub = self._subs[t.sid]
        amount = t.doses[0].amount if t.doses else sub.raw["default_dose"]
        out = []
        for route in sub.route_names:
            params = model.build_params(sub, self._person, route)
            curve = pk.simulate([pk.Dose(0.0, amount, route)], params,
                                hours=self._hours, points=900)
            n = len(curve.t)
            step = max(1, n // 400)
            out.append({
                "route": route,
                "note": sub.route(route)["note"],
                "cmax": f"{curve.cmax * sub.scale:.4g} {sub.unit}",
                "tmax": self.clock(curve.tmax),
                "f": f"{params.f * 100:.0f}%",
                "points": [[float(curve.t[i]), float(curve.conc[i] * sub.scale)]
                           for i in range(0, n, step)],
            })
        return out
