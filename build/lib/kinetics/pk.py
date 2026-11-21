"""Compartmental pharmacokinetics.

Plain numpy + scipy, no Qt, so the model can be tested on its own. Units:

    amount        mg
    volume        L
    concentration mg/L  (= µg/mL, which is how most papers report it)
    time          hours
    rate const    1/h

The model is a depot feeding a central compartment, optionally exchanging with
a peripheral compartment, optionally with an effect site hanging off it:

      depot ──ka──▶ central ──CL──▶ gone
                    ▲    │
                 k21│    │k12          (Q, the intercompartmental clearance)
                    │    ▼
                  peripheral          ···ke0···▶ effect site

**One compartment** (Q = 0) is enough for caffeine or paracetamol: the drug
mixes through the body faster than it is cleared, so the curve is a single
exponential decay. Its single-dose closed form is the Bateman function

    C(t) = F·D·ka / (V·(ka−ke)) · (e^(−ke·t) − e^(−ka·t))

which the tests check the solver against.

**Two compartments** are needed when distribution out of the blood is slow
enough to see — THC moving into fat, fentanyl into muscle, diazepam into
everything. The curve then has a fast distribution phase (alpha) and a slow
terminal phase (beta), and treating it as one compartment would badly
misreport both the early peak and how long traces persist.

**Michaelis–Menten elimination** (alcohol, GHB, and phenytoin in medicine)
replaces the first-order term. The enzyme saturates, so elimination runs at a
near-constant mg/L/h and there is no meaningful half-life.

**The effect site** is a massless compartment that lags the blood by ke0. It is
why the peak of an effect does not coincide with the peak blood level, and why
a level that is already falling can still feel like it is rising. Without it,
any curve shown next to a description of effects is quietly lying about timing.
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
    vd: float                  # central volume V1, L
    cl: float = 0.0            # clearance, L/h
    ka: float = 1.0            # absorption rate, 1/h
    f: float = 1.0             # bioavailability, 0..1
    tlag: float = 0.0          # delay before absorption starts, h
    v2: float = 0.0            # peripheral volume, L (0 = one compartment)
    q: float = 0.0             # intercompartmental clearance, L/h
    ke0: float = 0.0           # effect-site equilibration, 1/h (0 = no lag)
    saturable: bool = False    # Michaelis-Menten elimination
    vmax: float = 0.0          # mg/L/h  (saturable only)
    km: float = 0.0            # mg/L    (saturable only)

    @property
    def ke(self) -> float:
        return self.cl / self.vd if self.vd else 0.0

    @property
    def two_compartment(self) -> bool:
        return self.v2 > 0 and self.q > 0

    @property
    def vss(self) -> float:
        """Volume of distribution at steady state — the whole body's worth."""
        return self.vd + self.v2

    def _macro(self) -> tuple[float, float]:
        """(alpha, beta) hybrid rate constants for the two-compartment model."""
        k10, k12, k21 = self.ke, self.q / self.vd, self.q / self.v2
        s = k10 + k12 + k21
        disc = max(s * s - 4 * k10 * k21, 0.0)
        return (s + math.sqrt(disc)) / 2, (s - math.sqrt(disc)) / 2

    @property
    def half_life(self) -> float:
        """Terminal half-life in hours; NaN when elimination is saturable."""
        if self.saturable or self.ke <= 0:
            return float("nan")
        if self.two_compartment:
            return math.log(2) / self._macro()[1]
        return math.log(2) / self.ke

    @property
    def dist_half_life(self) -> float:
        """The fast distribution half-life; NaN for a one-compartment drug."""
        if not self.two_compartment or self.saturable:
            return float("nan")
        return math.log(2) / self._macro()[0]

    @property
    def flip_flop(self) -> bool:
        """True when absorption is slower than elimination.

        The observed terminal slope is then governed by absorption, so the
        curve's apparent half-life is the absorption half-life — the drug is
        not lingering, it is still trickling in.
        """
        if self.saturable or self.ka <= 0:
            return False
        terminal = math.log(2) / self.half_life if self.half_life > 0 else self.ke
        return self.ka < terminal

    @property
    def apparent_half_life(self) -> float:
        """The half-life you would actually measure off the terminal slope."""
        if self.saturable:
            return float("nan")
        true_rate = math.log(2) / self.half_life
        return math.log(2) / min(self.ka, true_rate) if self.ka > 0 else self.half_life

    @property
    def effect_lag_half_life(self) -> float:
        """How long the effect site takes to catch up halfway. NaN if instant."""
        return math.log(2) / self.ke0 if self.ke0 > 0 else float("nan")


