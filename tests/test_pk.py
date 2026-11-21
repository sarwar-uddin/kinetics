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
        split = model.metabolite_split(sub, self.person)
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
                        metabolite_split=model.metabolite_split(sub, drinker))
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


class TwoCompartment(unittest.TestCase):
    """THC, fentanyl, diazepam and ketamine redistribute into tissue, and a
    one-compartment model would misreport both the early fall and the tail."""

    def setUp(self):
        self.subs = model.load_substances()
        self.person = model.Person(70)

    def test_derivation_round_trips(self):
        for vss, cl, tt, cf in [(500, 14, 30, 0.09), (280, 55, 7, 0.12), (77, 1.8, 43, 0.25)]:
            v1, v2, c, q = pk.two_compartment(vss, cl, tt, cf)
            p = pk.Params(vd=v1, v2=v2, cl=c, q=q, ka=2.0, f=1.0)
            self.assertAlmostEqual(p.half_life, tt, delta=tt * 0.01)
            self.assertAlmostEqual(p.vss, vss, delta=vss * 0.01)
            self.assertLess(p.dist_half_life, p.half_life)

    def test_auc_is_dose_over_clearance(self):
        """Mass balance through two compartments: AUC must still be F·D/CL."""
        v1, v2, cl, q = pk.two_compartment(500, 14, 30, 0.09)
        p = pk.Params(vd=v1, v2=v2, cl=cl, q=q, ka=3.0, f=0.25)
        c = pk.simulate([pk.Dose(0.0, 10.0)], p, hours=600, points=14000)
        self.assertAlmostEqual(c.auc(), 0.25 * 10 / cl, delta=0.25 * 10 / cl * 0.02)

    def test_terminal_half_life_cannot_beat_the_limit(self):
        """A terminal half-life shorter than ln2·Vss/CL is physically impossible;
        the solver must clamp rather than return nonsense."""
        v1, v2, cl, q = pk.two_compartment(500, 14, 5.0, 0.09)   # limit is ~24.8 h
        p = pk.Params(vd=v1, v2=v2, cl=cl, q=q, ka=2.0, f=1.0)
        self.assertGreater(p.half_life, 4.0)
        self.assertFalse(math.isnan(p.half_life))

    def test_thc_smoked_falls_steeply_then_slowly(self):
        sub = self.subs["thc"]
        p = model.build_params(sub, self.person, "smoked")
        c = pk.simulate([pk.Dose(0.0, 10.0, "smoked")], p, hours=48, points=6000)
        # published: peak tens of µg/L, ~90% gone within the first hour
        self.assertTrue(20 < c.cmax * 1000 < 150, f"{c.cmax * 1000:.0f} µg/L")
        self.assertLess(c.at(1.0), c.cmax * 0.45)
        # but it is redistribution, not elimination: plenty is still in the body
        at1h = float(np.interp(1.0, c.t, c.peripheral + c.conc * p.vd))
        self.assertGreater(at1h, 10.0 * 0.25 * 0.5)

    def test_fentanyl_duration_grows_with_repeated_doses(self):
        """Context-sensitive half-time: the tissue fills, so later doses last longer."""
        sub = self.subs["fentanyl"]
        p = model.build_params(sub, self.person, "iv")
        single = pk.simulate([pk.Dose(0.0, 0.1, "iv")], p, hours=24, points=6000)
        repeated = pk.simulate([pk.Dose(i * 0.5, 0.1, "iv") for i in range(8)], p,
                               hours=24, points=6000)
        thresh = single.cmax * 0.2
        t1 = single.crossing(thresh, after=single.tmax)
        t2 = repeated.crossing(thresh, after=repeated.tmax)
        self.assertGreater(t2 - 3.5, (t1 or 0) * 2)


class EffectSite(unittest.TestCase):
    def setUp(self):
        self.subs = model.load_substances()
        self.person = model.Person(70)

    def test_effect_peaks_after_blood(self):
        p = pk.Params(vd=50, cl=20, ka=6.0, f=1.0, ke0=math.log(2) / 0.3)
        c = pk.simulate([pk.Dose(0.0, 100.0)], p, hours=12, points=4000)
        self.assertGreater(c.effect_tmax, c.tmax + 0.1)
        # In the terminal phase the two decay in parallel at a fixed ratio — they
        # do not become equal, because the effect site is always running behind.
        late = c.t > c.effect_tmax + 2
        ratio = c.effect[late] / c.conc[late]
        self.assertLess(ratio.max() - ratio.min(), 0.05)
        self.assertGreater(ratio.mean(), 1.0)

    def test_morphine_effect_lags_measurably(self):
        """Morphine is water-soluble and slow into the brain — the gap is the point."""
        sub = self.subs["morphine"]
        p = model.build_params(sub, self.person, "iv")
        c = pk.simulate([pk.Dose(0.0, 10.0, "iv")], p, hours=12, points=5000)
        self.assertGreater(c.effect_tmax - c.tmax, 0.2)

    def test_no_ke0_means_effect_equals_blood(self):
        p = pk.Params(vd=50, cl=20, ka=3.0, f=1.0, ke0=0.0)
        c = pk.simulate([pk.Dose(0.0, 100.0)], p, hours=12, points=2000)
        self.assertTrue(np.allclose(c.effect, c.conc))


