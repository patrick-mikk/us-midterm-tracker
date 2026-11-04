"""Generic Clarity / Scytl Election Night Reporting adapter.

Instances live at https://results.enr.clarityelections.com/{PATH}/{ELECTION_ID}/ . The current
version number is in current_ver.txt; the data then sits under {ver}/json/:
  en/summary.json          contest totals
  details.json             contests with per-county vote arrays (when the state publishes them)
  en/electionsettings.json participating county list
Election IDs change every cycle, so they are configured in adapters/__init__.py from the link on
the official state results page. Contest matching uses CONTEST_PATTERNS below; adjust per state.
"""
import re
from . import base

ROOT = "https://results.enr.clarityelections.com"

CONTEST_PATTERNS = [
    (re.compile(r"\bU\.?S\.? SENAT", re.I), "us_senate"),
    (re.compile(r"\bGOVERNOR\b(?!.*LIEUTENANT)", re.I), "governor"),
    (re.compile(r"\bU\.?S\.? (HOUSE|REPRESENTATIVE).*?(\d+)", re.I), "us_house"),
]


def classify(name):
    for pat, office in CONTEST_PATTERNS:
        m = pat.search(name)
        if m:
            dist = None
            if office == "us_house":
                dist = f"{int(m.group(2)):02d}"
            return office, dist
    return None, None


def make(state, path, election_id):
    class _Adapter:
        SOURCE_NAME = f"{state} official results (Clarity ENR)"
        SOURCE_URL = f"{ROOT}/{path}/{election_id}/"

        @staticmethod
        def fetch(ctx=None):
            ver = base.get(f"{ROOT}/{path}/{election_id}/current_ver.txt").strip()
            vbase = f"{ROOT}/{path}/{election_id}/{ver}/json/"
            details = base.get_json(vbase + "details.json")
            settings = {}
            try:
                settings = base.get_json(vbase + "en/electionsettings.json")
            except Exception:  # noqa: BLE001
                pass
            counties = []
            for row in (settings.get("settings", {}).get("electiondetails", {}).get("participatingcounties") or []):
                counties.append(row.split("|")[0])
            races = {}
            for contest in details.get("Contests", []):
                name = contest.get("C") or contest.get("K") or ""
                office, dist = classify(name)
                if not office:
                    continue
                rid = {"us_senate": f"{state}-SEN-2026", "governor": f"{state}-GOV-2026",
                       "us_house": f"{state}-H{dist}-2026"}[office]
                cand_names = contest.get("CH") or contest.get("C") or []
                parties = contest.get("P") or [""] * len(cand_names)
                per_county = contest.get("V") or []          # [county][candidate]
                prec = contest.get("PR") or []               # precincts reported per county (if present)
                prec_total = contest.get("PT") or []
                units = []
                for ci, votes in enumerate(per_county):
                    cname = counties[ci] if ci < len(counties) else f"Unit {ci + 1}"
                    units.append({
                        "fips": None, "name": cname,
                        "precincts": int(prec_total[ci]) if ci < len(prec_total) else None,
                        "precinctsReported": int(prec[ci]) if ci < len(prec) else None,
                        "candidates": [[base.clean_name(cand_names[k]), base.norm_party(parties[k] if k < len(parties) else ""),
                                        int(v or 0)] for k, v in enumerate(votes)],
                        "byType": None,
                    })
                races[rid] = {"id": rid, "office": office, "district": dist, "units": units}
            if not races:
                raise RuntimeError(f"{state}: Clarity feed parsed but no tracked contests found")
            return {"state": state, "source": _Adapter.SOURCE_URL, "sourceName": _Adapter.SOURCE_NAME,
                    "fetchedAt": base.now_ms(), "races": list(races.values())}

    return _Adapter
