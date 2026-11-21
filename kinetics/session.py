"""The QObject bridge: holds the dose schedule and exposes curves to QML."""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import Property, QObject, Signal, Slot

from . import model, pk


class Session(QObject):
    curveChanged = Signal()
    dosesChanged = Signal()
    substanceChanged = Signal()
    personChanged = Signal()
    cursorChanged = Signal()

    def __init__(self):
        super().__init__()
        self._subs = model.load_substances()
        self._person = model.Person.load()
        self._sid = "caffeine"
        self._route = self._subs[self._sid].default_route
        self._hours = 24.0
        self._cursor = 0.0
        self._doses: list[pk.Dose] = []
        self._curve = None
        self._params = None
        self.addDose(0.0, self._subs[self._sid].default_dose, "")

    # ------------------------------------------------------------ internals
    @property
    def sub(self) -> model.Substance:
        return self._subs[self._sid]

    def _recompute(self):
        sub = self.sub
        self._params = model.build_params(sub, self._person, self._route)
        split = (model.napqi_split(sub, self._person)
                 if self._sid == "paracetamol" else None)
        doses = self._doses or [pk.Dose(0.0, 0.0)]
        self._curve = pk.simulate(doses, self._params, hours=self._hours,
                                  metabolite_split=split)
        self.curveChanged.emit()
        self.cursorChanged.emit()   # cursorInfo and bodyState are derived from it

    # ------------------------------------------------------------- the curve
    @Property("QVariantList", notify=curveChanged)
    def series(self):
        """Down-sampled [[t, displayed concentration], ...] for plotting."""
        c, s = self._curve, self.sub.scale
        n = len(c.t)
        step = max(1, n // 700)
        return [[float(c.t[i]), float(c.conc[i] * s)] for i in range(0, n, step)]

    @Property("QVariantMap", notify=curveChanged)
    def stats(self):
        c, p, sub = self._curve, self._params, self.sub
        total = sum(d.amount for d in self._doses)
        out = {
            "cmax": f"{c.cmax * sub.scale:.4g} {sub.unit}",
            "tmax": self.clock(c.tmax),
            "auc": f"{c.auc() * sub.scale:.4g} {sub.unit}·h",
            "totalDose": f"{total:.6g} mg" if total < 1000 else f"{total / 1000:.4g} g",
            "absorbedMg": f"{total * p.f:.4g} mg of {total:.4g} mg "
                          f"({p.f * 100:.0f}%)",
            "vd": f"{p.vd:.1f} L",
            "unit": sub.unit,
            "saturable": p.saturable,
        }
        if p.saturable:
            peak = c.cmax
            rate = p.vmax * peak / (p.km + peak) if peak else 0.0
            out["halfLife"] = "no half-life — saturated elimination"
            out["clearRate"] = (f"{rate * sub.scale:.3f} {sub.unit}/h at the peak "
                                f"(roughly constant)")
            zero = c.crossing(max(peak * 0.02, 1e-6), after=c.tmax)
            out["backToZero"] = self.clock(zero) if zero else "beyond the window"
        elif p.flip_flop:
            # absorption is the slow step, so the tail reports ka, not ke
            out["halfLife"] = (f"{p.apparent_half_life:.2f} h apparent "
                               f"(true elimination: {p.half_life:.2f} h)")
            out["flipFlop"] = (
                "Flip-flop kinetics: this formulation releases the substance more "
                "slowly than the body clears it, so the slope of the tail is the "
                "release rate, not the elimination rate. The level stays up because "
                "it is still arriving, not because it is lingering. Stop the input "
                "and it falls at the true half-life instead.")
            out["clearRate"] = f"ka = {p.ka:.3f} /h (rate-limiting), ke = {p.ke:.3f} /h"
        else:
            out["halfLife"] = f"{p.half_life:.2f} h"
            out["clearRate"] = f"ke = {p.ke:.3f} /h"
            half = c.crossing(c.cmax / 2, after=c.tmax)
            out["halfGone"] = self.clock(half) if half else "beyond the window"
            q = c.crossing(c.cmax / 4, after=c.tmax)
            out["quarterLeft"] = self.clock(q) if q else "beyond the window"
            out["practicallyGone"] = (f"{p.half_life * 5:.1f} h after the last dose "
                                      f"(5 half-lives, about 3% left)")
        return out

    @Property("QVariantList", notify=curveChanged)
    def effectLevels(self):
        sub = self.sub
        return [{"y": lv["conc"] * sub.scale, "label": lv["label"]}
                for lv in sub.raw.get("effect_levels", [])]

    @Property("QVariantMap", notify=cursorChanged)
    def cursorInfo(self):
        return model.describe_phase(self._curve, self._params, self.sub,
                                    self._cursor, self._doses or [pk.Dose(0, 0)])

    @Property("QVariantMap", notify=cursorChanged)
    def bodyState(self):
        """Where the substance is right now — drives the body diagram."""
        c, t = self._curve, self._cursor
        total = max(sum(d.amount for d in self._doses) * self._params.f, 1e-9)
        gut = float(np.interp(t, c.t, c.gut))
        blood = float(np.interp(t, c.t, c.conc)) * self._params.vd
        gone = float(np.interp(t, c.t, c.eliminated))
        mets = {k: float(np.interp(t, c.t, v)) for k, v in c.metabolites.items()}
        return {
            "gut": gut / total, "blood": blood / total, "eliminated": gone / total,
            "gutMg": gut, "bloodMg": blood, "eliminatedMg": gone,
            "metabolites": [{"name": k, "mg": v, "frac": v / total}
                            for k, v in mets.items()],
        }

    # --------------------------------------------------------- the substance
    @Property("QVariantList", constant=True)
    def substances(self):
        return [{"id": s.raw["id"], "name": s.name, "color": s.color,
                 "class": s.raw["class"]} for s in self._subs.values()]

    @Property("QVariantMap", notify=substanceChanged)
    def info(self):
        sub = self.sub
        r = sub.route(self._route)
        return {
            "id": sub.raw["id"], "name": sub.name, "formula": sub.formula,
            "class": sub.raw["class"], "color": sub.color,
            "summary": sub.summary, "mechanism": sub.mechanism,
            "routeNote": r["note"], "unit": sub.unit,
            "bioavailability": r["f"],
            "vdNote": sub.raw.get("vd_note", ""),
            "eliminationNote": sub.raw.get("elimination_note", ""),
            "enzyme": sub.raw["metabolism"]["primary_enzyme"],
            "pathways": sub.raw["metabolism"]["pathways"],
            "sources": sub.raw["sources"],
            "presets": sub.raw["presets"],
            "routes": sub.route_names,
            "route": self._route,
            "defaultDose": sub.raw["default_dose"],
        }

    @Property("QVariantList", notify=personChanged)
    def activeFactors(self):
        return [{"name": n, "note": f.get("note", "")}
                for n, f in self._person.active_factors(self.sub)]

    @Property(str, notify=substanceChanged)
    def substanceId(self):
        return self._sid

    @Slot(str)
    def selectSubstance(self, sid):
        if sid not in self._subs:
            return
        self._sid = sid
        sub = self.sub
        self._route = sub.default_route
        self._doses = [pk.Dose(0.0, sub.raw["default_dose"], self._route)]
        self._hours = 24.0 if sid != "nicotine" else 12.0
        self._cursor = 0.0
        self._recompute()
        self.substanceChanged.emit()
        self.dosesChanged.emit()
        self.personChanged.emit()

    @Slot(str)
    def setRoute(self, route):
        if route in self.sub.raw["routes"]:
            self._route = route
            self._doses = [pk.Dose(d.time, d.amount, route, d.label) for d in self._doses]
            self._recompute()
            self.substanceChanged.emit()
            self.dosesChanged.emit()

    # -------------------------------------------------------------- the doses
    @Property("QVariantList", notify=dosesChanged)
    def doses(self):
        return [{"index": i, "time": d.time, "amount": d.amount,
                 "label": d.label or f"{d.amount:g} mg",
                 "clock": self.clock(d.time)}
                for i, d in enumerate(self._doses)]

    @Slot(float, float, str)
    def addDose(self, time, amount, label):
        self._doses.append(pk.Dose(float(time), float(amount), self._route, label))
        self._doses.sort(key=lambda d: d.time)
        self._recompute()
        self.dosesChanged.emit()

    @Slot(int)
    def removeDose(self, index):
        if 0 <= index < len(self._doses):
            del self._doses[index]
            self._recompute()
            self.dosesChanged.emit()

    @Slot()
    def clearDoses(self):
        self._doses = []
        self._recompute()
        self.dosesChanged.emit()

    @Slot(int, float)
    def moveDose(self, index, time):
        if 0 <= index < len(self._doses):
            d = self._doses[index]
            self._doses[index] = pk.Dose(max(0.0, float(time)), d.amount, d.route, d.label)
            self._doses.sort(key=lambda x: x.time)
            self._recompute()
            self.dosesChanged.emit()

    # -------------------------------------------------------- window, cursor
    @Property(float, notify=curveChanged)
    def hours(self):
        return self._hours

    @Slot(float)
    def setHours(self, h):
        self._hours = max(2.0, min(168.0, float(h)))
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
        """Hours since the first dose, as 'h:mm' plus the day when it runs over."""
        if t is None or (isinstance(t, float) and math.isnan(t)):
            return "—"
        h, m = divmod(round(t * 60), 60)
        if h < 24:
            return f"{int(h)}:{int(m):02d}"
        return f"day {int(h // 24) + 1}, {int(h % 24)}:{int(m):02d}"

    # ------------------------------------------------------------- the person
    @Property("QVariantMap", notify=personChanged)
    def person(self):
        p = self._person
        return {"weight": p.weight_kg, "sex": p.sex, "smoker": p.smoker,
                "chronicAlcohol": p.chronic_alcohol,
                "oralContraceptives": p.oral_contraceptives, "cyp2a6": p.cyp2a6}

    @Slot(str, "QVariant")
    def setPersonField(self, key, value):
        mapping = {"weight": "weight_kg", "sex": "sex", "smoker": "smoker",
                   "chronicAlcohol": "chronic_alcohol",
                   "oralContraceptives": "oral_contraceptives", "cyp2a6": "cyp2a6"}
        attr = mapping.get(key)
        if not attr:
            return
        if attr == "weight_kg":
            value = max(30.0, min(200.0, float(value)))
        setattr(self._person, attr, value)
        self._person.save()
        self._recompute()
        self.personChanged.emit()

    # ------------------------------------------------- comparisons & scenarios
    @Slot(result="QVariantList")
    def compareRoutes(self):
        """The same dose by every available route — the headline nicotine demo."""
        sub = self.sub
        amount = self._doses[0].amount if self._doses else sub.raw["default_dose"]
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
