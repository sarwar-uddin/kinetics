"""The model has to reproduce textbook pharmacokinetics before the UI is worth anything."""

import math
import unittest

import numpy as np

from kinetics import model, pk


class Solver(unittest.TestCase):
    def test_matches_bateman_closed_form(self):
        p = pk.Params(vd=42.0, cl=5.8, ka=2.5, f=0.99)
        c = pk.simulate([pk.Dose(0.0, 100.0)], p, hours=24, points=4000)
        ref = pk.bateman(c.t, 100.0, p)
        self.assertLess(np.abs(c.conc - ref).max() / ref.max(), 1e-4)

    def test_lag_shifts_without_distorting(self):
        p = pk.Params(vd=40.0, cl=6.0, ka=2.0, f=1.0, tlag=1.5)
        c = pk.simulate([pk.Dose(0.0, 100.0)], p, hours=24, points=3000)
        self.assertAlmostEqual(c.tmax - 1.5, math.log(p.ka / p.ke) / (p.ka - p.ke), places=1)
        self.assertLess(c.at(1.4), 1e-6)

    def test_mass_is_conserved(self):
        p = pk.Params(vd=40.0, cl=6.0, ka=1.5, f=0.8)
        c = pk.simulate([pk.Dose(0.0, 200.0)], p, hours=48, points=3000)
        total = c.gut[-1] + c.conc[-1] * p.vd + c.eliminated[-1]
        self.assertAlmostEqual(total, 200.0 * 0.8, places=3)

    def test_iv_starts_at_peak(self):
        p = pk.Params(vd=50.0, cl=10.0, ka=1.0, f=1.0)
        c = pk.simulate([pk.Dose(0.0, 100.0, route="iv")], p, hours=12, points=2000)
        self.assertLess(c.tmax, 0.05)
        self.assertAlmostEqual(c.cmax, 100.0 / 50.0, places=2)

    def test_repeat_doses_accumulate_to_steady_state(self):
        # dosing every half-life should plateau near twice the single-dose peak
        p = pk.Params(vd=40.0, cl=40 * math.log(2) / 6.0, ka=3.0, f=1.0)
        doses = [pk.Dose(6.0 * i, 100.0) for i in range(12)]
        c = pk.simulate(doses, p, hours=96, points=6000)
        late = c.conc[(c.t > 60) & (c.t < 66)]
        earlier = c.conc[(c.t > 24) & (c.t < 30)]
        self.assertGreater(late.max(), earlier.max() * 0.97)
        self.assertLess(late.max(), earlier.max() * 1.10)   # has plateaued

    def test_ka_from_tmax_round_trips(self):
        for ke in (0.14, 0.35, 0.69):
            for tmax in (0.1, 0.25, 0.75, 2.0, 6.0, 12.0):
                ka = pk.ka_from_tmax(tmax, ke)
                self.assertAlmostEqual(math.log(ka / ke) / (ka - ke), tmax, places=3,
                                       msg=f"ke={ke} tmax={tmax}")

    def test_flip_flop_kinetics(self):
        """When absorption is slower than elimination, the terminal slope reports
        the absorption rate — the apparent half-life is not the real one."""
        ke = math.log(2) / 2.0            # a 2 h drug
        ka = pk.ka_from_tmax(8.0, ke)     # released slowly over 8 h
        p = pk.Params(vd=180.0, cl=180.0 * ke, ka=ka, f=1.0)
        self.assertTrue(p.flip_flop)
        self.assertLess(ka, ke)
        self.assertAlmostEqual(p.half_life, 2.0, places=2)
        self.assertGreater(p.apparent_half_life, 6.0)

        c = pk.simulate([pk.Dose(0.0, 21.0)], p, hours=72, points=6000)
        self.assertAlmostEqual(c.tmax, 8.0, delta=0.3)
        # measure the real terminal slope and confirm it reflects ka, not ke
        seg = (c.t > 40) & (c.t < 70)
        slope = np.polyfit(c.t[seg], np.log(c.conc[seg]), 1)[0]
        self.assertAlmostEqual(-slope, ka, delta=ka * 0.05)


