#!/usr/bin/env python3
"""Stand-in for the `bw` CLI, backed by a JSON file, for tests.

FAKE_VAULT: path of the JSON vault (list of items). The master password is "master",
the session key "fake-session". FAKE_DROP_PASSKEY=1 makes `edit` lose passkeys.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bwdedupe.demo import DemoVault  # noqa: E402

VAULT = os.environ["FAKE_VAULT"]
SESSION = "fake-session"


def main(args):
    args = [a for a in args if a != "--nointeraction"]
    unlocked = os.environ.get("BW_SESSION") == SESSION
    cmd = args[0]
    if cmd == "status":
        print(json.dumps({"status": "unlocked" if unlocked else "locked", "userId": "user-1"}))
    elif cmd in ("unlock", "login"):
        sys.stderr.write("? Master password: [input is hidden] ")
        sys.stderr.flush()
        if sys.stdin.readline().strip() != "master":
            sys.exit("Invalid master password.")
        print(SESSION)
    elif not unlocked:
        sys.exit("Vault is locked.")
    else:
        with open(VAULT, encoding="utf-8") as f:
            vault = DemoVault(json.load(f), drop_passkeys=bool(os.environ.get("FAKE_DROP_PASSKEY")))
        try:
            out = vault.handle(args, sys.stdin.read() if cmd == "edit" else None)
        except ValueError as err:
            sys.exit(str(err))
        with open(VAULT, "w", encoding="utf-8") as f:
            json.dump(vault.items, f, indent=1)
        print(out)


if __name__ == "__main__":
    main(sys.argv[1:])