@dataclass
class Curve:
    """The result of a simulation."""
    t: np.ndarray              # hours
    conc: np.ndarray           # mg/L in the central compartment (blood)
    effect: np.ndarray         # mg/L at the effect site
    peripheral: np.ndarray     # mg in the peripheral compartment (tissue/fat)
    absorbed: np.ndarray       # cumulative mg that has reached the blood
    gut: np.ndarray            # mg still waiting to be absorbed
    eliminated: np.ndarray     # cumulative mg cleared
    metabolites: dict = field(default_factory=dict)   # name -> cumulative mg

    def at(self, time: float) -> float:
        return float(np.interp(time, self.t, self.conc))

    def effect_at(self, time: float) -> float:
        return float(np.interp(time, self.t, self.effect))

    @property
    def cmax(self) -> float:
        return float(self.conc.max()) if len(self.conc) else 0.0

    @property
    def tmax(self) -> float:
        return float(self.t[int(self.conc.argmax())]) if len(self.conc) else 0.0

    @property
    def effect_tmax(self) -> float:
        return float(self.t[int(self.effect.argmax())]) if len(self.effect) else 0.0

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

    def duration_above(self, level: float) -> float:
        """Total hours spent above a concentration."""
        return float(np.trapezoid((self.conc >= level).astype(float), self.t))


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

    k12 = params.q / params.vd if params.two_compartment else 0.0
    k21 = params.q / params.v2 if params.two_compartment else 0.0

    # state: [depot, central, peripheral, eliminated, Ce, *metabolites]
    def rhs(t, y):
        depot, central, periph = y[0], max(y[1], 0.0), max(y[2], 0.0)
        ce = y[4]
        conc = central / params.vd
        absorb = params.ka * depot
        if params.saturable:
            elim = (params.vmax * conc / (params.km + conc)) * params.vd if conc > 0 else 0.0
        else:
            elim = params.ke * central
        to_periph = k12 * central
        from_periph = k21 * periph
        d_ce = params.ke0 * (conc - ce) if params.ke0 > 0 else 0.0
        out = [-absorb,
               absorb - elim - to_periph + from_periph,
               to_periph - from_periph,
               elim,
               d_ce]
        if names:
            split = metabolite_split(conc)
            out += [elim * split[n] for n in names]
        return out

    y = np.zeros(5 + len(names))
    ts, ys = [], []
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
                        rtol=1e-8, atol=1e-11, max_step=0.25)
        ts.append(sol.t)
        ys.append(sol.y)
        y = sol.y[:, -1].copy()

    t = np.concatenate(ts)
    yy = np.concatenate(ys, axis=1)
    keep = np.concatenate(([True], np.diff(t) > 1e-12))
    t, yy = t[keep], yy[:, keep]

    central = np.clip(yy[1], 0, None)
    conc = central / params.vd
    effect = np.clip(yy[4], 0, None) if params.ke0 > 0 else conc
    mets = {n: yy[5 + i] for i, n in enumerate(names)}
    return Curve(t=t, conc=conc, effect=effect, peripheral=np.clip(yy[2], 0, None),
                 absorbed=central + yy[2] + yy[3], gut=np.clip(yy[0], 0, None),
                 eliminated=yy[3], metabolites=mets)


