"""Compartmental pharmacokinetics.

Everything here is plain numpy + scipy and has no Qt in it, so the model can be
tested on its own. Units, consistently:

    amount        mg
    volume        L
    concentration mg/L  (= µg/mL, which is how most papers report it)
    time          hours
    rate const    1/h

The two models:

  * **First-order elimination** (caffeine, nicotine, paracetamol). Absorption is
    first-order with rate ka into a central compartment that empties at ke =
    CL/Vd. With a single dose this has the closed form (Bateman function)

        C(t) = F·D·ka / (Vd·(ka−ke)) · (e^(−ke·t) − e^(−ka·t))

    which we use to check the solver.

  * **Michaelis–Menten elimination** (alcohol). The enzyme that clears it
    saturates almost immediately, so elimination runs at a near-constant
    mg/L/h rather than halving at a fixed interval. There is no useful
    half-life, and no closed form; it has to be integrated.

        dC/dt = −Vmax·C/(Km + C)

Doses are given as a schedule, so several intakes accumulate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.integrate import solve_ivp


@dataclass(frozen=True)
class Dose:
    """One intake: `amount` mg of the parent substance, taken at `time` h."""
    time: float
    amount: float
    route: str = "oral"
    label: str = ""


@dataclass
class Params:
    """The per-person, per-substance numbers the curve is computed from."""
    vd: float                  # volume of distribution, L
    cl: float = 0.0            # clearance, L/h (first-order models)
    ka: float = 1.0            # absorption rate, 1/h
    f: float = 1.0             # bioavailability, 0..1
    tlag: float = 0.0          # delay before absorption starts, h
    saturable: bool = False    # use Michaelis-Menten elimination
    vmax: float = 0.0          # mg/L/h  (saturable only)
    km: float = 0.0            # mg/L    (saturable only)

    @property
    def ke(self) -> float:
        return self.cl / self.vd if self.vd else 0.0

    @property
    def half_life(self) -> float:
        """True elimination half-life in hours; NaN when elimination is saturable."""
        if self.saturable or self.ke <= 0:
            return float("nan")
        return math.log(2) / self.ke

    @property
    def flip_flop(self) -> bool:
        """True when absorption is slower than elimination.

        The observed terminal slope is then governed by absorption, so the
        curve's apparent half-life is the absorption half-life — the drug is
        not lingering, it is still trickling in.
        """
        return not self.saturable and 0 < self.ka < self.ke

    @property
    def apparent_half_life(self) -> float:
        """The half-life you would actually measure off the terminal slope."""
        if self.saturable:
            return float("nan")
        rate = min(self.ka, self.ke) if self.ka > 0 else self.ke
        return math.log(2) / rate


@dataclass
class Curve:
    """The result of a simulation."""
    t: np.ndarray              # hours
    conc: np.ndarray           # mg/L in the central compartment
    absorbed: np.ndarray       # cumulative mg that has reached the blood
    gut: np.ndarray            # mg still waiting to be absorbed
    eliminated: np.ndarray     # cumulative mg cleared
    metabolites: dict = field(default_factory=dict)   # name -> cumulative mg

    def at(self, time: float) -> float:
        """Concentration at an arbitrary time, interpolated."""
        return float(np.interp(time, self.t, self.conc))

    @property
    def cmax(self) -> float:
        return float(self.conc.max()) if len(self.conc) else 0.0

    @property
    def tmax(self) -> float:
        return float(self.t[int(self.conc.argmax())]) if len(self.conc) else 0.0

    def auc(self) -> float:
        """Area under the curve, mg·h/L — total exposure."""
        return float(np.trapezoid(self.conc, self.t))

    def crossing(self, level: float, after: float = 0.0, falling: bool = True):
        """When the curve next passes `level` after `after`. None if it never does."""
        idx = np.searchsorted(self.t, after)
        for i in range(max(idx, 1), len(self.t)):
            a, b = self.conc[i - 1], self.conc[i]
            if (falling and a >= level > b) or (not falling and a <= level < b):
                if b == a:
                    return float(self.t[i])
                frac = (level - a) / (b - a)
                return float(self.t[i - 1] + frac * (self.t[i] - self.t[i - 1]))
        return None


def simulate(doses: list[Dose], params: Params, hours: float = 24.0,
             points: int = 2000, metabolite_split=None) -> Curve:
    """Integrate the model over `hours`, starting at t=0.

    `metabolite_split` is an optional callable taking the central concentration
    and returning {name: fraction}; the fractions apportion the eliminated
    amount between pathways (that is what drives the paracetamol/NAPQI view).
    """
    t_eval = np.linspace(0, hours, points)
    doses = sorted(doses, key=lambda d: d.time)
    names = list(metabolite_split(0.0)) if metabolite_split else []

    # state: [gut amount, central amount, cumulative eliminated, *metabolites]
    def rhs(t, y):
        gut, central = y[0], max(y[1], 0.0)
        conc = central / params.vd
        absorb = params.ka * gut
        if params.saturable:
            elim_conc_rate = params.vmax * conc / (params.km + conc) if conc > 0 else 0.0
            elim = elim_conc_rate * params.vd
        else:
            elim = params.ke * central
        out = [-absorb, absorb - elim, elim]
        if names:
            split = metabolite_split(conc)
            out += [elim * split[n] for n in names]
        return out

    y = np.zeros(3 + len(names))
    ts, ys = [], []
    # integrate between dose times, adding each dose to the gut as we pass it
    events = sorted({0.0, hours} | {d.time + params.tlag for d in doses if d.time < hours})
    for i in range(len(events) - 1):
        t0, t1 = events[i], events[i + 1]
        for d in doses:
            if abs(d.time + params.tlag - t0) < 1e-9:
                if d.route == "iv":
                    y[1] += d.amount          # straight into the blood
                else:
                    y[0] += d.amount * params.f
        seg = t_eval[(t_eval >= t0) & (t_eval <= t1)]
        if len(seg) == 0 or seg[-1] < t1:
            seg = np.append(seg, t1)
        sol = solve_ivp(rhs, (t0, t1), y, t_eval=seg, method="LSODA",
                        rtol=1e-8, atol=1e-10, max_step=0.25)
        ts.append(sol.t)
        ys.append(sol.y)
        y = sol.y[:, -1].copy()

    t = np.concatenate(ts)
    yy = np.concatenate(ys, axis=1)
    # drop the duplicated boundary samples
    keep = np.concatenate(([True], np.diff(t) > 1e-12))
    t, yy = t[keep], yy[:, keep]

    conc = np.clip(yy[1], 0, None) / params.vd
    mets = {n: yy[3 + i] for i, n in enumerate(names)}
    return Curve(t=t, conc=conc, absorbed=np.clip(yy[1], 0, None) + yy[2],
                 gut=np.clip(yy[0], 0, None), eliminated=yy[2], metabolites=mets)


def bateman(t, dose_mg: float, params: Params) -> np.ndarray:
    """Closed-form single-dose oral curve — used to verify `simulate`."""
    ka, ke = params.ka, params.ke
    t = np.asarray(t, dtype=float) - params.tlag
    out = np.zeros_like(t)
    m = t > 0
    if abs(ka - ke) < 1e-9:   # the degenerate case ka == ke
        out[m] = params.f * dose_mg / params.vd * ke * t[m] * np.exp(-ke * t[m])
    else:
        out[m] = (params.f * dose_mg * ka / (params.vd * (ka - ke))
                  * (np.exp(-ke * t[m]) - np.exp(-ka * t[m])))
    return out


def ka_from_tmax(tmax: float, ke: float) -> float:
    """Invert tmax = ln(ka/ke)/(ka−ke) to get the absorption rate.

    tmax decreases monotonically in ka across the whole positive range
    (→∞ as ka→0, = 1/ke at ka = ke, →0 as ka→∞), so one bisection in log
    space covers both the ordinary case and the flip-flop case.

    **Flip-flop kinetics:** when the requested tmax exceeds 1/ke, the only
    solution has ka < ke — absorption slower than elimination. That is a real
    and common situation (nicotine patches, depot injections, extended-release
    tablets). The terminal slope of the curve is then the *absorption* rate,
    not the elimination rate, so the drug appears to have a far longer
    half-life than it does. Refusing ka < ke here would have silently given
    the wrong curve for every slow-release formulation.
    """
    def tmax_of(ka):
        if abs(ka - ke) < 1e-12:
            return 1.0 / ke
        return math.log(ka / ke) / (ka - ke)

    lo, hi = ke * 1e-4, ke * 1e4
    if tmax_of(hi) > tmax:      # absorption can't be made fast enough
        return hi
    if tmax_of(lo) < tmax:      # nor slow enough
        return lo
    for _ in range(200):
        mid = math.sqrt(lo * hi)
        if tmax_of(mid) > tmax:
            lo = mid
        else:
            hi = mid
    return math.sqrt(lo * hi)


def time_to_fraction(params: Params, fraction: float) -> float:
    """Hours for the terminal phase to fall to `fraction` of its value."""
    if params.saturable or params.ke <= 0:
        return float("nan")
    return -math.log(fraction) / params.ke
