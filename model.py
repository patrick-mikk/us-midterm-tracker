"""Projection model for the midterms tracker.

Pure Python standard library. One call to `project_race` per race returns a summary dict
(for the public JSON) and keeps the raw simulated final margins so `chambers.py` can
combine races draw by draw with a shared national shift.

Everything tunable lives in CONFIG. CALLS_ENABLED gates the "Projected winner" status; until
the backtest in tests/test_backtest.py passes, the page shows leaders only.
"""
import math
import random
import statistics

CALLS_ENABLED = True

CONFIG = {
    "draws": 1000,                 # Monte Carlo draws per race
    "seed_national": 20261103,     # fixed seed so the national shift vector is identical every run
    "sigma_national": 0.015,       # shared national shift in share points (1.5 pts of two-party share)
    "sigma_state": 0.025,          # statewide shift on top of the national one (so ~4 pts combined margin swing)
    "sigma_turnout": 0.15,         # lognormal sd of the county turnout factor
    "sigma_county": 0.03,          # county split residual, share points (6 pts of margin)
    "no_vote_type_widen": 1.3,     # multiplier on sigma_state when a source gives no mail/early/day split
    "min_counted_for_own_split": 0.20,  # county uses its own counted split above this share counted
    "precinct_share_for_estimate": 0.30,
    "complete_runs": 3,            # a county whose count hasn't moved for this many runs is treated as complete
    "min_share_for_call": 0.25,    # share of expected vote counted before any call
    "late_count_min_share": 0.50,  # stricter floor in late-counting states
    "call_win_prob": 0.995,
    "call_needs_share": 0.75,      # trailing candidate needs at least this share of 1.5x the remaining
    "call_remaining_multiplier": 1.5,
    "hist_bins": 41,
    "prior_turnout_ratio": 0.72,   # midterm vote relative to 2024 presidential when the prior is presidential
}

PARTY_ORDER = ["DEM", "REP", "IND", "LIB", "GRN", "OTH"]

STATUS_LABELS = {
    "no_votes": "No votes yet",
    "too_early": "Too early to call",
    "leader": "Leader",
    "projected": "Projected winner",
    "withdrawn": "Projection withdrawn",
    "runoff": "Runoff likely",
    "rcv": "RCV tabulation",
    "final": "Final count",
    "no_source": "No live source",
}


def _national_shift_vector(n):
    rng = random.Random(CONFIG["seed_national"])
    return [rng.gauss(0.0, CONFIG["sigma_national"]) for _ in range(n)]


_NATIONAL = None


def national_shift(n=None):
    """Shared DEM-favourable national shift, one value per draw, identical across races and runs."""
    global _NATIONAL
    n = n or CONFIG["draws"]
    if _NATIONAL is None or len(_NATIONAL) != n:
        _NATIONAL = _national_shift_vector(n)
    return _NATIONAL


def _clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def aggregate_candidates(units, listed=None):
    """Sum candidate votes across units. Returns list of [name, party, votes] sorted by votes."""
    totals = {}
    order = []
    for c in (listed or []):
        key = (c[0], c[1])
        if key not in totals:
            totals[key] = 0
            order.append(key)
    for u in units:
        for name, party, votes in u.get("candidates", []):
            key = (name, party or "OTH")
            if key not in totals:
                totals[key] = 0
                order.append(key)
            totals[key] += int(votes or 0)
    cands = [[k[0], k[1], totals[k]] for k in order]
    cands.sort(key=lambda c: (-c[2], PARTY_ORDER.index(c[1]) if c[1] in PARTY_ORDER else 9))
    return cands


def _unit_counted(u):
    return sum(int(c[2] or 0) for c in u.get("candidates", []))


def _prior_a_share(state_margin_rep_minus_dem, party_a, party_b):
    """Convert a REP-minus-DEM margin in points into A's expected two-party share."""
    dem_share = 0.5 - state_margin_rep_minus_dem / 200.0
    if party_a == "DEM" and party_b == "REP":
        return _clamp(dem_share, 0.02, 0.98)
    if party_a == "REP" and party_b == "DEM":
        return _clamp(1.0 - dem_share, 0.02, 0.98)
    return 0.5


