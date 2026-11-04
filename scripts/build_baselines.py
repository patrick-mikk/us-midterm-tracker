#!/usr/bin/env python3
"""Build data/baselines.json.

Two layers:
  1. Statewide priors (always written): approximate 2024 presidential total vote and
     two-party margin per state, scaled to a midterm turnout. These are coarse priors the
     model uses when no county baseline exists. The live turnout factor and county splits
     learned from counted votes override them quickly.
  2. County baselines (optional): pass MEDSL county-level CSVs and this script derives, per
     county FIPS and race type, the total vote and two-party margin.

Usage:
  python3 scripts/build_baselines.py                      # statewide priors only
  python3 scripts/build_baselines.py medsl_2022.csv ...    # add county detail

MEDSL CSV columns used: year, state_po, county_name, county_fips, office, party, candidatevotes.
"""
import csv, json, os, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# (approx 2024 presidential total votes in thousands, REP minus DEM margin in points)
STATE_2024 = {
    "AL": (2270, 30.5), "AK": (340, 13.1), "AZ": (3430, 5.5), "AR": (1180, 30.6), "CA": (15800, -20.1),
    "CO": (3200, -11.0), "CT": (1700, -14.5), "DE": (510, -14.7), "FL": (10800, 13.1), "GA": (5260, 2.2),
    "HI": (520, -23.3), "ID": (900, 36.5), "IL": (5600, -11.0), "IN": (2970, 19.0), "IA": (1670, 13.2),
    "KS": (1330, 16.2), "KY": (2130, 30.5), "LA": (2050, 22.1), "ME": (830, -6.9), "MD": (2970, -29.0),
    "MA": (3500, -25.4), "MI": (5660, 1.4), "MN": (3270, -4.2), "MS": (1230, 22.8), "MO": (3030, 18.4),
    "MT": (600, 19.9), "NE": (950, 20.4), "NV": (1490, 3.1), "NH": (830, -2.8), "NJ": (4190, -5.9),
    "NM": (920, -6.0), "NY": (8400, -12.6), "NC": (5700, 3.2), "ND": (370, 36.6), "OH": (5700, 11.2),
    "OK": (1560, 34.2), "OR": (2270, -14.3), "PA": (7030, 1.7), "RI": (520, -13.8), "SC": (2550, 17.9),
    "SD": (430, 29.6), "TN": (3090, 29.8), "TX": (11330, 13.7), "UT": (1500, 21.6), "VT": (370, -31.9),
    "VA": (4480, -5.8), "WA": (3900, -18.3), "WV": (760, 41.8), "WI": (3420, 0.9), "WY": (270, 45.8),
}
MIDTERM_TURNOUT_RATIO = 0.72  # typical midterm vote relative to the previous presidential election

OFFICE_MAP = {"US SENATE": "us_senate", "US SENATOR": "us_senate", "GOVERNOR": "governor",
              "US HOUSE": "us_house", "US PRESIDENT": "president", "PRESIDENT": "president"}


def county_baselines(paths):
    acc = defaultdict(lambda: defaultdict(lambda: {"total": 0, "dem": 0, "rep": 0, "name": ""}))
    for p in paths:
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                office = OFFICE_MAP.get((row.get("office") or "").upper())
                if not office:
                    continue
                fips = (row.get("county_fips") or "").strip().zfill(5)
                if not fips.isdigit():
                    continue
                try:
                    v = int(float(row.get("candidatevotes") or 0))
                except ValueError:
                    continue
                key = office
                if office == "us_house":
                    key = f"us_house:{(row.get('district') or '').strip().zfill(2)}"
                cell = acc[fips][key]
                cell["total"] += v
                party = (row.get("party") or row.get("party_simplified") or "").upper()
                if party.startswith("DEM"):
                    cell["dem"] += v
                elif party.startswith("REP"):
                    cell["rep"] += v
                cell["name"] = (row.get("county_name") or "").title()
                cell["state"] = row.get("state_po")
    out = {}
    for fips, byoffice in acc.items():
        out[fips] = {"name": next(iter(byoffice.values()))["name"],
                     "state": next(iter(byoffice.values())).get("state"), "races": {}}
        for key, c in byoffice.items():
            two = c["dem"] + c["rep"]
            out[fips]["races"][key] = {"total": c["total"],
                                       "margin": round(100.0 * (c["rep"] - c["dem"]) / two, 2) if two else None}
    return out


def main():
    states = {}
    for st, (kvotes, margin) in STATE_2024.items():
        states[st] = {"total2024": kvotes * 1000, "margin2024": margin,
                      "expectedMidterm": int(kvotes * 1000 * MIDTERM_TURNOUT_RATIO)}
    out = {"note": "Statewide priors are approximate 2024 presidential figures (REP minus DEM, points). "
                   "County detail comes from MEDSL files when provided.",
           "midtermTurnoutRatio": MIDTERM_TURNOUT_RATIO, "states": states, "counties": {}}
    if len(sys.argv) > 1:
        out["counties"] = county_baselines(sys.argv[1:])
        out["countySource"] = "MIT Election Data + Science Lab county returns"
    with open(os.path.join(ROOT, "data", "baselines.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(f"wrote {len(states)} states, {len(out['counties'])} counties")


if __name__ == "__main__":
    main()
