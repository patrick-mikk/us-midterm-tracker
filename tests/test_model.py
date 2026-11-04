import unittest
from tests.helpers import make_units, run, race, BASELINES
import model


class ModelStatusTests(unittest.TestCase):
    def test_full_count_is_final(self):
        s = run(make_units(pct=1.0, a_share=0.52))
        self.assertEqual(s["status"], "final")
        self.assertEqual(s["pctExpected"], 1.0)

    def test_two_percent_is_too_early(self):
        s = run(make_units(pct=0.02, a_share=0.70))
        self.assertEqual(s["status"], "too_early")

    def test_big_lead_little_remaining_is_projected(self):
        model.CALLS_ENABLED = True
        s = run(make_units(pct=0.9, a_share=0.62))
        self.assertEqual(s["status"], "projected", s)
        self.assertGreaterEqual(s["candidates"][0]["p"], 0.995)
        self.assertGreaterEqual(s["needs"]["shareOf1_5x"], 0.75)

    def test_narrow_lead_lots_remaining_is_leader(self):
        s = run(make_units(pct=0.4, a_share=0.51))
        self.assertEqual(s["status"], "leader")
        self.assertLess(s["candidates"][0]["p"], 0.995)

    def test_majority_rule_at_49_is_runoff(self):
        units = make_units(pct=0.9, a_share=0.49)
        for u in units:  # add a third candidate so nobody reaches 50%
            counted = sum(c[2] for c in u["candidates"])
            u["candidates"][0][2] = int(counted * 0.49)
            u["candidates"][1][2] = int(counted * 0.45)
            u["candidates"].append(["Cara Ind", "IND", counted - u["candidates"][0][2] - u["candidates"][1][2]])
        s = run(units, rule="majority")
        self.assertEqual(s["status"], "runoff")

    def test_calls_disabled_shows_leader_only(self):
        model.CALLS_ENABLED = False
        try:
            s = run(make_units(pct=0.9, a_share=0.62))
            self.assertEqual(s["status"], "leader")
        finally:
            model.CALLS_ENABLED = True

    def test_withdrawn_projection_stays_visible(self):
        mem = {}
        s1 = run(make_units(pct=0.9, a_share=0.62), memory=mem)
        self.assertEqual(s1["status"], "projected")
        # the count shifts hard against the leader
        s2 = run(make_units(pct=0.92, a_share=0.505), memory=mem)
        self.assertEqual(s2["status"], "withdrawn")
        s3 = run(make_units(pct=0.93, a_share=0.51), memory=mem)
        self.assertEqual(s3["status"], "withdrawn")
        self.assertTrue(any(h["status"] == "withdrawn" for h in s3["callHistory"]))

    def test_needs_line_math(self):
        s = run(make_units(pct=0.5, a_share=0.55))
        n = s["needs"]
        # trailing candidate needs (margin + remaining)/(2*remaining) of the remaining two-party vote
        margin = s["margin"]
        rem = n["remaining"]
        self.assertAlmostEqual(n["share"], (margin + rem) / (2 * rem), places=3)
        self.assertEqual(n["party"], "REP")

    def test_no_votes(self):
        s = run(make_units(pct=0.0))
        self.assertEqual(s["status"], "no_votes")

    def test_late_count_state_waits_longer(self):
        r = race()
        r["lateCount"] = True
        s, m, rows = model.project_race(r, make_units(pct=0.4, a_share=0.65), BASELINES, {}, draws=300)
        self.assertEqual(s["status"], "too_early")

    def test_turnout_factor_learned_from_complete_units(self):
        units = make_units(n=10, pct=1.0, a_share=0.5, size=150000)
        for u in units[5:]:  # half the units have nothing in yet
            u["precinctsReported"] = 0
            for c in u["candidates"]:
                c[2] = 0
        s = run(units)
        # baseline is 100000 per unit; complete units show 150000, so expected is 1.5x
        self.assertAlmostEqual(s["turnoutFactor"], 1.5, places=2)
        self.assertEqual(s["expected"], 1500000)

    def test_histogram_sums_to_draws(self):
        s = run(make_units(pct=0.5, a_share=0.53), draws=400)
        self.assertEqual(sum(s["hist"]["bins"]), 400)


if __name__ == "__main__":
    unittest.main()