class Saturable(unittest.TestCase):
    """Alcohol: the elimination limb should be a straight line, not an exponential."""

    def setUp(self):
        self.subs = model.load_substances()
        self.person = model.Person(weight_kg=70, sex="male")

    def test_elimination_is_linear(self):
        sub = self.subs["alcohol"]
        p = model.build_params(sub, self.person, "oral")
        c = pk.simulate([pk.Dose(0.0, 42000.0)], p, hours=12, points=4000)
        seg = (c.t > c.tmax + 0.5) & (c.conc > 0.4 * c.cmax)
        t, y = c.t[seg], c.conc[seg]
        fit = np.polyfit(t, y, 1)
        resid = y - np.polyval(fit, t)
        # a straight line fits the decay to within 1% of the peak
        self.assertLess(np.abs(resid).max() / c.cmax, 0.01)
        # and the slope is the published 0.15-0.20 g/L/h
        self.assertTrue(-0.21 < fit[0] / 1000 < -0.14, f"{fit[0] / 1000} g/L/h")

    def test_double_dose_doubles_the_time(self):
        sub = self.subs["alcohol"]
        p = model.build_params(sub, self.person, "oral")
        times = []
        for amount in (28000.0, 56000.0):
            c = pk.simulate([pk.Dose(0.0, amount)], p, hours=30, points=5000)
            times.append(c.crossing(100.0, after=c.tmax))
        # first-order would add one half-life; saturated kinetics roughly doubles
        self.assertGreater(times[1] / times[0], 1.75)

    def test_matches_widmark_by_back_extrapolation(self):
        """Widmark's BAC = F·dose/(weight·r) is the elimination limb extrapolated
        back to t=0, not the peak that is actually reached. The real peak is lower,
        because elimination is already running while the drink is being absorbed."""
        sub = self.subs["alcohol"]
        p = model.build_params(sub, self.person, "oral")
        c = pk.simulate([pk.Dose(0.0, 42000.0)], p, hours=12, points=4000)   # 3 US drinks
        seg = (c.t > c.tmax + 0.5) & (c.conc > 0.4 * c.cmax)
        slope, intercept = np.polyfit(c.t[seg], c.conc[seg], 1)

        widmark = 42000.0 * p.f / (70 * 0.68)
        self.assertAlmostEqual(intercept, widmark, delta=widmark * 0.05)
        # the measured peak sits meaningfully below it
        self.assertLess(c.cmax, intercept * 0.85)
        self.assertTrue(0.05 < c.cmax / 10000.0 < 0.08, f"{c.cmax / 10000:.3f}%")

    def test_female_peaks_higher(self):
        sub = self.subs["alcohol"]
        male = model.build_params(sub, model.Person(70, "male"), "oral")
        female = model.build_params(sub, model.Person(70, "female"), "oral")
        cm = pk.simulate([pk.Dose(0.0, 28000.0)], male, hours=12, points=2000)
        cf = pk.simulate([pk.Dose(0.0, 28000.0)], female, hours=12, points=2000)
        self.assertGreater(cf.cmax, cm.cmax * 1.15)


