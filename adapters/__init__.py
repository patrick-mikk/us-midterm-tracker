"""Adapter registry: state code -> adapter module.

Each adapter exposes `fetch(ctx) -> dict` in the common schema:
{"state": "NC", "source": "...", "fetchedAt": ms, "races": [{"id", "office", "district", "units": [...]}]}
and a module-level `SOURCE_URL` and `SOURCE_NAME` for the page's source strip.
"""
from . import nc, clarity, demo

LIVE = {
    "NC": nc,
}

# Clarity/Scytl instances. Fill in the election ID from the official state results page on
# election night; without an ID the state is listed as "No live source".
CLARITY_SITES = {
    # "GA": {"path": "GA", "election_id": None},
}


def live_adapters():
    out = dict(LIVE)
    for st, cfg in CLARITY_SITES.items():
        if cfg.get("election_id"):
            out[st] = clarity.make(st, cfg["path"], cfg["election_id"])
    return out
