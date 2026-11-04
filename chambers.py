"""Chamber totals and joint path-to-victory simulation.

Combines the per-race Monte Carlo draws produced by model.project_race draw by draw. Because
every race shares the same national-shift vector (model.national_shift), draw i across races
is one coherent "night", so the seat histograms carry the right correlation.
"""
from collections import Counter

SENATE_SEATS, SENATE_MAJORITY = 100, 51
HOUSE_SEATS, HOUSE_MAJORITY = 435, 218
GOV_SEATS = 36

CALLED = ("projected", "final")


def _party_bucket(p):
    return p if p in ("DEM", "REP") else "OTH"


def _dem_win_draws(summary, margins):
    """Per draw: 1 if DEM wins, 0 if REP wins, None if neither of the top two is DEM/REP."""
    cands = summary["candidates"]
    if len(cands) < 2:
        return None
    a, b = cands[0]["party"], cands[1]["party"]
    if a == "DEM":
        return [1 if m > 0 else 0 for m in margins]
    if a == "REP":
        return [0 if m > 0 else 1 for m in margins]
    if b == "DEM":
        return [0 if m > 0 else 1 for m in margins]
    if b == "REP":
        return [1 if m > 0 else 0 for m in margins]
    return None


def summarise(office, summaries, draws_by_race, holdovers=None, n_draws=1000):
    """Return the chamber block for latest.json."""
    seats_total = {"us_senate": SENATE_SEATS, "us_house": HOUSE_SEATS, "governor": GOV_SEATS}[office]
    majority = {"us_senate": SENATE_MAJORITY, "us_house": HOUSE_MAJORITY, "governor": None}[office]
    hold = dict(holdovers or {})
    called = Counter()
    leading = Counter()
    uncalled_ids = []
    dem_base = hold.get("DEM", 0) + hold.get("IND", 0)  # independents caucus with DEM
    rep_base = hold.get("REP", 0)
    per_draw_dem = [dem_base] * n_draws
    per_draw_rep = [rep_base] * n_draws
    path = []
    for s in summaries:
        if s["office"] != office:
            continue
        leader = s.get("leader")
        lp = _party_bucket(leader["party"]) if leader else None
        if s["status"] in CALLED and leader:
            called[lp] += 1
            if lp == "DEM":
                per_draw_dem = [x + 1 for x in per_draw_dem]
            elif lp == "REP":
                per_draw_rep = [x + 1 for x in per_draw_rep]
            continue
        uncalled_ids.append(s["id"])
        if leader:
            leading[lp] += 1
        dw = _dem_win_draws(s, draws_by_race.get(s["id"], []))
        p_dem = s.get("winProbParty", {}).get("DEM", 0.0)
        p_rep = s.get("winProbParty", {}).get("REP", 0.0)
        if dw and len(dw) == n_draws:
            for i, d in enumerate(dw):
                if d:
                    per_draw_dem[i] += 1
                else:
                    per_draw_rep[i] += 1
        else:
            # no usable draws (e.g. no votes yet): fall back to the race's win probability
            import random
            rng = random.Random(s["id"])
            for i in range(n_draws):
                if rng.random() < (p_dem if (p_dem or p_rep) else 0.5):
                    per_draw_dem[i] += 1
                else:
                    per_draw_rep[i] += 1
        path.append({"id": s["id"], "name": s["name"], "state": s["state"], "pDem": round(p_dem, 3),
                     "pRep": round(p_rep, 3), "status": s["status"], "pctExpected": s["pctExpected"],
                     "marginPct": s.get("marginPct")})
    dem_hist = Counter(per_draw_dem)
    rep_hist = Counter(per_draw_rep)
    out = {
        "office": office, "seats": seats_total, "majority": majority,
        "holdovers": hold, "called": dict(called), "leading": dict(leading),
        "uncalled": len(uncalled_ids),
        "secured": {"DEM": dem_base + called["DEM"], "REP": rep_base + called["REP"], "OTH": called["OTH"]},
        "ifLeadersHold": {"DEM": dem_base + called["DEM"] + leading["DEM"],
                          "REP": rep_base + called["REP"] + leading["REP"], "OTH": called["OTH"] + leading["OTH"]},
        "distribution": {"DEM": {str(k): v for k, v in sorted(dem_hist.items())},
                         "REP": {str(k): v for k, v in sorted(rep_hist.items())}},
        "expectedSeats": {"DEM": round(sum(per_draw_dem) / n_draws, 1), "REP": round(sum(per_draw_rep) / n_draws, 1)},
        "path": sorted(path, key=lambda r: -r["pDem"]),
    }
    if majority:
        out["controlProb"] = {
            "DEM": round(sum(1 for x in per_draw_dem if x >= majority) / n_draws, 4),
            "REP": round(sum(1 for x in per_draw_rep if x >= majority) / n_draws, 4),
        }
        if office == "us_senate":
            # 50-50 leaves control with the vice president's party (REP)
            ties = sum(1 for x in per_draw_dem if x == 50) / n_draws
            out["controlProb"]["REP"] = round(out["controlProb"]["REP"] + ties, 4)
            out["tieProb"] = round(ties, 4)
        # Tipping point: in draws where a party lands exactly on the majority, the race it won by
        # the narrowest share is the one that decided control. Count how often each race plays that role.
        tip = Counter()
        rows = []
        for s in summaries:
            if s["office"] != office or s["status"] in CALLED:
                continue
            m = draws_by_race.get(s["id"])
            dw = _dem_win_draws(s, m or [])
            if dw and len(dw) == n_draws:
                denom = float(s.get("expected") or 1)
                rows.append((s["id"], dw, [abs(x) / denom for x in m]))
        if rows:
            for i in range(n_draws):
                dem_hit = per_draw_dem[i] == majority
                rep_hit = per_draw_rep[i] == majority or (office == "us_senate" and per_draw_rep[i] == 50)
                if not (dem_hit or rep_hit):
                    continue
                best, best_m = None, 9e9
                for rid, dw, mg in rows:
                    if (dw[i] == 1) == dem_hit and mg[i] < best_m:
                        best, best_m = rid, mg[i]
                if best:
                    tip[best] += 1
        out["tippingPoint"] = [{"id": k, "share": round(v / n_draws, 3)} for k, v in tip.most_common(5)]
    return out
