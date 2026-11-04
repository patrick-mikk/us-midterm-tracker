"""Simulation adapter: a synthetic election night for every race in races.json.

Used by scripts/dev_server.py and `fetch.py --demo` so the page and model can be exercised
without live data. Everything it produces is labelled as a simulation on the page. Ground truth
per race is drawn from the statewide prior with state, district and county noise; counties are
revealed over simulated time, early-vote batches first, with a realistic early skew that fades.
"""
import math
import random
from . import base

SOURCE_NAME = "Simulation (no live source)"
SOURCE_URL = None

MINUTES_FROM_FIRST_CLOSE = 0  # simulated clock starts at 19:00 ET


def _poll_close_minutes(hhmm):
    h, m = hhmm.split(":")
    mins = int(h) * 60 + int(m)
    if int(h) < 12:          # after midnight
        mins += 24 * 60
    return mins - 19 * 60


def _county_count(state_seats):
    # more House seats roughly tracks population and county count, capped for speed
    return max(6, min(40, 6 + state_seats * 2))


class Night:
    """Deterministic synthetic ground truth for all races, built once per process."""

    def __init__(self, races_doc, baselines, seed=2026):
        self.rng = random.Random(seed)
        self.states = races_doc["states"]
        self.base = baselines["states"]
        self.truth = {}
        self.units = {}
        for st, info in self.states.items():
            prior = self.base.get(st, {"expectedMidterm": 500000, "margin2024": 0.0})
            rng = random.Random(f"{seed}-{st}")
            n = _county_count(info["houseSeats"])
            # county sizes lognormal; bigger counties lean DEM relative to the state (urban gradient)
            sizes = [math.exp(rng.gauss(0, 1.1)) for _ in range(n)]
            tot = sum(sizes)
            state_dem = 0.5 - prior["margin2024"] / 200.0
            state_swing = rng.gauss(0.0, 0.03)
            units = []
            # centre the urban gradient so the vote-weighted lean matches the statewide prior
            wmean_log = sum(s * math.log(s) for s in sizes) / tot
            for i, s in enumerate(sizes):
                size = prior["expectedMidterm"] * s / tot
                urban = (math.log(s) - wmean_log) * 0.045
                lean = state_dem + state_swing + urban + rng.gauss(0, 0.06)
                units.append({
                    "fips": f"{st}{i + 1:03d}", "name": f"{info['name']} unit {i + 1:02d}",
                    "size": size, "dem": max(0.05, min(0.95, lean)),
                    "speed": rng.uniform(0.6, 1.6),       # how fast this county counts
                    "lag": rng.uniform(0, 60) + (90 if info["lateCount"] else 0),
                    "early_share": rng.uniform(0.35, 0.7),  # share of vote cast early/mail
                    "early_skew": rng.uniform(0.02, 0.10),  # early vote is this much more DEM
                    "precincts": max(3, int(size / 2200)),
                    "districts": None,
                })
            self.units[st] = units
            self.state_swing = getattr(self, "state_swing", {})
            self.state_swing[st] = state_swing
        for r in races_doc["races"]:
            st = r["state"]
            rng = random.Random(f"{seed}-{r['id']}")
            info = self.states[st]
            units = self.units[st]
            if r["office"] == "us_house":
                k = max(1, len(units) // info["houseSeats"])
                d = int(r["district"]) if r["district"] != "AL" else 1
                picked = units[(d - 1) * k:(d - 1) * k + k] or units[-k:]
                if info["houseSeats"] > 1 and len(units) >= info["houseSeats"]:
                    # give each district a distinctive partisanship around its counties
                    offs = rng.gauss(0, 0.07)
                else:
                    offs = 0.0
                scale = 1.0 / max(1, len(units) // max(1, k)) if info["houseSeats"] > 1 else 1.0
            else:
                picked = units
                offs = rng.gauss(0, 0.02)
                scale = 1.0
            cands = r.get("candidates") or []
            dem = next((c[0] for c in cands if c[1] == "DEM"), "Democratic nominee")
            rep = next((c[0] for c in cands if c[1] == "REP"), "Republican nominee")
            third = [(c[0], c[1]) for c in cands if c[1] not in ("DEM", "REP")]
            if not third and rng.random() < 0.35:
                third = [("Libertarian nominee", "LIB")]
            third_share = rng.uniform(0.01, 0.04) if third else 0.0
            self.truth[r["id"]] = {"units": picked, "offset": offs, "dem": dem, "rep": rep,
                                   "third": third, "thirdShare": third_share, "scale": scale,
                                   "office": r["office"]}

    def snapshot(self, race_id, state, sim_minutes):
        """Units for one race at simulated minute `sim_minutes` since 19:00 ET."""
        info = self.states[state]
        close = _poll_close_minutes(info["pollCloseET"])
        t = sim_minutes - close
        tr = self.truth[race_id]
        out = []
        for u in tr["units"]:
            rng = random.Random(f"{race_id}-{u['fips']}")
            size = u["size"] * tr["scale"] * (0.85 if tr["office"] == "us_house" else 1.0)
            if t <= 0:
                frac = 0.0
            else:
                # early/mail batch lands first, then election-day precincts stream in
                early_done = min(1.0, max(0.0, (t - u["lag"] * 0.3) / 25.0))
                day_done = min(1.0, max(0.0, (t - u["lag"]) / (240.0 / u["speed"])))
                frac_early = u["early_share"] * early_done
                frac_day = (1 - u["early_share"]) * day_done
                frac = frac_early + frac_day
            dem_true = max(0.03, min(0.97, u["dem"] + tr["offset"]))
            # composition of what is counted so far
            e = u["early_share"] * (min(1.0, max(0.0, (t - u["lag"] * 0.3) / 25.0)) if t > 0 else 0)
            d = frac - e
            dem_counted = dem_true
            if frac > 0:
                dem_counted = ((dem_true + u["early_skew"]) * e + (dem_true - u["early_skew"] * u["early_share"] / max(0.05, 1 - u["early_share"])) * d) / frac
                dem_counted += rng.gauss(0, 0.004)
            counted = int(size * frac)
            two_party = int(counted * (1 - tr["thirdShare"]))
            dem_v = int(two_party * max(0.0, min(1.0, dem_counted)))
            rep_v = two_party - dem_v
            cands = [[tr["dem"], "DEM", dem_v], [tr["rep"], "REP", rep_v]]
            for name, party in tr["third"]:
                cands.append([name, party, counted - two_party])
            prec_rep = int(round(u["precincts"] * min(1.0, max(0.0, (t - u["lag"]) / (240.0 / u["speed"])) if t > 0 else 0)))
            if frac >= 0.999:
                prec_rep = u["precincts"]
            out.append({"fips": u["fips"], "name": u["name"], "precincts": u["precincts"],
                        "precinctsReported": prec_rep, "candidates": cands,
                        "byType": {"early": {}, "electionDay": {}, "mail": {}} if e > 0 else None})
        return out


_NIGHT = None


def night(races_doc, baselines):
    global _NIGHT
    if _NIGHT is None:
        _NIGHT = Night(races_doc, baselines)
    return _NIGHT


def fetch_state(state, races_doc, baselines, sim_minutes):
    nt = night(races_doc, baselines)
    races = []
    for r in races_doc["races"]:
        if r["state"] != state:
            continue
        races.append({"id": r["id"], "office": r["office"], "district": r["district"],
                      "units": nt.snapshot(r["id"], state, sim_minutes)})
    return {"state": state, "source": None, "sourceName": SOURCE_NAME, "fetchedAt": base.now_ms(),
            "races": races, "simulated": True, "simMinutes": sim_minutes}
