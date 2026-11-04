#!/usr/bin/env python3
"""Record raw adapter output into fixtures/snapshots/ for replay and tests.

  python3 scripts/record.py            # one snapshot of every live adapter
  python3 scripts/record.py --loop 60  # keep recording every 60 s (Ctrl-C to stop)

Each snapshot is {state: adapter_result}; `fetch.py --replay fixtures/snapshots` steps through them.
"""
import argparse, datetime as dt, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fetch  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures", "snapshots")


def snap():
    results, _ = fetch.run_live_adapters()
    good = {st: r for st, r in results.items() if not isinstance(r, Exception)}
    for st, r in results.items():
        if isinstance(r, Exception):
            print(f"{st}: failed: {r}")
    os.makedirs(OUT, exist_ok=True)
    name = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(good, f, separators=(",", ":"))
    print(f"wrote {name}: {sorted(good)}")


ap = argparse.ArgumentParser()
ap.add_argument("--loop", type=int, default=0)
a = ap.parse_args()
while True:
    snap()
    if not a.loop:
        break
    time.sleep(a.loop)
