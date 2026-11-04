#!/usr/bin/env python3
"""Laptop only: run fetch.py in a loop and serve site/ at http://127.0.0.1:8766

  python3 scripts/dev_server.py                 # live adapters every 60 s
  python3 scripts/dev_server.py --demo          # simulated night, 30 simulated minutes per real minute
  python3 scripts/dev_server.py --demo --speed 60 --every 10
  python3 scripts/dev_server.py --replay fixtures/snapshots
"""
import argparse, os, subprocess, sys, threading, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=SITE, **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        if "latest.json" not in (args[0] if args else ""):
            super().log_message(fmt, *args)


def loop(args):
    cmd = [sys.executable, os.path.join(ROOT, "fetch.py"), "--no-lock"]
    if args.demo:
        cmd += ["--demo", "--speed", str(args.speed)]
        if args.reset:
            cmd.append("--reset-demo")
    if args.replay:
        cmd += ["--replay", args.replay]
    if args.states:
        cmd += ["--states", args.states]
    first = True
    while True:
        subprocess.call(cmd if first else [c for c in cmd if c != "--reset-demo"])
        first = False
        time.sleep(args.every)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--speed", type=float, default=30.0)
    ap.add_argument("--every", type=float, default=None, help="seconds between runs")
    ap.add_argument("--reset", action="store_true", help="demo: restart the simulated night")
    ap.add_argument("--replay", default=None)
    ap.add_argument("--states", default=None)
    ap.add_argument("--port", type=int, default=8766)
    args = ap.parse_args()
    if args.every is None:
        args.every = 10 if (args.demo or args.replay) else 60
    threading.Thread(target=loop, args=(args,), daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"serving {SITE} at http://127.0.0.1:{args.port}  ({'demo' if args.demo else 'replay' if args.replay else 'live'} mode)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