class PublishedValues(unittest.TestCase):
    """Each substance should reproduce the literature numbers it was built from."""

    def setUp(self):
        self.subs = model.load_substances()
        self.person = model.Person(weight_kg=70, sex="male")

    def test_tmax_and_half_life_round_trip(self):
        for sid in ("caffeine", "nicotine", "paracetamol"):
            sub = self.subs[sid]
            for route in sub.route_names:
                p = model.build_params(sub, self.person, route)
                want_tmax = sub.route(route)["tmax"] + sub.route(route).get("tlag", 0)
                hours = max(24.0, want_tmax * 8)
                c = pk.simulate([pk.Dose(0.0, sub.raw["default_dose"], route)], p,
                                hours=hours, points=6000)
                self.assertAlmostEqual(c.tmax, want_tmax, delta=max(0.05, want_tmax * 0.12),
                                       msg=f"{sid}/{route} tmax")
                self.assertAlmostEqual(p.half_life, sub.raw["half_life"], places=5,
                                       msg=f"{sid} half-life")

    def test_caffeine_coffee_peak_is_realistic(self):
        """One 95 mg coffee should peak around 1.5-2.5 mg/L in a 70 kg adult."""
        sub = self.subs["caffeine"]
        p = model.build_params(sub, self.person, "oral")
        c = pk.simulate([pk.Dose(0.0, 95.0)], p, hours=24, points=3000)
        self.assertTrue(1.5 < c.cmax < 2.5, f"{c.cmax:.2f} mg/L")

    def test_smoking_halves_caffeine_half_life(self):
        sub = self.subs["caffeine"]
        normal = model.build_params(sub, model.Person(70, smoker=False), "oral")
        smoker = model.build_params(sub, model.Person(70, smoker=True), "oral")
        self.assertAlmostEqual(smoker.half_life, normal.half_life / 1.9, places=2)
        self.assertTrue(2.4 < smoker.half_life < 2.8)

    def test_nicotine_routes_rank_by_speed(self):
        """The whole point: same dose, wildly different peak depending on route."""
        sub = self.subs["nicotine"]
        peaks = {}
        for route in ("smoked", "gum", "patch"):
            p = model.build_params(sub, self.person, route)
            c = pk.simulate([pk.Dose(0.0, 2.0, route)], p, hours=24, points=4000)
            peaks[route] = (c.cmax, c.tmax)
        self.assertGreater(peaks["smoked"][0], peaks["gum"][0])
        self.assertGreater(peaks["gum"][0], peaks["patch"][0])
        self.assertLess(peaks["smoked"][1], peaks["patch"][1])
        # the patch spreads the same milligrams over many hours
        self.assertGreater(peaks["smoked"][0] / peaks["patch"][0], 3.0)

    def test_paracetamol_napqi_fraction(self):
        sub = self.subs["paracetamol"]
        p = model.build_params(sub, self.person, "oral")
        split = model.napqi_split(sub, self.person)
        c = pk.simulate([pk.Dose(0.0, 1000.0)], p, hours=24, points=3000,
                        metabolite_split=split)
        napqi = c.metabolites["NAPQI (via CYP2E1)"][-1]
        total = c.eliminated[-1]
        self.assertAlmostEqual(napqi / total, 0.08, delta=0.01)

    def test_chronic_alcohol_doubles_napqi(self):
        sub = self.subs["paracetamol"]
        drinker = model.Person(70, chronic_alcohol=True)
        p = model.build_params(sub, drinker, "oral")
        c = pk.simulate([pk.Dose(0.0, 1000.0)], p, hours=24, points=3000,
                        metabolite_split=model.napqi_split(sub, drinker))
        frac = c.metabolites["NAPQI (via CYP2E1)"][-1] / c.eliminated[-1]
        self.assertTrue(0.14 < frac < 0.18, f"{frac:.3f}")

    def test_pathway_fractions_sum_to_one(self):
        for sid, sub in self.subs.items():
            if sid == "alcohol":
                continue   # sequential, not parallel: ethanol -> acetaldehyde -> acetate
            total = sum(p["fraction"] for p in sub.raw["metabolism"]["pathways"])
            self.assertAlmostEqual(total, 1.0, places=2, msg=sid)

    def test_every_value_has_sources(self):
        for sid, sub in self.subs.items():
            self.assertGreaterEqual(len(sub.raw["sources"]), 3, sid)
            for s in sub.raw["sources"]:
                self.assertIn("for", s)
                self.assertTrue(s["text"].strip())


if __name__ == "__main__":
    unittest.main()
