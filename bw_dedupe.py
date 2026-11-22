#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["tldextract>=5.1"]
# ///
"""Review and merge duplicate Bitwarden logins in a local web UI, through the official `bw` CLI."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import webbrowser
from pathlib import Path

from bwdedupe import unlock
from bwdedupe.server import App
from bwdedupe.state import Session, SessionError
from bwdedupe.vault import Bw, BwError


def main() -> int:
    parser = argparse.ArgumentParser(description="Review and merge duplicate Bitwarden logins.")
    parser.add_argument("--workfile", type=Path, default=Path("bw-dedupe-session.json"),
                        help="file holding your decisions, used to resume later (default: %(default)s)")
    parser.add_argument("--reports", type=Path, default=Path("bw-dedupe-reports"),
                        help="folder for reports and backups (default: %(default)s)")
    parser.add_argument("--port", type=int, default=0, help="local port (default: random)")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    parser.add_argument("--keep-unlocked", action="store_true", help="do not lock the vault when quitting")
    parser.add_argument("--bw", default=shutil.which("bw"), help="path of the bw executable")
    parser.add_argument("--unlock-helper", nargs=2, metavar=("CALLBACK", "TOKEN"), help=argparse.SUPPRESS)
    args = parser.parse_args()

    if not args.bw:
        print("bw not found in PATH. Install the Bitwarden CLI or pass --bw.", file=sys.stderr)
        return 2
    if args.unlock_helper:
        return unlock.run_helper(args.bw, *args.unlock_helper)

    bw = Bw(args.bw, os.environ.get("BW_SESSION"))
    session = Session(bw, args.workfile, args.reports)
    try:
        if bw.status().get("status") != "unlocked" and sys.stdin.isatty():
            bw.session = unlock.prompt_session(args.bw)
            if not bw.session:
                print("Vault not unlocked.", file=sys.stderr)
                return 1
        print("Loading the vault...")
        session.open()
    except (BwError, SessionError) as err:
        print(err, file=sys.stderr)
        return 1

    app = App(session, args.bw, lock_on_quit=not args.keep_unlocked and not os.environ.get("BW_SESSION"))
    app.serve(args.port)
    if not session.unlocked:
        app.request_unlock()
        if app.unlock_error:
            print(app.unlock_error, file=sys.stderr)
    print(f"Open {app.url}\nPress Ctrl+C or use Quit in the page to stop.")
    if not args.no_browser:
        webbrowser.open(app.url)
    try:
        app.httpd.serve_forever()
    except KeyboardInterrupt:
        app.shutdown()
    print("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