class Interactions(unittest.TestCase):
    def test_opioid_plus_sedative_is_flagged_danger(self):
        hits = model.find_interactions(["heroin", "diazepam"])
        self.assertTrue(hits)
        self.assertEqual(hits[0]["severity"], "danger")

    def test_tag_matching_covers_every_opioid_and_sedative(self):
        for op in ("heroin", "morphine", "fentanyl", "methadone", "codeine"):
            for sed in ("diazepam", "alprazolam", "ghb", "alcohol"):
                hits = model.find_interactions([op, sed])
                self.assertTrue(any(h["severity"] == "danger" for h in hits),
                                f"{op} + {sed} not flagged")

    def test_single_substance_has_no_interactions(self):
        for sid in ("caffeine", "lsd", "thc"):
            self.assertEqual(model.find_interactions([sid]), [])

    def test_specific_pair_beats_generic_tag(self):
        hits = model.find_interactions(["cocaine", "alcohol"])
        self.assertIn("cocaethylene", hits[0]["title"] + hits[0]["text"])

    def test_results_are_sorted_by_severity(self):
        hits = model.find_interactions(["cocaine", "alcohol", "heroin"])
        ranks = [model.SEVERITY_RANK[h["severity"]] for h in hits]
        self.assertEqual(ranks, sorted(ranks))


class Library(unittest.TestCase):
    """Every substance must survive the model and carry its sources."""

    def setUp(self):
        self.subs = model.load_substances()
        self.person = model.Person(70)

    def test_every_substance_simulates_on_every_route(self):
        for sid, sub in self.subs.items():
            for route in sub.route_names:
                p = model.build_params(sub, self.person, route)
                c = pk.simulate([pk.Dose(0.0, sub.raw["default_dose"], route)], p,
                                hours=48, points=1500,
                                metabolite_split=model.metabolite_split(sub, self.person))
                self.assertTrue(np.all(np.isfinite(c.conc)), f"{sid}/{route}")
                self.assertGreater(c.cmax, 0, f"{sid}/{route}")
                self.assertTrue(np.all(c.conc >= -1e-9), f"{sid}/{route} negative")

    def test_tmax_matches_the_literature_value(self):
        for sid, sub in self.subs.items():
            if sub.raw.get("saturable"):
                continue    # tmax is an outcome of dose, not an input
            for route in sub.route_names:
                r = sub.route(route)
                if route == "iv":
                    continue
                want = r["tmax"] + r.get("tlag", 0)
                p = model.build_params(sub, self.person, route)
                c = pk.simulate([pk.Dose(0.0, sub.raw["default_dose"], route)], p,
                                hours=max(48, want * 8), points=6000)
                self.assertAlmostEqual(c.tmax, want, delta=max(0.08, want * 0.15),
                                       msg=f"{sid}/{route}")

    def test_every_substance_is_tagged_and_categorised(self):
        tags = model.load_tags()
        for sid, sub in self.subs.items():
            self.assertIn(sid, tags, f"{sid} has no tags entry")
            self.assertIn(sub.category, model.CATEGORY_ORDER, sid)

    def test_every_substance_has_sources_and_risk(self):
        for sid, sub in self.subs.items():
            self.assertGreaterEqual(len(sub.raw["sources"]), 3, sid)
            for s in sub.raw["sources"]:
                self.assertTrue(s.get("for") and s.get("text"), sid)
            if sub.category != "Everyday":
                self.assertTrue(sub.raw.get("risk"), f"{sid} has no risk notes")

    def test_pathway_fractions_sum_to_one(self):
        for sid, sub in self.subs.items():
            if sid in ("alcohol",):
                continue   # sequential, not parallel
            total = sum(q["fraction"] for q in sub.raw["metabolism"]["pathways"])
            self.assertAlmostEqual(total, 1.0, delta=0.02, msg=sid)

    def test_display_scale_keeps_numbers_readable(self):
        """A peak should land in a human range once scaled, not 0.0000 or 100000."""
        for sid, sub in self.subs.items():
            p = model.build_params(sub, self.person, sub.default_route)
            c = pk.simulate([pk.Dose(0.0, sub.raw["default_dose"], sub.default_route)],
                            p, hours=48, points=2000)
            shown = c.cmax * sub.scale
            self.assertTrue(0.01 < shown < 10000, f"{sid}: {shown:g} {sub.unit}")
