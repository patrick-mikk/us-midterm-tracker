"""Shared helpers for adapters: polite HTTP, party normalisation, name cleaning."""
import gzip
import json
import re
import time
import urllib.request
import urllib.error

USER_AGENT = "midterms-tracker/1.0 (+https://midterms.mikkelsen.ca)"
TIMEOUT = 20

PARTY_MAP = {
    "DEM": "DEM", "DEMOCRAT": "DEM", "DEMOCRATIC": "DEM", "D": "DEM", "DFL": "DEM", "DNL": "DEM",
    "REP": "REP", "REPUBLICAN": "REP", "R": "REP", "GOP": "REP",
    "IND": "IND", "INDEPENDENT": "IND", "I": "IND", "UNA": "IND", "UNAFFILIATED": "IND", "NPA": "IND", "NP": "IND",
    "LIB": "LIB", "LIBERTARIAN": "LIB", "L": "LIB", "LPF": "LIB",
    "GRN": "GRN", "GRE": "GRN", "GREEN": "GRN", "G": "GRN", "PGP": "GRN",
    "WRI": "OTH", "WRITE-IN": "OTH", "": "OTH",
}

_PAREN_PARTY = re.compile(r"\s*\((DEM|REP|IND|LIB|GRN|GRE|D|R|I|L|G)\)\s*$", re.I)


def norm_party(p):
    if p is None:
        return "OTH"
    key = str(p).strip().upper()
    return PARTY_MAP.get(key, "OTH")


def clean_name(name):
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    return _PAREN_PARTY.sub("", name)


def get(url, timeout=TIMEOUT, retries=1, binary=False):
    """GET with the tracker's User-Agent. Returns bytes (binary) or decoded text."""
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                if binary:
                    return data
                charset = resp.headers.get_content_charset() or "utf-8"
                return data.decode(charset, errors="replace")
        except (urllib.error.URLError, OSError, ValueError) as e:
            last = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed for {url}: {last}")


def get_json(url, **kw):
    return json.loads(get(url, **kw))


def now_ms():
    return int(time.time() * 1000)


def parallel_map(fn, items, workers=8):
    """Run fn over items in threads, returning results in order. Exceptions are returned, not raised."""
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(fn, it) for it in items]
        out = []
        for f in futs:
            try:
                out.append(f.result())
            except Exception as e:  # noqa: BLE001 - one bad unit must not sink the state
                out.append(e)
        return out
