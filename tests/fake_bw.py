#!/usr/bin/env python3
"""Stand-in for the `bw` CLI, backed by a JSON file, for tests and screenshots.

FAKE_VAULT: path of the JSON vault (list of items). The master password is "master",
the session key "fake-session". FAKE_DROP_PASSKEY=1 makes `edit` lose passkeys.
"""

import base64
import datetime
import json
import os
import sys

VAULT = os.environ["FAKE_VAULT"]
SESSION = "fake-session"


def load():
    with open(VAULT, encoding="utf-8") as f:
        return json.load(f)


def save(items):
    with open(VAULT, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=1)


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
    elif cmd in ("sync", "lock"):
        print("ok")
    elif cmd == "list" and args[1] == "folders":
        print(json.dumps([{"id": "f-shopping", "name": "Shopping"}, {"id": "f-games", "name": "Games"}]))
    elif cmd == "list":
        print(json.dumps([i for i in load() if not i.get("deletedDate")]))
    elif cmd == "edit":
        payload = json.loads(base64.b64decode(sys.stdin.read()))
        payload["revisionDate"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if os.environ.get("FAKE_DROP_PASSKEY"):
            payload.get("login", {}).pop("fido2Credentials", None)
        items = [payload if i["id"] == args[2] else i for i in load()]
        save(items)
        print(json.dumps(payload))
    elif cmd == "delete":
        items = load()
        for i in items:
            if i["id"] == args[2]:
                i["deletedDate"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save(items)
    elif cmd == "export":
        with open(args[args.index("--output") + 1], "w", encoding="utf-8") as f:
            f.write('{"encrypted": true}')
    else:
        sys.exit(f"unsupported command: {cmd}")


if __name__ == "__main__":
    main(sys.argv[1:])
