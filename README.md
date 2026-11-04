# Midterms 2026 Tracker

Public results tracker for the 2026 US Senate, House and governor races, with the tracker's own
statistical projections, path-to-victory simulations and county-level geographic analysis.
Python 3 standard library only, no build step, one static page.

```
fetch.py            cron entry point: fetch sources, run the model, write site/data/*.json
model.py            projection model (expected vote, Monte Carlo, status rules); CONFIG + CALLS_ENABLED
chambers.py         Senate / House / governor totals and joint seat simulations
adapters/           nc.py (live), clarity.py (generic Scytl/Clarity), demo.py (simulated night)
data/               races.json, holdovers.json, baselines.json (built by scripts/)
site/index.html     the dashboard (dark theme default, simple and advanced views)
scripts/            build_races.py, build_baselines.py, dev_server.py, record.py, backtest.py
tests/              unit tests, adapter fixture tests, backtest
```

## Run it on a Windows laptop (or any laptop)

Needs Python 3.9 or newer from python.org (tick "Add python.exe to PATH" in the installer). Then:

- **Live sources**: double-click `run_local.bat` (or `py run_local.py`).
- **Simulated night**: double-click `run_demo.bat` (or `py run_local.py --demo --reset`).

A console window stays open, the page opens in your browser at http://127.0.0.1:8766, and both the
data (every 60 seconds live, 10 in demo) and the page (every 20 seconds) refresh on their own.
Close the window to stop. Options: `--states NC` to fetch only some states, `--every 30` to change
the update interval, `--speed 60` for a faster demo night, `--port 9000` for another port.

## Run it on the laptop (developer loop)

```bash
python3 scripts/dev_server.py --demo          # simulated election night at http://127.0.0.1:8766
python3 scripts/dev_server.py                 # live sources (currently North Carolina)
python3 fetch.py --demo --demo-minutes 240    # one simulated run at 23:00 ET
python3 -m unittest                           # unit tests plus a short backtest
BACKTEST_NIGHTS=200 python3 -m unittest tests.test_backtest   # the full backtest
```

The demo clock starts at 19:00 ET and advances 30 simulated minutes per real minute
(`--speed`). Use `--reset` to restart the night. Every page in demo mode carries a
"Simulated election night" banner.

## Deploy to cPanel (WHC)

1. **Subdomain**: create `midterms.mikkelsen.ca` in cPanel > Domains. Note its document root and
   put it in `.cpanel.yml` (`DOCROOT`) if it is not `$HOME/midterms.mikkelsen.ca`.
2. **Git Version Control**: clone this repo on the server, then Deploy HEAD. `.cpanel.yml` copies
   the code to `$HOME/midterms-tracker/` and the site files to the document root. It never touches
   `state/`, `logs/` or the generated `data/` on the server.
3. **Cron job** (cPanel > Cron Jobs), every minute or the shortest interval WHC allows:

   ```
   * * * * * cd $HOME/midterms-tracker && /usr/bin/python3 fetch.py >> logs/fetch.log 2>&1
   ```

   Confirm `/usr/bin/python3 --version` is 3.9 or newer. If the interval is longer than a minute,
   set `UPDATE_INTERVAL_SEC` in `fetch.py` so the page says so.
4. After two minutes check `logs/fetch.log` and load the page once with the browser console open.

**Pause updates**: disable the cron job. The page shows "Updates paused" once the data is more than
five minutes old. **Redeploy**: push to GitHub, then Deploy HEAD in Git Version Control (the
server's working tree must be clean).

## Statuses

| Status | Meaning |
|---|---|
| No live source | The state has no adapter tonight. Counted as uncalled. |
| No votes yet | Nothing counted. |
| Too early to call | Under 25% of the expected vote in (50% in late-counting states), or no other rule met. |
| Leader · N% | Leader shown with the share of simulations they win. |
| Projected winner | Leader wins at least 99.5% of simulations, the trailing candidate would need 75% or more of 1.5× the remaining vote, and enough is counted. |
| Projection withdrawn | A projected race fell below the bar. Stays marked for the night; logged in `state/`. |
| Runoff likely / RCV tabulation | Majority or ranked-choice state with nobody projected over 50%. |
| Final count | Every county reports all precincts. |

`CALLS_ENABLED` in `model.py` switches projections off (leaders only). All thresholds are in `CONFIG`.

## Model in brief

Expected vote per county = max(counted, baseline × turnout factor), the factor being the median of
counted ÷ baseline across complete counties; with precinct data, counted ÷ precinct share is also
used once 30% of precincts are in. The remaining vote in a county splits like its counted vote once
20% is in, blended toward its baseline below that. 1000 Monte Carlo draws per race with a shared
national shift (so chamber simulations are correlated), a statewide shift, county turnout noise and
county split noise. Chamber seat distributions, control probabilities and tipping-point races come
from combining races draw by draw.

Baselines: `scripts/build_baselines.py` writes statewide 2024 priors; pass MEDSL county CSVs to add
county-level baselines, which the model prefers when present.

## Sources

See `SOURCES.md`. Only official state election offices are used. Projections are this tracker's own
model output, not media calls.
