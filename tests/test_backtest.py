"""Backtest: simulated election nights against known ground truth.

Ground truth comes from county baselines (MEDSL 2022, when data/baselines.json has counties) or,
failing that, from the deterministic synthetic world in adapters/demo.py. Counties are revealed in
random order, each partly reported with noise, and the model runs at every step. The model passes
if it never projects the wrong winner. BACKTEST_NIGHTS (default 3) controls the nights per race;
scripts/backtest.py runs the full 200.
"""
import json, os, random, statistics, unittest
from tests.helpers import ROOT, load
import model
from adapters import demo


def ground_truth_races():
    races_doc = load(os.path.join(ROOT, "data", "races.json"))
    baselines = load(os.path.join(ROOT, "data", "baselines.json"))
    out = []
    night = demo.Night(races_doc, baselines, seed=2022)
    for r in races_doc["races"]:
        if r["office"] not in ("us_senate", "governor"):
            continue
        tr = night.truth[r["id"]]
        units = []
        for u in tr["units"]:
            dem = max(0.03, min(0.97, u["dem"] + tr["offset"]))
            total = int(u["size"])
            units.append({"fips": u["fips"], "name": u["name"], "precincts": u["precincts"],
                          "total": total, "dem": int(total * dem), "rep": total - int(total * dem)})
        out.append((r, units, baselines))
    return out


def simulate_night(race, truth_units, baselines, rng, draws=300):
    """Returns (wrong_call, pct_counted_at_correct_call or None)."""
    order = list(range(len(truth_units)))
    rng.shuffle(order)
    revealed = {}
    memory = {}
    true_dem = sum(u["dem"] for u in truth_units)
    true_rep = sum(u["rep"] for u in truth_units)
    true_winner = "DEM" if true_dem > true_rep else "REP"
    first_call = None
    steps = order + order[:: max(1, len(order) // 3)]  # a second pass fills partial counties
    for step, idx in enumerate(steps):
        u = truth_units[idx]
        frac = rng.uniform(0.3, 1.0) if idx not in revealed else 1.0
        # early batches skew DEM, later ones skew REP, so partial counts are biased
        skew = rng.uniform(0.0, 0.06) * (1 - frac)
        dem_c = int(u["dem"] * frac * (1 + skew))
        rep_c = int(u["rep"] * frac * (1 - skew))
        if frac >= 1.0:
            dem_c, rep_c = u["dem"], u["rep"]
        revealed[idx] = (dem_c, rep_c, int(u["precincts"] * frac))
        units = []
        for j, tu in enumerate(truth_units):
            d, r_, p = revealed.get(j, (0, 0, 0))
            units.append({"fips": tu["fips"], "name": tu["name"], "precincts": tu["precincts"], "precinctsReported": p,
                          "candidates": [["Dem Candidate", "DEM", d], ["Rep Candidate", "REP", r_]], "byType": None})
        rc = dict(race)
        rc["lateCount"] = False
        s, m, rows = model.project_race(rc, units, baselines, memory, draws=draws)
        if s["status"] == "projected":
            if s["candidates"][0]["party"] != true_winner:
                return True, s["pctExpected"]
            if first_call is None:
                first_call = s["pctExpected"]
    return False, first_call


class BacktestTests(unittest.TestCase):
    def test_no_wrong_calls(self):
        nights = int(os.environ.get("BACKTEST_NIGHTS", "3"))
        rng = random.Random(7)
        wrong = []
        call_points = []
        for race, units, baselines in ground_truth_races():
            for k in range(nights):
                bad, pct = simulate_night(race, units, baselines, rng)
                if bad:
                    wrong.append((race["id"], k, pct))
                elif pct is not None:
                    call_points.append(pct)
        self.assertEqual(wrong, [], f"wrong projections: {wrong}")
        if call_points:
            print(f"\nbacktest: {len(call_points)} correct calls, median share counted at call "
                  f"{statistics.median(call_points):.2f}")


if __name__ == "__main__":
    unittest.main()
