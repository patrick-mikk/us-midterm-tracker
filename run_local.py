#!/usr/bin/env python3
"""One-click local tracker for Windows, macOS or Linux.

Double-click run_local.bat on Windows, or run:  python run_local.py [--demo] [--states NC]

It runs fetch.py on a loop in the background, serves the page at http://127.0.0.1:8766 and opens
your browser. The page itself refreshes every 20 seconds; the data refreshes every 60 seconds in
live mode (every 10 seconds in demo mode). Close the window or press Ctrl-C to stop.
"""
import argparse, os, subprocess, sys, threading, time, webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(ROOT, "site")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=SITE, **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):  # keep the console quiet
        pass


def update_loop(args):
    cmd = [sys.executable, os.path.join(ROOT, "fetch.py"), "--no-lock"]
    if args.demo:
        cmd += ["--demo", "--speed", str(args.speed)]
    if args.states:
        cmd += ["--states", args.states]
    every = args.every or (10 if args.demo else 60)
    first = True
    while True:
        try:
            subprocess.call(cmd + (["--reset-demo"] if (first and args.demo and args.reset) else []), cwd=ROOT)
        except Exception as e:  # noqa: BLE001
            print("update failed:", e)
        first = False
        time.sleep(every)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="simulated election night instead of live sources")
    ap.add_argument("--speed", type=float, default=30.0, help="demo: simulated minutes per real minute")
    ap.add_argument("--reset", action="store_true", help="demo: restart the simulated night")
    ap.add_argument("--states", default=None, help="live: comma list of states, e.g. NC")
    ap.add_argument("--every", type=int, default=None, help="seconds between data updates")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    if sys.version_info < (3, 9):
        sys.exit("Python 3.9 or newer is needed (you have %s)" % sys.version.split()[0])
    os.makedirs(os.path.join(SITE, "data"), exist_ok=True)
    threading.Thread(target=update_loop, args=(args,), daemon=True).start()
    srv = None
    for port in range(args.port, args.port + 10):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if srv is None:
        sys.exit(f"no free port between {args.port} and {args.port + 9}")
    url = f"http://127.0.0.1:{port}/"
    print(f"Midterms tracker running at {url}  ({'demo' if args.demo else 'live'} mode)")
    print("Leave this window open. Press Ctrl-C to stop.")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
