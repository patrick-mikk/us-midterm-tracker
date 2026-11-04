# Live sources (checked 2026-11-04 from a cloud container; re-check from the WHC server)

| State | Source | Endpoint | Format | Status |
|---|---|---|---|---|
| North Carolina | er.ncsbe.gov | `https://er.ncsbe.gov/enr/20261103/data/results_{0..100}.txt` (0 = statewide, 1–100 = counties alphabetical) | JSON array; fields cid, cnm, bnm, pty, vct, prt, ptl, ovc (one-stop early), evc (election day), avc (mail), pvc (provisional) | **Working.** Adapter `adapters/nc.py`, fixtures in `fixtures/`. Candidates for the Senate race confirmed from the feed. 100 small requests per run, in 10 threads. |
| Florida | results.elections.myflorida.com | `downloadresults.asp?ElectionDate=11/3/2026&DATAMODE=` | Tab-delimited text (classic ASP) | Reachable, but the 2026 extract returned a server error on the day after the election. Retry; if it serves, write `adapters/fl.py` for the tab format. |
| Georgia | results.sos.ga.gov (Angular app) and Clarity (`results.enr.clarityelections.com/GA/…`) | Clarity: `{eid}/current_ver.txt`, `{ver}/json/details.json` | JSON | Clarity blocked the container (403). Take the election ID from the official results page and set it in `adapters/__init__.py` `CLARITY_SITES`. Majority rule: runoff below 50%. |
| Pennsylvania | electionreturns.pa.gov | county-level JSON behind the page | JSON | 403 from the container; test from the server. |
| Arizona | results.arizona.vote | — | — | 403 from the container; test from the server. Late-counting state. |
| Michigan | mielections.us | — | — | Connection timed out from the container. |
| Nevada | silverstateelection.nv.gov | — | — | Page loads but is a JS shell; endpoint not yet identified. Late-counting state. |
| Ohio | liveresults.ohiosos.gov | — | — | 403 from the container. |
| Texas | results.texas-election.com | — | — | 403 from the container. |
| Wisconsin | none statewide | county sites only | — | No live source. |
| All others | — | — | — | No live source yet. Listed as "No live source" on the page. |

Rules: official state sources only, one fetch per source per minute, User-Agent
`midterms-tracker/1.0 (+https://midterms.mikkelsen.ca)`, no news-site scraping. Sites that block
data-centre addresses must be re-tested from the hosting server before election night.
