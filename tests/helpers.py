import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import model  # noqa: E402

BASELINES = {"states": {"ZZ": {"expectedMidterm": 1000000, "margin2024": 0.0}}, "counties": {}}


def make_units(n=10, a_share=0.55, pct=1.0, size=100000, precincts=100, a=("Alice Dem", "DEM"), b=("Bob Rep", "REP"),
               complete_precincts=None):
    units = []
    for i in range(n):
        counted = int(size * pct)
        av = int(counted * a_share)
        pr = precincts if pct >= 1.0 else int(precincts * pct)
        if complete_precincts is not None:
            pr = complete_precincts
        units.append({"fips": f"ZZ{i:03d}", "name": f"Unit {i}", "precincts": precincts, "precinctsReported": pr,
                      "candidates": [[a[0], a[1], av], [b[0], b[1], counted - av]], "byType": None})
    return units


def race(rule="plurality", office="us_senate"):
    return {"id": "ZZ-SEN-2026", "state": "ZZ", "office": office, "district": None, "winRule": rule,
            "candidates": [], "lateCount": False, "houseSeats": 1}


def run(units, rule="plurality", memory=None, draws=400):
    s, m, rows = model.project_race(race(rule), units, BASELINES, memory if memory is not None else {}, draws=draws)
    return s


def load(path):
    with open(path, encoding="utf-8") as f:
        import json
        return json.load(f)