def bateman(t, dose_mg: float, params: Params) -> np.ndarray:
    """Closed-form single-dose oral curve — used to verify `simulate`."""
    ka, ke = params.ka, params.ke
    t = np.asarray(t, dtype=float) - params.tlag
    out = np.zeros_like(t)
    m = t > 0
    if abs(ka - ke) < 1e-9:
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
    tablets, and methadone's long tail). The terminal slope of the curve is
    then the *absorption* rate, not the elimination rate, so the drug appears
    to have a far longer half-life than it does.
    """
    def tmax_of(ka):
        if abs(ka - ke) < 1e-12:
            return 1.0 / ke
        return math.log(ka / ke) / (ka - ke)

    lo, hi = ke * 1e-4, ke * 1e4
    if tmax_of(hi) > tmax:
        return hi
    if tmax_of(lo) < tmax:
        return lo
    for _ in range(200):
        mid = math.sqrt(lo * hi)
        if tmax_of(mid) > tmax:
            lo = mid
        else:
            hi = mid
    return math.sqrt(lo * hi)


def fit_ka(target_tmax: float, template: Params, dose: float = 1.0,
           max_iter: int = 40) -> float:
    """Find the absorption rate that puts the peak at `target_tmax`.

    `ka_from_tmax` inverts the one-compartment formula analytically, but that
    formula is wrong as soon as the model is not one compartment. For a
    two-compartment drug the early fall is dominated by distribution, which is
    much faster than elimination, so the analytic ka puts the peak far too
    early — diazepam came out at 46 minutes against a literature 1.2 hours.
    Saturable elimination has no closed form at all.

    Peak time falls monotonically as ka rises, whatever the model underneath,
    so bisecting on a real simulation works for every case and costs a few
    milliseconds once per parameter build.

    `dose` matters only when elimination is saturable: there, the shape of the
    curve genuinely depends on how much was taken, so the fit has to be done at
    a representative dose rather than a nominal 1 mg. For a linear model the
    dose scales out and any value gives the same answer.
    """
    horizon = max(target_tmax * 6, target_tmax + 2.0)

    def tmax_of(ka: float) -> float:
        p = Params(**{**template.__dict__, "ka": ka})
        return simulate([Dose(0.0, dose)], p, hours=horizon, points=900).tmax

    lo, hi = 1e-3, 1e3
    if tmax_of(hi) > target_tmax:
        return hi
    if tmax_of(lo) < target_tmax:
        return lo
    for _ in range(max_iter):
        mid = math.sqrt(lo * hi)
        if tmax_of(mid) > target_tmax:
            lo = mid
        else:
            hi = mid
        if hi / lo < 1.0005:
            break
    return math.sqrt(lo * hi)


def two_compartment(vss: float, cl: float, t_half_term: float,
                    central_fraction: float) -> tuple[float, float, float, float]:
    """Turn the numbers papers report into (V1, V2, CL, Q).

    Clearance and the terminal half-life are the two best-reported quantities
    (clearance because AUC = F·D/CL fixes total exposure), so those are the
    inputs, along with the steady-state volume and how much of it is central.

    Solving instead for the two *half-lives* looks natural and is a trap: the
    residual in Q is U-shaped, so it has two roots or none, and a bisection
    over it silently returns nonsense. Terminal beta, in contrast, rises
    monotonically with Q from 0 towards CL/Vss, so the inversion below is
    well-posed and has exactly one answer.

    That limit is also a real constraint: a two-compartment drug's terminal
    half-life can never be shorter than ln2·Vss/CL. If the requested one is,
    the inputs disagree with each other and we return the closest model we can
    (a very fast exchange, i.e. effectively one compartment).
    """
    v1 = max(vss * central_fraction, 1e-9)
    v2 = max(vss - v1, 1e-9)
    k10 = cl / v1
    want_beta = math.log(2) / t_half_term

    def beta_of(q):
        k12, k21 = q / v1, q / v2
        s = k10 + k12 + k21
        return (s - math.sqrt(max(s * s - 4 * k10 * k21, 0.0))) / 2

    if want_beta >= cl / vss:          # inconsistent inputs: clamp
        return v1, v2, cl, cl * 50.0

    lo, hi = 1e-12, 1.0
    while beta_of(hi) < want_beta and hi < 1e9:
        hi *= 4
    for _ in range(300):
        mid = math.sqrt(lo * hi)
        if beta_of(mid) < want_beta:
            lo = mid
        else:
            hi = mid
    return v1, v2, cl, math.sqrt(lo * hi)
