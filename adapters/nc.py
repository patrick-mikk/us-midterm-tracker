"""North Carolina: er.ncsbe.gov Election Night Reporting.

Endpoints (verified 2026-11-04):
  https://er.ncsbe.gov/enr/20261103/data/results_0.txt      statewide totals, JSON array
  https://er.ncsbe.gov/enr/20261103/data/results_{N}.txt    county N (1..100, alphabetical), JSON array
Row fields: cid county id, cnm contest name, bnm candidate, pty party, vct votes, prt precincts
reported, ptl precincts total, ovc one-stop early, evc election day, avc absentee by mail, pvc provisional.
"""
import re
from . import base

SOURCE_NAME = "NC State Board of Elections"
SOURCE_URL = "https://er.ncsbe.gov/?election_dt=11/03/2026"
ELECTION = "20261103"
BASE = f"https://er.ncsbe.gov/enr/{ELECTION}/data/"

COUNTIES = [
    "Alamance", "Alexander", "Alleghany", "Anson", "Ashe", "Avery", "Beaufort", "Bertie", "Bladen", "Brunswick",
    "Buncombe", "Burke", "Cabarrus", "Caldwell", "Camden", "Carteret", "Caswell", "Catawba", "Chatham", "Cherokee",
    "Chowan", "Clay", "Cleveland", "Columbus", "Craven", "Cumberland", "Currituck", "Dare", "Davidson", "Davie",
    "Duplin", "Durham", "Edgecombe", "Forsyth", "Franklin", "Gaston", "Gates", "Graham", "Granville", "Greene",
    "Guilford", "Halifax", "Harnett", "Haywood", "Henderson", "Hertford", "Hoke", "Hyde", "Iredell", "Jackson",
    "Johnston", "Jones", "Lee", "Lenoir", "Lincoln", "Macon", "Madison", "Martin", "McDowell", "Mecklenburg",
    "Mitchell", "Montgomery", "Moore", "Nash", "New Hanover", "Northampton", "Onslow", "Orange", "Pamlico",
    "Pasquotank", "Pender", "Perquimans", "Person", "Pitt", "Polk", "Randolph", "Richmond", "Robeson", "Rockingham",
    "Rowan", "Rutherford", "Sampson", "Scotland", "Stanly", "Stokes", "Surry", "Swain", "Transylvania", "Tyrrell",
    "Union", "Vance", "Wake", "Warren", "Washington", "Watauga", "Wayne", "Wilkes", "Wilson", "Yadkin", "Yancey",
]
assert len(COUNTIES) == 100 and COUNTIES[91] == "Wake"


def county_fips(n):
    return f"37{2 * n - 1:03d}"


_HOUSE = re.compile(r"^US HOUSE OF REPRESENTATIVES DISTRICT (\d+)", re.I)


def contest_to_race(cnm):
    """Map an NC contest name to a race id and office, or None if not tracked."""
    c = cnm.upper()
    if c.startswith("US SENATE"):
        return "NC-SEN-2026", "us_senate", None
    m = _HOUSE.match(c)
    if m:
        d = f"{int(m.group(1)):02d}"
        return f"NC-H{d}-2026", "us_house", d
    if c.startswith("NC GOVERNOR") or c == "GOVERNOR":
        return "NC-GOV-2026", "governor", None
    return None


def parse_rows(rows, county_n):
    """Turn one county file into {race_id: unit}."""
    units = {}
    for r in rows:
        mapped = contest_to_race(r.get("cnm", ""))
        if not mapped:
            continue
        rid, office, dist = mapped
        u = units.setdefault(rid, {
            "fips": county_fips(county_n), "name": COUNTIES[county_n - 1],
            "precincts": int(r.get("ptl") or 0) or None,
            "precinctsReported": int(r.get("prt") or 0) if r.get("ptl") else None,
            "candidates": [], "byType": {"early": {}, "electionDay": {}, "mail": {}, "provisional": {}},
            "_office": office, "_district": dist,
        })
        name = base.clean_name(r.get("bnm"))
        if name.lower().startswith("write-in"):
            continue
        party = base.norm_party(r.get("pty"))
        votes = int(r.get("vct") or 0)
        u["candidates"].append([name, party, votes])
        u["byType"]["early"][name] = int(r.get("ovc") or 0)
        u["byType"]["electionDay"][name] = int(r.get("evc") or 0)
        u["byType"]["mail"][name] = int(r.get("avc") or 0)
        u["byType"]["provisional"][name] = int(r.get("pvc") or 0)
    return units


def fetch(ctx=None):
    def one(n):
        return n, base.get_json(f"{BASE}results_{n}.txt", retries=1)

    results = base.parallel_map(one, range(1, 101), workers=10)
    races = {}
    failures = []
    for res in results:
        if isinstance(res, Exception):
            failures.append(str(res))
            continue
        n, rows = res
        for rid, u in parse_rows(rows, n).items():
            office, dist = u.pop("_office"), u.pop("_district")
            race = races.setdefault(rid, {"id": rid, "office": office, "district": dist, "units": []})
            race["units"].append(u)
    if not races:
        raise RuntimeError("NC: no counties parsed; " + (failures[0] if failures else "empty feed"))
    return {"state": "NC", "source": SOURCE_URL, "sourceName": SOURCE_NAME, "fetchedAt": base.now_ms(),
            "races": list(races.values()), "partial": len(failures), "warnings": failures[:3]}