def project_race(race, units, baselines, memory, draws=None, complete_hint=None):
    """Run the model for one race.

    race: dict from races.json (needs id, state, office, winRule, candidates)
    units: list of unit dicts in the common adapter schema
    baselines: {"states": {ST: {...}}, "counties": {fips: {...}}}
    memory: per-race dict persisted between runs (counts per unit, stable-run counters, call history)
    Returns (summary, margin_draws, unit_rows). margin_draws is A minus B in votes per draw,
    where A is the current leader (or the first listed candidate before any votes).
    """
    cfg = CONFIG
    n = draws or cfg["draws"]
    st = race["state"]
    state_prior = baselines.get("states", {}).get(st, {})
    county_base = baselines.get("counties", {})
    late = race.get("lateCount", False)

    cands = aggregate_candidates(units, race.get("candidates"))
    counted = sum(c[2] for c in cands)
    if len(cands) < 2:
        # Unopposed or unknown field: never simulate, just describe.
        cands = cands + [["(no second candidate)", "OTH", 0]] * (2 - len(cands))
    A, B = cands[0], cands[1]
    party_a, party_b = A[1], B[1]
    two_party = A[2] + B[2]
    tp_frac = (two_party / counted) if counted else 1.0

    # ----- baselines per unit -----
    office_key = race["office"] if race["office"] != "us_house" else f"us_house:{race['district']}"
    state_expected = state_prior.get("expectedMidterm") or 0
    sum_ptl = sum((u.get("precincts") or 0) for u in units)
    n_units = max(1, len(units))
    unit_rows = []
    for u in units:
        fips = u.get("fips")
        cb = county_base.get(fips, {}).get("races", {}) if fips else {}
        base = cb.get(office_key) or cb.get("us_senate") or cb.get("governor") or cb.get("president")
        if base and base.get("total"):
            b_total = float(base["total"])
            if "president" in str(base) and office_key != "president":
                b_total *= cfg["prior_turnout_ratio"]
            b_margin = base.get("margin")
            b_source = "county"
        else:
            if sum_ptl and u.get("precincts"):
                b_total = state_expected * (u["precincts"] / sum_ptl)
            else:
                b_total = state_expected / n_units
            b_margin = state_prior.get("margin2024")
            b_source = "state"
        if race["office"] == "us_house" and b_source == "state":
            # a House district is roughly one seat's slice of the statewide prior
            b_total = b_total / max(1, race.get("houseSeats") or 1)
        unit_rows.append({
            "fips": fips, "name": u.get("name"), "precincts": u.get("precincts"),
            "precinctsReported": u.get("precinctsReported"), "counted": _unit_counted(u),
            "baseTotal": max(1.0, b_total), "baseMargin": b_margin, "baseSource": b_source,
            "candidates": u.get("candidates", []), "byType": u.get("byType"),
        })

    # ----- completeness and stability memory -----
    mem_units = memory.setdefault("units", {})
    complete_flags = []
    for r in unit_rows:
        key = str(r["fips"] or r["name"])
        m = mem_units.setdefault(key, {"last": None, "stable": 0})
        if m["last"] == r["counted"] and r["counted"] > 0:
            m["stable"] += 1
        else:
            m["stable"] = 0
        m["last"] = r["counted"]
        p, pt = r["precinctsReported"], r["precincts"]
        pct_prec = (p / pt) if (p is not None and pt) else None
        complete = bool(pt and p is not None and p >= pt and r["counted"] > 0)
        if not complete and r["counted"] > 0 and m["stable"] >= cfg["complete_runs"] and (pct_prec is None or pct_prec >= 0.95):
            complete = True
        if complete_hint is not None:
            complete = bool(complete_hint.get(key, complete))
        r["complete"] = complete
        r["pctPrecincts"] = pct_prec
        complete_flags.append(complete)

    # ----- turnout factor from complete units -----
    ratios = [r["counted"] / r["baseTotal"] for r in unit_rows if r["complete"] and r["baseTotal"] > 0]
    factor = statistics.median(ratios) if ratios else 1.0
    factor = _clamp(factor, 0.4, 2.5)
    factor_uncertain = len(ratios) < 3

    # ----- expected and remaining votes per unit -----
    for r in unit_rows:
        if r["complete"]:
            exp = float(r["counted"])
        else:
            exp = max(float(r["counted"]), r["baseTotal"] * factor)
            pp = r["pctPrecincts"]
            if pp and pp >= cfg["precinct_share_for_estimate"]:
                exp = max(exp, r["counted"] / pp)
        r["expected"] = exp
        r["remaining"] = max(0.0, exp - r["counted"])
    expected_total = sum(r["expected"] for r in unit_rows)
    remaining_total = sum(r["remaining"] for r in unit_rows)
    pct_expected = (counted / expected_total) if expected_total else 0.0

    # ----- split of the remaining vote -----
    prior_state_a = _prior_a_share(state_prior.get("margin2024") or 0.0, party_a, party_b)
    # observed statewide swing relative to the prior, from units with counted votes
    obs_a = (A[2] / two_party) if two_party else prior_state_a
    swing = obs_a - prior_state_a if two_party else 0.0
    for r in unit_rows:
        a_votes = sum(int(c[2] or 0) for c in r["candidates"] if c[0] == A[0] and c[1] == A[1])
        b_votes = sum(int(c[2] or 0) for c in r["candidates"] if c[0] == B[0] and c[1] == B[1])
        tp = a_votes + b_votes
        own = (a_votes / tp) if tp else None
        if r["baseMargin"] is not None and r["baseSource"] == "county":
            prior_u = _clamp(_prior_a_share(r["baseMargin"], party_a, party_b) + swing, 0.02, 0.98)
        else:
            prior_u = _clamp(prior_state_a + swing, 0.02, 0.98)
        frac = (r["counted"] / r["expected"]) if r["expected"] else 0.0
        if own is not None and frac >= cfg["min_counted_for_own_split"]:
            p = own
        elif own is not None and frac > 0:
            w = frac / cfg["min_counted_for_own_split"]
            p = w * own + (1 - w) * prior_u
        else:
            p = prior_u
        r["splitA"] = p
        r["ownA"] = own
        r["currentMarginA"] = (a_votes - b_votes)
        r["aVotes"], r["bVotes"] = a_votes, b_votes
        # residual sd shrinks as more of the county is counted
        r["sdA"] = cfg["sigma_county"] * math.sqrt(max(0.05, 1.0 - frac))
        # the trailing party gains if remaining in this county leans their way
        r["remainingTP"] = r["remaining"] * tp_frac

    # ----- Monte Carlo -----
    current_margin = A[2] - B[2]
    nat = national_shift(n)
    sign = 1.0 if party_a == "DEM" else (-1.0 if party_a == "REP" else 0.0)
    if party_b not in ("DEM", "REP"):
        sign = 0.0
    sigma_state = cfg["sigma_state"]
    has_types = any(r.get("byType") and any(r["byType"].values()) for r in unit_rows)
    if not has_types and pct_expected < 0.5:
        sigma_state *= cfg["no_vote_type_widen"]
    if factor_uncertain:
        sigma_state *= 1.25
    sigma_t = cfg["sigma_turnout"]
    rng = random.Random(hash((race["id"], counted)) & 0xFFFFFFFF)
    gauss = rng.gauss
    exp_ = math.exp
    live = [(r["remainingTP"], r["splitA"], r["sdA"]) for r in unit_rows if r["remainingTP"] > 0]
    margins = [0.0] * n
    for i in range(n):
        shift = sign * nat[i] + gauss(0.0, sigma_state)
        acc = 0.0
        for rem, p, sd in live:
            share = p + shift + gauss(0.0, sd)
            if share < 0.0:
                share = 0.0
            elif share > 1.0:
                share = 1.0
            acc += rem * exp_(gauss(0.0, sigma_t)) * (2.0 * share - 1.0)
        margins[i] = current_margin + acc
    wins_a = sum(1 for m in margins if m > 0)
    win_a = wins_a / n
    ms = sorted(margins)

    def q(p):
        return ms[min(n - 1, max(0, int(p * n)))]

    # ----- what the trailing candidate needs -----
    rem_tp = sum(r["remainingTP"] for r in unit_rows)
    needs = None
    if rem_tp > 0:
        needs_share = (current_margin + rem_tp) / (2.0 * rem_tp)
        big = rem_tp * cfg["call_remaining_multiplier"]
        needs_share_big = (current_margin + big) / (2.0 * big)
        needs = {"candidate": B[0], "party": B[1], "share": round(_clamp(needs_share, 0, 1.5), 4),
                 "shareOf1_5x": round(_clamp(needs_share_big, 0, 1.5), 4), "remaining": int(round(rem_tp))}
    else:
        needs = {"candidate": B[0], "party": B[1], "share": None, "shareOf1_5x": None, "remaining": 0}

    # ----- projected final share of the leader (for runoff rules) -----
    exp_a_final = A[2] + sum(r["remainingTP"] * r["splitA"] for r in unit_rows)
    leader_final_share = (exp_a_final / expected_total) if expected_total else 0.0

    # ----- status -----
    all_complete = bool(unit_rows) and all(r["complete"] for r in unit_rows) and all(
        (r["precincts"] or 0) > 0 for r in unit_rows)
    min_share = cfg["late_count_min_share"] if late else cfg["min_share_for_call"]
    rule = race.get("winRule", "plurality")
    prev_status = memory.get("status")
    status = "too_early"
    if counted == 0:
        status = "no_votes"
    elif all_complete:
        status = "final"
        if rule in ("majority", "rcv") and (A[2] / counted) < 0.5:
            status = "runoff" if rule == "majority" else "rcv"
    elif pct_expected >= min_share:
        projected = (CALLS_ENABLED and win_a >= cfg["call_win_prob"]
                     and needs["shareOf1_5x"] is not None and needs["shareOf1_5x"] >= cfg["call_needs_share"])
        if rule in ("majority", "rcv") and leader_final_share < 0.5:
            status = "runoff" if rule == "majority" else "rcv"
        elif projected:
            status = "projected"
        else:
            status = "leader"
    # Withdrawal: once projected, dropping below the bar is shown, never hidden
    history = memory.setdefault("calls", [])
    if prev_status == "projected" and status not in ("projected", "final"):
        status = "withdrawn"
    if prev_status == "withdrawn" and status in ("leader", "too_early"):
        status = "withdrawn"
    if status != prev_status:
        history.append({"status": status, "leader": A[0], "party": party_a, "pct": round(pct_expected, 4),
                        "winProb": round(win_a, 4)})
        memory["statusChangedAt"] = None  # filled by fetch with the run timestamp
    memory["status"] = status

    # ----- histogram of simulated final margin in points of expected vote -----
    bins = cfg["hist_bins"]
    denom = expected_total or 1.0
    pts = [100.0 * m / denom for m in margins]
    lo, hi = -30.0, 30.0
    hist = [0] * bins
    width = (hi - lo) / bins
    for v in pts:
        k = int((v - lo) / width)
        hist[0 if k < 0 else bins - 1 if k >= bins else k] += 1

    def share(c):
        return round(c[2] / counted, 4) if counted else None

    summary = {
        "id": race["id"], "state": st, "office": race["office"], "district": race.get("district"),
        "name": race.get("name"), "winRule": rule, "special": race.get("special", False),
        "incumbentParty": race.get("incumbentParty"), "lateCount": late,
        "status": status,
        "candidates": [{"name": c[0], "party": c[1], "votes": c[2], "share": share(c),
                        "p": round(win_a, 4) if i == 0 else round(1 - win_a, 4) if i == 1 else 0.0}
                       for i, c in enumerate(cands[:6])],
        "leader": {"name": A[0], "party": party_a} if counted else None,
        "counted": counted, "expected": int(round(expected_total)), "remaining": int(round(remaining_total)),
        "pctExpected": round(pct_expected, 4),
        "margin": current_margin, "marginPct": round(100.0 * current_margin / counted, 2) if counted else None,
        "winProbParty": {party_a: round(win_a, 4), party_b: round(1 - win_a, 4)},
        "projMarginPts": {"p05": round(100 * q(0.05) / denom, 2), "p50": round(100 * q(0.5) / denom, 2),
                          "p95": round(100 * q(0.95) / denom, 2)},
        "leaderFinalShare": round(leader_final_share, 4),
        "hist": {"lo": lo, "hi": hi, "bins": hist},
        "needs": needs,
        "turnoutFactor": round(factor, 3), "completeUnits": sum(complete_flags), "units": len(unit_rows),
        "precinctsReported": sum((r["precinctsReported"] or 0) for r in unit_rows) or None,
        "precinctsTotal": sum((r["precincts"] or 0) for r in unit_rows) or None,
        "callHistory": history[-6:],
    }
    return summary, margins, unit_rows


def unit_detail_rows(unit_rows, A, B):
    """Public county table rows for data/states/XX.json."""
    out = []
    for r in unit_rows:
        tp = r["aVotes"] + r["bVotes"]
        out.append({
            "fips": r["fips"], "name": r["name"], "precincts": r["precincts"],
            "precinctsReported": r["precinctsReported"], "counted": r["counted"],
            "expected": int(round(r["expected"])), "remaining": int(round(r["remaining"])),
            "complete": r["complete"], "baseMargin": r["baseMargin"], "baseSource": r["baseSource"],
            "candidates": [[c[0], c[1], int(c[2] or 0)] for c in r["candidates"]],
            "leaderShare": round(r["aVotes"] / tp, 4) if tp else None,
            "splitA": round(r["splitA"], 4),
            "marginPct": round(100.0 * (r["aVotes"] - r["bVotes"]) / tp, 2) if tp else None,
        })
    return out
