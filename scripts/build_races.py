#!/usr/bin/env python3
"""Build data/races.json and data/holdovers.json from the tables below.

Run on the laptop:  python3 scripts/build_races.py
Candidates are left empty unless listed in CANDIDATES; live adapters add the
names they see in official feeds. Everything here was cross-checked against the
2026 Senate, House and gubernatorial election lists; re-run after any change.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# ---- Senate seats up in 2026: class 2 plus the Ohio and Florida specials ----
# state: (incumbent party, special?)
SENATE = {
    "AL": ("REP", False), "AK": ("REP", False), "AR": ("REP", False), "CO": ("DEM", False),
    "DE": ("DEM", False), "GA": ("DEM", False), "ID": ("REP", False), "IL": ("DEM", False),
    "IA": ("REP", False), "KS": ("REP", False), "KY": ("REP", False), "LA": ("REP", False),
    "ME": ("REP", False), "MA": ("DEM", False), "MI": ("DEM", False), "MN": ("DEM", False),
    "MS": ("REP", False), "MT": ("REP", False), "NE": ("REP", False), "NH": ("DEM", False),
    "NJ": ("DEM", False), "NM": ("DEM", False), "NC": ("REP", False), "OK": ("REP", False),
    "OR": ("DEM", False), "RI": ("DEM", False), "SC": ("REP", False), "SD": ("REP", False),
    "TN": ("REP", False), "TX": ("REP", False), "VA": ("DEM", False), "WV": ("REP", False),
    "WY": ("REP", False),
    "OH": ("REP", True), "FL": ("REP", True),
}

# ---- Governor races in 2026 (36): incumbent party ----
GOVERNORS = {
    "AL": "REP", "AK": "REP", "AZ": "DEM", "AR": "REP", "CA": "DEM", "CO": "DEM", "CT": "DEM",
    "FL": "REP", "GA": "REP", "HI": "DEM", "ID": "REP", "IL": "DEM", "IA": "REP", "KS": "DEM",
    "ME": "DEM", "MD": "DEM", "MA": "DEM", "MI": "DEM", "MN": "DEM", "NE": "REP", "NV": "REP",
    "NH": "REP", "NM": "DEM", "NY": "DEM", "OH": "REP", "OK": "REP", "OR": "DEM", "PA": "DEM",
    "RI": "DEM", "SC": "REP", "SD": "REP", "TN": "REP", "TX": "REP", "VT": "REP", "WI": "DEM",
    "WY": "REP",
}

# ---- House seats per state (435) ----
HOUSE_SEATS = {
    "AL": 7, "AK": 1, "AZ": 9, "AR": 4, "CA": 52, "CO": 8, "CT": 5, "DE": 1, "FL": 28, "GA": 14,
    "HI": 2, "ID": 2, "IL": 17, "IN": 9, "IA": 4, "KS": 4, "KY": 6, "LA": 6, "ME": 2, "MD": 8,
    "MA": 9, "MI": 13, "MN": 8, "MS": 4, "MO": 8, "MT": 2, "NE": 3, "NV": 4, "NH": 2, "NJ": 12,
    "NM": 3, "NY": 26, "NC": 14, "ND": 1, "OH": 15, "OK": 5, "OR": 6, "PA": 17, "RI": 2, "SC": 7,
    "SD": 1, "TN": 9, "TX": 38, "UT": 4, "VT": 1, "VA": 11, "WA": 10, "WV": 2, "WI": 8, "WY": 1,
}

# ---- Win rules. Georgia holds a general-election runoff below 50%; Maine and
# Alaska use ranked-choice tabulation for these offices. Everything else is plurality.
WIN_RULES = {"GA": "majority", "ME": "rcv", "AK": "rcv"}
# Georgia's governor race also goes to a runoff; Alaska's governor uses RCV; Maine's governor is RCV too.

# ---- Senate holdovers (seats not up in 2026) ----
# After the 2024 cycle: 53 REP, 45 DEM, 2 IND who caucus with the Democrats (King, Sanders).
# 22 REP seats and 13 DEM seats are up, so holdovers are 31 REP, 32 DEM, 2 IND.
HOLDOVERS = {"REP": 31, "DEM": 32, "IND": 2}

# ---- Candidates confirmed from official state feeds (names as the state lists them) ----
CANDIDATES = {
    "NC-SEN-2026": [["Roy Cooper", "DEM"], ["Michael Whatley", "REP"], ["Shannon W. Bray", "LIB"], ["Michael Dublin", "GRN"]],
}

STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}

# Approximate poll-closing time (Eastern, 24h) of the last polls in each state. Used only for display
# ordering and for the simulation adapter. Split states use their latest closing.
POLL_CLOSE_ET = {
    "IN": "19:00", "KY": "19:00", "GA": "19:00", "SC": "19:00", "VT": "19:00", "VA": "19:00",
    "NC": "19:30", "OH": "19:30", "WV": "19:30",
    "AL": "20:00", "CT": "20:00", "DE": "20:00", "FL": "20:00", "IL": "20:00", "ME": "20:00", "MD": "20:00",
    "MA": "20:00", "MS": "20:00", "MO": "20:00", "NH": "20:00", "NJ": "20:00", "OK": "20:00", "PA": "20:00",
    "RI": "20:00", "TN": "20:00", "TX": "21:00", "ND": "20:00",
    "AR": "20:30",
    "AZ": "21:00", "CO": "21:00", "KS": "21:00", "LA": "21:00", "MI": "21:00", "MN": "21:00", "NE": "21:00",
    "NM": "21:00", "NY": "21:00", "SD": "21:00", "WI": "21:00", "WY": "21:00",
    "IA": "22:00", "MT": "22:00", "NV": "22:00", "UT": "22:00",
    "CA": "23:00", "ID": "23:00", "OR": "23:00", "WA": "23:00",
    "HI": "00:00", "AK": "01:00",
}

# States that count a large share of mail ballots after election night. The model waits for
# more of the expected vote before any call there (see model.CONFIG["late_count_min_share"]).
LATE_COUNT_STATES = ["AZ", "CA", "NV", "OR", "WA", "UT", "CO", "AK", "MD", "NY", "NJ", "IL"]


def main():
    assert sum(HOUSE_SEATS.values()) == 435, sum(HOUSE_SEATS.values())
    assert len(SENATE) == 35, len(SENATE)
    assert len(GOVERNORS) == 36, len(GOVERNORS)
    up = {"REP": 0, "DEM": 0}
    for p, _ in SENATE.values():
        up[p] += 1
    assert up == {"REP": 22, "DEM": 13}, up
    assert sum(HOLDOVERS.values()) + len(SENATE) == 100

    races = []
    for st in sorted(SENATE):
        party, special = SENATE[st]
        races.append({
            "id": f"{st}-SEN-2026", "state": st, "office": "us_senate", "district": None,
            "name": f"{STATE_NAMES[st]} Senate" + (" (special)" if special else ""),
            "special": special, "incumbentParty": party,
            "winRule": WIN_RULES.get(st, "plurality"),
            "candidates": CANDIDATES.get(f"{st}-SEN-2026", []),
        })
    for st in sorted(GOVERNORS):
        races.append({
            "id": f"{st}-GOV-2026", "state": st, "office": "governor", "district": None,
            "name": f"{STATE_NAMES[st]} Governor", "special": False,
            "incumbentParty": GOVERNORS[st],
            "winRule": WIN_RULES.get(st, "plurality"),
            "candidates": CANDIDATES.get(f"{st}-GOV-2026", []),
        })
    for st in sorted(HOUSE_SEATS):
        n = HOUSE_SEATS[st]
        for d in range(1, n + 1):
            dist = "AL" if n == 1 else f"{d:02d}"
            label = "at-large" if n == 1 else f"District {d}"
            races.append({
                "id": f"{st}-H{dist}-2026", "state": st, "office": "us_house", "district": dist,
                "name": f"{st}-{dist} House ({STATE_NAMES[st]} {label})", "special": False,
                "incumbentParty": None,
                "winRule": WIN_RULES.get(st, "plurality"),
                "candidates": CANDIDATES.get(f"{st}-H{dist}-2026", []),
            })

    out = {
        "cycle": 2026, "electionDate": "2026-11-03",
        "counts": {"us_senate": len(SENATE), "governor": len(GOVERNORS), "us_house": 435},
        "states": {st: {"name": STATE_NAMES[st], "pollCloseET": POLL_CLOSE_ET[st],
                        "lateCount": st in LATE_COUNT_STATES, "houseSeats": HOUSE_SEATS[st]}
                   for st in STATE_NAMES},
        "races": races,
    }
    with open(os.path.join(ROOT, "data", "races.json"), "w") as f:
        json.dump(out, f, indent=1)
    hold = {
        "note": "Senate seats not up in 2026. The two independents (Maine and Vermont) caucus with the Democrats.",
        "holdovers": HOLDOVERS,
        "independentsCaucusWith": "DEM",
        "majority": 51, "seats": 100, "vicePresidentBreaksTies": True,
    }
    with open(os.path.join(ROOT, "data", "holdovers.json"), "w") as f:
        json.dump(hold, f, indent=1)
    print(f"wrote {len(races)} races")


if __name__ == "__main__":
    main()
