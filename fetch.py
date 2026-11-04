#!/usr/bin/env python3
"""Cron entry point for the midterms tracker.

  python3 fetch.py                      one live run, writes site/data (or --out DIR)
  python3 fetch.py --demo [--speed 30]  one simulated-night run; the simulated clock advances
                                        `speed` minutes per real minute from the first demo run
  python3 fetch.py --replay fixtures/ --out site/data   step through recorded snapshots
  python3 fetch.py --states NC,PA       limit live adapters to these states

Runs under a lock so overlapping cron runs exit at once. Each state source is fetched in its own
thread with a 20 s timeout; a failing source keeps its last good data and is marked stale.
Only races whose counts changed are re-simulated; the rest reuse cached summaries and draws.
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import traceback
import concurrent.futures as cf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import model      # noqa: E402
import chambers   # noqa: E402
import adapters   # noqa: E402
from adapters import demo as demo_adapter  # noqa: E402

DATA = os.path.join(HERE, "data")
STATE = os.path.join(HERE, "state")
LOGS = os.path.join(HERE, "logs")
LOCK = os.path.join(STATE, "fetch.lock")
STALE_MS = 5 * 60 * 1000
SOURCE_TIMEOUT = 20
UPDATE_INTERVAL_SEC = 60
HISTORY_MAX = 240


# ------------------------------------------------------------------ helpers
def acquire_lock(path):
    """Non-blocking exclusive lock. Works on Linux/macOS (fcntl) and Windows (msvcrt).
    Returns the open file handle (keep it alive) or None if another run holds the lock."""
    fh = open(path, "a+")
    try:
        if os.name == "nt":
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fh
    except OSError:
        fh.close()
        return None


def eastern_now_label(ms):
    t = dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        t = t.astimezone(ZoneInfo("America/New_York"))
    except Exception:  # noqa: BLE001 - no tzdata on the host
        t = t.astimezone(dt.timezone(dt.timedelta(hours=-5)))
    return t.strftime("%H:%M:%S ET")


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json_atomic(path, obj, compact=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        if compact:
            json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)
        else:
            json.dump(obj, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def log(msg):
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} {msg}", flush=True)


def trim_log(path, keep=2000):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if len(lines) > keep:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines[-keep:])
    except OSError:
        pass


def race_signature(units):
    """Cheap fingerprint of the counts in a race, used to skip unchanged races."""
    sig = 0
    for u in units:
        sig = (sig * 1000003 + (u.get("precinctsReported") or 0)) & 0xFFFFFFFFFFFF
        for c in u.get("candidates", []):
            sig = (sig * 1000003 + int(c[2] or 0)) & 0xFFFFFFFFFFFF
    return f"{len(units)}:{sig}"


# ------------------------------------------------------------------ fetching
def run_live_adapters(states_filter=None):
    """Fetch every registered live source in parallel. Returns {state: result or Exception}."""
    reg = adapters.live_adapters()
    if states_filter:
        reg = {k: v for k, v in reg.items() if k in states_filter}
    out = {}
    if not reg:
        return out, reg
    with cf.ThreadPoolExecutor(max_workers=min(8, len(reg))) as ex:
        futs = {ex.submit(mod.fetch, {}): st for st, mod in reg.items()}
        for fut, st in futs.items():
            try:
                out[st] = fut.result(timeout=SOURCE_TIMEOUT + 10)
            except Exception as e:  # noqa: BLE001
                out[st] = e
    return out, reg


def demo_sim_minutes(speed, reset=False):
    path = os.path.join(STATE, "demo_clock.json")
    clock = load_json(path, None)
    now = time.time()
    if reset or not clock or clock.get("speed") != speed:
        clock = {"start": now, "speed": speed}
        write_json_atomic(path, clock)
    return (now - clock["start"]) / 60.0 * speed


def run_demo(races_doc, baselines, speed, reset=False, fixed_minutes=None):
    sim_minutes = fixed_minutes if fixed_minutes is not None else demo_sim_minutes(speed, reset)
    out = {}
    for st in races_doc["states"]:
        out[st] = demo_adapter.fetch_state(st, races_doc, baselines, sim_minutes)
    return out, sim_minutes


def run_replay(replay_dir, step):
    """Each snapshot file in replay_dir is {state: adapter_result}. Returns the step-th snapshot."""
    files = sorted(f for f in os.listdir(replay_dir) if f.endswith(".json"))
    if not files:
        raise SystemExit("no snapshots in " + replay_dir)
    f = files[min(step, len(files) - 1)]
    return load_json(os.path.join(replay_dir, f), {}), f, len(files)


# ------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "site", "data"))
    ap.add_argument("--demo", action="store_true", help="simulated election night")
    ap.add_argument("--speed", type=float, default=30.0, help="demo: simulated minutes per real minute")
    ap.add_argument("--demo-minutes", type=float, default=None, help="demo: fixed simulated minute (testing)")
    ap.add_argument("--reset-demo", action="store_true")
    ap.add_argument("--replay", default=None, help="directory of recorded snapshots")
    ap.add_argument("--replay-step", type=int, default=None)
    ap.add_argument("--states", default=None, help="comma list of states to fetch live")
    ap.add_argument("--draws", type=int, default=None)
    ap.add_argument("--no-lock", action="store_true")
    args = ap.parse_args(argv)

    os.makedirs(STATE, exist_ok=True)
    os.makedirs(LOGS, exist_ok=True)
    lock_fh = None
    if not args.no_lock:
        lock_fh = acquire_lock(LOCK)
        if lock_fh is None:
            log("previous run still going; exiting")
            return 0
    t0 = time.time()
    if args.draws:
        model.CONFIG["draws"] = args.draws
    n_draws = model.CONFIG["draws"]

    races_doc = load_json(os.path.join(DATA, "races.json"), {"races": [], "states": {}})
    holdovers = load_json(os.path.join(DATA, "holdovers.json"), {"holdovers": {}})
    baselines = load_json(os.path.join(DATA, "baselines.json"), {"states": {}, "counties": {}})
    memory = load_json(os.path.join(STATE, "memory.json"), {"races": {}, "signatures": {}, "summaries": {}})
    draw_cache = load_json(os.path.join(STATE, "draws.json"), {})
    history = load_json(os.path.join(STATE, "history.json"), {"races": {}, "chambers": {}})
    lastgood = load_json(os.path.join(STATE, "lastgood.json"), {})
    now_ms = int(time.time() * 1000)

    # ---- gather source results
    mode = "live"
    sim_minutes = None
    replay_label = None
    registry = {}
    if args.demo:
        mode = "demo"
        results, sim_minutes = run_demo(races_doc, baselines, args.speed, args.reset_demo, args.demo_minutes)
    elif args.replay:
        mode = "replay"
        step = args.replay_step
        if step is None:
            step = memory.get("replayStep", -1) + 1
        results, replay_label, n_files = run_replay(args.replay, step)
        memory["replayStep"] = step if step < n_files - 1 else -1
    else:
        states_filter = set(args.states.split(",")) if args.states else None
        results, registry = run_live_adapters(states_filter)

    # ---- source health, with last-good fallback
    sources = []
    by_state = {}
    for st, res in results.items():
        if isinstance(res, Exception):
            prev = lastgood.get(st)
            err = str(res)[:200]
            log(f"{st}: FAIL {err}")
            if prev:
                by_state[st] = prev
                sources.append({"state": st, "ok": False, "stale": True, "fetchedAt": prev.get("fetchedAt"),
                                "error": err, "source": prev.get("source"), "name": prev.get("sourceName")})
            else:
                sources.append({"state": st, "ok": False, "stale": True, "fetchedAt": None, "error": err,
                                "source": getattr(registry.get(st), "SOURCE_URL", None),
                                "name": getattr(registry.get(st), "SOURCE_NAME", st)})
            continue
        by_state[st] = res
        if mode == "live":
            lastgood[st] = res
        sources.append({"state": st, "ok": True, "stale": False, "fetchedAt": res.get("fetchedAt"),
                        "source": res.get("source"), "name": res.get("sourceName"),
                        "partial": res.get("partial", 0), "warnings": res.get("warnings", [])})
    # states with an adapter that was not run this time keep last good data
    if mode == "live":
        for st, prev in lastgood.items():
            if st not in by_state:
                by_state[st] = prev
                sources.append({"state": st, "ok": False, "stale": True, "fetchedAt": prev.get("fetchedAt"),
                                "error": "not fetched this run", "source": prev.get("source"), "name": prev.get("sourceName")})
    for s in sources:
        if s["fetchedAt"] and now_ms - s["fetchedAt"] > STALE_MS:
            s["stale"] = True

    units_by_race = {}
    for st, res in by_state.items():
        for r in res.get("races", []):
            units_by_race[r["id"]] = r.get("units", [])
    states_with_source = set(by_state)

    # ---- model
    summaries = []
    draws = {}
    state_detail = {}
    changed = reused = 0
    mem_races = memory.setdefault("races", {})
    sigs = memory.setdefault("signatures", {})
    cached = memory.setdefault("summaries", {})
    house_seats = {st: info.get("houseSeats", 1) for st, info in races_doc.get("states", {}).items()}
    for race in races_doc["races"]:
        rid = race["id"]
        race = dict(race)
        race["lateCount"] = races_doc["states"].get(race["state"], {}).get("lateCount", False)
        race["houseSeats"] = house_seats.get(race["state"], 1)
        units = units_by_race.get(rid)
        if units is None:
            s = {"id": rid, "state": race["state"], "office": race["office"], "district": race.get("district"),
                 "name": race.get("name"), "winRule": race.get("winRule"), "special": race.get("special", False),
                 "incumbentParty": race.get("incumbentParty"), "lateCount": race["lateCount"],
                 "status": "no_source",
                 "candidates": [{"name": c[0], "party": c[1], "votes": 0, "share": None, "p": None} for c in race.get("candidates", [])],
                 "leader": None, "counted": 0, "expected": None, "remaining": None, "pctExpected": 0.0,
                 "margin": 0, "marginPct": None, "winProbParty": {}, "needs": None, "hist": None,
                 "units": 0, "completeUnits": 0, "callHistory": []}
            summaries.append(s)
            continue
        sig = race_signature(units)
        if sigs.get(rid) == sig and rid in cached and rid in draw_cache and len(draw_cache[rid]) == n_draws:
            s = cached[rid]
            summaries.append(s)
            draws[rid] = draw_cache[rid]
            reused += 1
            detail = state_detail.setdefault(race["state"], {})
            detail[rid] = memory.get("details", {}).get(rid)
            continue
        mem = mem_races.setdefault(rid, {})
        try:
            s, m, rows = model.project_race(race, units, baselines, mem)
        except Exception:  # noqa: BLE001
            log(f"{rid}: model error\n{traceback.format_exc()}")
            continue
        if mem.get("statusChangedAt") is None and s["callHistory"]:
            mem["statusChangedAt"] = now_ms
            s["callHistory"][-1]["at"] = now_ms
        s["statusChangedAt"] = mem.get("statusChangedAt")
        s["updatedAt"] = now_ms
        summaries.append(s)
        draws[rid] = [round(x, 1) for x in m]
        sigs[rid] = sig
        cached[rid] = s
        detail_rows = model.unit_detail_rows(rows, s["candidates"][0], s["candidates"][1])
        memory.setdefault("details", {})[rid] = detail_rows
        state_detail.setdefault(race["state"], {})[rid] = detail_rows
        changed += 1
    # keep previously computed details for reused races
    details_mem = memory.get("details", {})
    for st in states_with_source:
        for s in summaries:
            if s["state"] == st and s["id"] in details_mem:
                state_detail.setdefault(st, {}).setdefault(s["id"], details_mem[s["id"]])

    # ---- history (win probability over time)
    hist_r = history.setdefault("races", {})
    for s in summaries:
        if s["status"] == "no_source":
            continue
        p_dem = s.get("winProbParty", {}).get("DEM")
        if p_dem is None:
            continue
        h = hist_r.setdefault(s["id"], [])
        if not h or h[-1][1] != round(p_dem, 3) or h[-1][2] != round(s["pctExpected"], 3):
            h.append([now_ms, round(p_dem, 3), round(s["pctExpected"], 3)])
            del h[:-HISTORY_MAX]

    # ---- chambers
    hold = holdovers.get("holdovers", {})
    ch = {
        "senate": chambers.summarise("us_senate", summaries, draws, hold, n_draws),
        "house": chambers.summarise("us_house", summaries, draws, {}, n_draws),
        "governors": chambers.summarise("governor", summaries, draws, {}, n_draws),
    }
    hist_c = history.setdefault("chambers", {})
    for key, block in ch.items():
        h = hist_c.setdefault(key, [])
        pc = block.get("controlProb", {}).get("DEM")
        h.append([now_ms, pc, block["expectedSeats"]["DEM"], block["expectedSeats"]["REP"]])
        del h[:-HISTORY_MAX]
        block["history"] = h[-120:]

    # ---- public files
    out_dir = args.out
    latest = {
        "generatedAt": now_ms, "generatedLabel": eastern_now_label(now_ms), "mode": mode,
        "simMinutes": sim_minutes, "replay": replay_label,
        "callsEnabled": model.CALLS_ENABLED, "updateIntervalSec": UPDATE_INTERVAL_SEC,
        "draws": n_draws, "model": {k: model.CONFIG[k] for k in (
            "sigma_national", "sigma_state", "sigma_turnout", "sigma_county", "min_share_for_call",
            "late_count_min_share", "call_win_prob", "call_needs_share", "call_remaining_multiplier")},
        "cycle": races_doc.get("cycle"), "electionDate": races_doc.get("electionDate"),
        "holdovers": holdovers, "chambers": ch, "sources": sources,
        # 2024 presidential two-party margin per state, DEM positive, for the swing views
        "priors": {st: -v["margin2024"] for st, v in baselines.get("states", {}).items() if v.get("margin2024") is not None},
        "states": {st: {"name": info["name"], "pollCloseET": info["pollCloseET"], "lateCount": info["lateCount"],
                        "houseSeats": info["houseSeats"], "hasSource": st in states_with_source}
                   for st, info in races_doc.get("states", {}).items()},
        "races": summaries,
        "runSeconds": round(time.time() - t0, 2), "changed": changed, "reused": reused,
    }
    # keep latest.json small: House races carry their histogram and call log in the state file only
    slim = []
    for s in summaries:
        s2 = dict(s)
        s2.pop("leader", None)
        s2["callHistory"] = s.get("callHistory", [])[-1:]
        if s["office"] == "us_house":
            s2.pop("hist", None)
        slim.append(s2)
    latest["races"] = slim
    write_json_atomic(os.path.join(out_dir, "latest.json"), latest)
    full_by_id = {s["id"]: s for s in summaries}
    for st, races_detail in state_detail.items():
        rh = {rid: hist_r.get(rid, [])[-120:] for rid in races_detail}
        extra = {rid: {"hist": full_by_id[rid].get("hist"), "callHistory": full_by_id[rid].get("callHistory", [])}
                 for rid in races_detail if rid in full_by_id}
        write_json_atomic(os.path.join(out_dir, "states", f"{st}.json"),
                          {"state": st, "generatedAt": now_ms, "races": races_detail, "history": rh, "model": extra})
    write_json_atomic(os.path.join(out_dir, "status.json"),
                      {"generatedAt": now_ms, "mode": mode, "sources": sources, "runSeconds": latest["runSeconds"],
                       "changed": changed, "reused": reused})

    # ---- private state
    memory["signatures"] = sigs
    memory["summaries"] = cached
    write_json_atomic(os.path.join(STATE, "memory.json"), memory)
    write_json_atomic(os.path.join(STATE, "draws.json"), draws)
    write_json_atomic(os.path.join(STATE, "history.json"), history)
    if mode == "live":
        write_json_atomic(os.path.join(STATE, "lastgood.json"), lastgood)
    trim_log(os.path.join(LOGS, "fetch.log"))
    called = sum(1 for s in summaries if s["status"] in ("projected", "final"))
    log(f"{mode}: {len(by_state)} sources, {changed} races modelled, {reused} reused, {called} called, "
        f"{latest['runSeconds']}s" + (f", sim t+{sim_minutes:.0f}min" if sim_minutes is not None else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
