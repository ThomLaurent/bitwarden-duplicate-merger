#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Review and merge duplicate Bitwarden logins in a local web UI, through the official `bw` CLI."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import webbrowser
from pathlib import Path

from bwdedupe import bwcli, unlock
from bwdedupe.demo import DemoBw
from bwdedupe.server import App
from bwdedupe.state import Session, SessionError
from bwdedupe.vault import Bw, BwError


def main() -> int:
    parser = argparse.ArgumentParser(description="Review and merge duplicate Bitwarden logins.")
    parser.add_argument("--workfile", type=Path,
                        help="file holding your decisions, used to resume later (default: bw-dedupe-session.json)")
    parser.add_argument("--reports", type=Path, help="folder for reports and backups (default: bw-dedupe-reports)")
    parser.add_argument("--port", type=int, default=0, help="local port (default: random)")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    parser.add_argument("--keep-unlocked", action="store_true", help="do not lock the vault when quitting")
    parser.add_argument("--bw", help="path of the bw executable (default: found in PATH, or downloaded)")
    parser.add_argument("--demo", action="store_true",
                        help="try the tool on a made-up vault, without bw or a Bitwarden account")
    parser.add_argument("--unlock-helper", nargs=2, metavar=("CALLBACK", "TOKEN"), help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.demo:
        folder = Path(tempfile.mkdtemp(prefix="bw-dedupe-demo-"))
        print(f"Demo: made-up vault, changes stay in memory. Work file and reports go to {folder}", flush=True)
        bw: Bw = DemoBw()
        exe = ""
        workfile, reports = args.workfile or folder / "bw-dedupe-session.json", args.reports or folder / "reports"
    else:
        exe = bwcli.resolve(args.bw, sys.stdin.isatty())
        if not exe:
            return 2
        if args.unlock_helper:
            return unlock.run_helper(exe, *args.unlock_helper)
        bw = Bw(exe, os.environ.get("BW_SESSION"))
        workfile = args.workfile or Path("bw-dedupe-session.json")
        reports = args.reports or Path("bw-dedupe-reports")

    session = Session(bw, workfile, reports)
    try:
        if not args.demo and bw.status().get("status") != "unlocked" and sys.stdin.isatty():
            bw.session = unlock.prompt_session(exe)
            if not bw.session:
                print("Vault not unlocked.", file=sys.stderr)
                return 1
        print("Loading the vault...", flush=True)
        session.open()
    except (BwError, SessionError) as err:
        print(err, file=sys.stderr)
        return 1

    app = App(session, exe, demo=args.demo,
              lock_on_quit=not args.demo and not args.keep_unlocked and not os.environ.get("BW_SESSION"))
    app.serve(args.port)
    if not session.unlocked:
        app.request_unlock()
        if app.unlock_error:
            print(app.unlock_error, file=sys.stderr)
    print(f"Open {app.url}\nPress Ctrl+C or use Quit in the page to stop.", flush=True)
    if not args.no_browser:
        webbrowser.open(app.url)
    try:
        app.httpd.serve_forever()
    except KeyboardInterrupt:
        app.shutdown()
    print("Stopped.")
    return 0


def pause_on_error(code: int) -> int:
    # A double-clicked Windows executable runs in a console window that closes as soon as it exits.
    if code and getattr(sys, "frozen", False) and sys.platform == "win32" and sys.stdin.isatty():
        input("Press Enter to close this window.")
    return code


if __name__ == "__main__":
    sys.exit(pause_on_error(main()))
