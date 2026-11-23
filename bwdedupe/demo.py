"""Made-up vault for `--demo`, the tests and the screenshots, and a stand-in for the `bw` commands the tool uses."""

from __future__ import annotations

import base64
import copy
import datetime
import json
from pathlib import Path

from .vault import Bw, BwError


def login(item_id, name, username, password, uris, revision, **extra):
    item = {
        "id": item_id, "type": 1, "name": name, "folderId": extra.pop("folder", None),
        "favorite": extra.pop("favorite", False), "reprompt": 0, "notes": extra.pop("notes", None),
        "fields": extra.pop("fields", None), "attachments": extra.pop("attachments", None),
        "organizationId": extra.pop("org", None), "revisionDate": f"{revision}T10:00:00.000Z",
        "login": {"username": username, "password": password, "totp": extra.pop("totp", None),
                  "uris": [{"match": None, "uri": u} for u in uris],
                  "fido2Credentials": extra.pop("passkeys", None)},
    }
    assert not extra, extra
    return item


JANE = "jane.doe@example.com"

FOLDERS = [{"id": "f-shopping", "name": "Shopping"}, {"id": "f-games", "name": "Games"}]

ITEMS = [
    login("amz-1", "Amazon", JANE, "demo-pw-amazon", ["https://www.amazon.fr/ap/signin"], "2024-03-02",
          folder="f-shopping"),
    login("amz-2", "amazon login", "Jane.Doe@example.com ", "demo-pw-amazon",
          ["https://login.amazon.fr", "androidapp://com.amazon.mShop.android.shopping"], "2023-01-15",
          notes="demo-note-prime"),
    login("amz-3", "amazon.fr", JANE, "demo-pw-amazon", ["amazon.fr"], "2022-06-30", favorite=True),
    login("gh-1", "GitHub", "janedoe", "demo-pw-github", ["https://github.com/login"], "2025-01-10",
          totp="demo-totp-github"),
    login("gh-2", "gist", "janedoe", "demo-pw-github", ["https://gist.github.com"], "2021-09-01"),
    login("st-1", "Steam", "jdoe_gamer", "demo-pw-steam-old", ["https://store.steampowered.com/login"], "2020-02-11",
          folder="f-games"),
    login("st-2", "Steam help", "jdoe_gamer", "demo-pw-steam-new", ["https://help.steampowered.com"], "2025-05-20"),
    login("st-3", "steampowered.com", "jdoe_gamer", "demo-pw-steam-old", ["https://steampowered.com"], "2019-12-01"),
    login("goo-1", "Google", JANE, "demo-pw-google", ["https://accounts.google.com"], "2025-02-01",
          passkeys=[{"credentialId": "demo-passkey"}]),
    login("goo-2", "Gmail", JANE, "demo-pw-google", ["https://mail.google.com"], "2022-04-12"),
    login("nf-1", "Netflix", JANE, "demo-pw-netflix", ["https://www.netflix.com/login"], "2023-11-03"),
    login("nf-2", "netflix.com", JANE, "demo-pw-netflix", ["https://netflix.com"], "2021-03-08"),
    login("db-1", "Dropbox", JANE, "demo-pw-dropbox", ["https://www.dropbox.com/login"], "2024-08-19",
          notes="demo-note-recovery", fields=[{"name": "Recovery email", "value": "demo-field", "type": 0}]),
    login("db-2", "dropbox old", JANE, "demo-pw-dropbox", ["https://dropbox.com"], "2020-05-05",
          notes="demo-note-old"),
    login("rd-1", "reddit", "jane_d", "demo-pw-reddit", ["https://old.reddit.com"], "2022-10-10"),
    login("rd-2", "Reddit", "jane_d", "demo-pw-reddit", ["https://www.reddit.com/login"], "2024-12-24"),
    login("eb-1", "eBay", JANE, "demo-pw-ebay", ["https://signin.ebay.fr"], "2023-02-02"),
    login("eb-2", "eBay US", JANE, "demo-pw-ebay", ["https://www.ebay.com"], "2021-07-07"),
    login("blog-a", "blog", "jane", "demo-pw-pages", ["https://alice.github.io/admin"], "2024-01-01"),
    login("blog-b", "other blog", "jane", "demo-pw-pages", ["https://bob.github.io"], "2024-01-02"),
    login("bank", "My Bank", "123456789", "demo-pw-bank", ["https://www.mybank.co.uk/login"], "2025-03-03"),
    login("router", "Router", "admin", "demo-pw-router", ["http://192.168.1.1"], "2020-01-01"),
    login("multi", "Shared login", "jane", "demo-pw-multi", ["https://a.example.com", "https://b.example.org"],
          "2020-01-01"),
    login("org-1", "Work Slack", JANE, "demo-pw-work", ["https://acme.slack.com"], "2024-01-01", org="org-acme"),
    login("org-2", "Slack", JANE, "demo-pw-work", ["https://app.slack.com"], "2024-01-01", org="org-acme"),
]


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class DemoVault:
    """Answers the `bw` commands the tool uses, on a list of items. Status and unlock are left to the caller."""

    def __init__(self, items: list[dict], drop_passkeys: bool = False):
        self.items = items
        self.drop_passkeys = drop_passkeys

    def handle(self, args: list[str], stdin: str | None = None) -> str:
        cmd = args[0]
        if cmd in ("sync", "lock"):
            return "ok"
        if cmd == "list" and args[1] == "folders":
            return json.dumps(FOLDERS)
        if cmd == "list":
            return json.dumps([i for i in self.items if not i.get("deletedDate")])
        if cmd == "edit":
            payload = json.loads(base64.b64decode(stdin or ""))
            payload["revisionDate"] = now()
            if self.drop_passkeys:
                payload.get("login", {}).pop("fido2Credentials", None)
            self.items = [payload if i["id"] == args[2] else i for i in self.items]
            return json.dumps(payload)
        if cmd == "delete":
            for i in self.items:
                if i["id"] == args[2]:
                    i["deletedDate"] = now()
            return ""
        if cmd == "export":
            Path(args[args.index("--output") + 1]).write_text('{"encrypted": true}', encoding="utf-8")
            return ""
        raise ValueError(f"unsupported command: {cmd}")


class DemoBw(Bw):
    """In-process `bw` for `--demo`: an unlocked vault of made-up items, changed in memory only."""

    def __init__(self):
        super().__init__("", "demo")
        self.vault = DemoVault(copy.deepcopy(ITEMS))

    def run(self, *args: str, stdin: str | None = None) -> str:
        if args[0] == "status":
            return json.dumps({"status": "unlocked", "userId": "demo-user"})
        try:
            return self.vault.handle(list(args), stdin)
        except (ValueError, IndexError, KeyError) as err:
            raise BwError(f"bw {' '.join(args[:3])}: {err}") from None

    def export_backup(self, path: Path) -> None:
        self.run("export", "--format", "encrypted_json", "--output", str(path))
