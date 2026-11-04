#!/usr/bin/env python3
"""Full backtest: 200 simulated nights per Senate and governor race. Prints wrong calls and the
median share of the vote counted when correct calls came. Takes a while; run on the laptop."""
import os, sys, random, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_backtest import ground_truth_races, simulate_night  # noqa: E402

nights = int(sys.argv[1]) if len(sys.argv) > 1 else 200
rng = random.Random(2026)
wrong, calls, late = [], [], 0
for race, units, baselines in ground_truth_races():
    for k in range(nights):
        bad, pct = simulate_night(race, units, baselines, rng, draws=500)
        if bad:
            wrong.append((race["id"], k, pct))
        elif pct is None:
            late += 1
        else:
            calls.append(pct)
    print(f"{race['id']}: done, wrong so far {len(wrong)}", flush=True)
print(f"\nwrong calls: {len(wrong)} {wrong[:10]}")
print(f"correct calls: {len(calls)}, never called before full count: {late}")
if calls:
    print(f"median share counted at call: {statistics.median(calls):.3f}")
