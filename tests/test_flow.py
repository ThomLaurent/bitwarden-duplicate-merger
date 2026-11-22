"""End-to-end tests against a fake `bw` CLI. Run with: python -m unittest discover tests"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import demo_vault  # noqa: E402
from bwdedupe import server  # noqa: E402
from bwdedupe.psl import registrable_domain  # noqa: E402
from bwdedupe.state import Session  # noqa: E402
from bwdedupe.vault import Bw  # noqa: E402


@unittest.skipIf(os.name == "nt", "the fake bw is a POSIX script")
class FlowTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.vault = self.dir / "vault.json"
        self.vault.write_text(json.dumps(demo_vault.ITEMS), encoding="utf-8")
        self.bw_exe = self.dir / "bw"
        self.bw_exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{ROOT / "tests" / "fake_bw.py"}" "$@"\n')
        self.bw_exe.chmod(0o755)
        os.environ["FAKE_VAULT"] = str(self.vault)
        os.environ.pop("FAKE_DROP_PASSKEY", None)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def session(self, key="fake-session") -> Session:
        s = Session(Bw(str(self.bw_exe), key), self.dir / "work.json", self.dir / "reports")
        s.open()
        return s

    def vault_items(self) -> dict:
        return {i["id"]: i for i in json.loads(self.vault.read_text(encoding="utf-8"))}

    @staticmethod
    def by_domain(s: Session) -> dict:
        return {g["domain"]: g for g in s.groups}

    def apply(self, s: Session, group_ids, backup=False):
        s.start_apply(group_ids, backup)
        while s.progress["running"]:
            time.sleep(0.05)
        return s.data["runs"][-1]

    def test_suggestions(self):
        groups = self.by_domain(self.session())
        kinds = {d: g["kind"] for d, g in groups.items()}
        self.assertEqual(kinds, {
            "amazon.fr": "rule", "github.com": "rule", "netflix.com": "rule", "dropbox.com": "rule",
            "reddit.com": "rule", "steampowered.com": "conflict", "google.com": "skipped",
        })
        amazon = groups["amazon.fr"]["decision"]
        self.assertEqual(amazon["keep"], "amz-1")
        self.assertEqual(amazon["name"], "amazon.fr")
        self.assertEqual([u["uri"] for u in amazon["uris"]],
                         ["https://amazon.fr", "androidapp://com.amazon.mShop.android.shopping"])
        self.assertEqual(groups["github.com"]["decision"]["totpFrom"], "gh-1")
        labels = self.session().group_view(groups["steampowered.com"])["passwordLabels"]
        self.assertEqual(labels["st-1"], labels["st-3"])
        self.assertNotEqual(labels["st-1"], labels["st-2"])

    def test_apply_with_user_decisions(self):
        s = self.session()
        groups = self.by_domain(s)
        for d in ("amazon.fr", "github.com", "dropbox.com"):
            s.update_group(groups[d]["id"], groups[d]["decision"], "validated")
        steam = groups["steampowered.com"]
        decision = dict(steam["decision"], action="merge", keep="st-1", usernameFrom="st-1", passwordFrom="st-2",
                        include=["st-1", "st-2"], notesFrom=[])
        s.update_group(steam["id"], decision, "validated")
        manual = s.create_group(["eb-1", "eb-2"])
        s.update_group(manual, s.group(manual)["decision"], "validated")
        self.assertEqual(s.rename(["bank"]), 1)

        run = self.apply(s, [g["id"] for g in s.groups], backup=True)
        items = self.vault_items()
        trashed = {i for i, v in items.items() if v.get("deletedDate")}
        self.assertEqual(trashed, {"amz-2", "amz-3", "gh-2", "db-2", "st-2", "eb-2"})
        self.assertEqual(items["st-1"]["login"]["password"], "demo-pw-steam-new")
        self.assertEqual(items["amz-1"]["notes"], "demo-note-prime")
        self.assertTrue(items["amz-1"]["favorite"])
        self.assertEqual(items["db-1"]["notes"], "demo-note-recovery\n\n----\n\ndemo-note-old")
        self.assertEqual(items["bank"]["name"], "mybank.co.uk")
        self.assertEqual([u["uri"] for u in items["eb-1"]["login"]["uris"]], ["https://ebay.fr", "https://ebay.com"])
        self.assertEqual(run["counts"]["stale"], 0)
        self.assertEqual(run["counts"]["byYou"], 3)

        stored = (self.dir / "work.json").read_text(encoding="utf-8")
        stored += Path(run["report"]).read_text(encoding="utf-8")
        for secret in demo_vault.SECRETS:
            self.assertNotIn(secret, stored)

    def test_resume_flags_changed_items(self):
        s = self.session()
        g = self.by_domain(s)["netflix.com"]
        s.update_group(g["id"], g["decision"], "validated")
        items = json.loads(self.vault.read_text(encoding="utf-8"))
        for i in items:
            if i["id"] == "nf-2":
                i["revisionDate"] = "2099-01-01T00:00:00.000Z"
        self.vault.write_text(json.dumps(items), encoding="utf-8")
        self.assertEqual(self.by_domain(self.session())["netflix.com"]["status"], "stale")

    def test_apply_skips_items_changed_after_review(self):
        s = self.session()
        g = self.by_domain(s)["reddit.com"]
        s.update_group(g["id"], g["decision"], "validated")
        items = json.loads(self.vault.read_text(encoding="utf-8"))
        for i in items:
            if i["id"] == "rd-1":
                i["revisionDate"] = "2099-01-01T00:00:00.000Z"
        self.vault.write_text(json.dumps(items), encoding="utf-8")
        run = self.apply(s, [g["id"]])
        self.assertEqual(run["results"][0]["outcome"], "stale")
        self.assertFalse(any(i.get("deletedDate") for i in self.vault_items().values()))

    def test_lost_passkey_stops_the_merge(self):
        os.environ["FAKE_DROP_PASSKEY"] = "1"
        s = self.session()
        g = self.by_domain(s)["google.com"]
        s.update_group(g["id"], dict(g["decision"], action="merge"), "validated")
        run = self.apply(s, [g["id"]])
        self.assertEqual(run["results"][0]["outcome"], "failed")
        self.assertFalse(self.vault_items()["goo-2"].get("deletedDate"))

    def test_server_access_control(self):
        s = self.session()
        app = server.App(s, str(self.bw_exe), lock_on_quit=False)
        app.serve(0)
        threading.Thread(target=app.httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{app.port}"

        def status(path, headers=None, data=None):
            req = urllib.request.Request(base + path, data=data, headers=headers or {})
            try:
                with urllib.request.urlopen(req) as res:
                    return res.status
            except urllib.error.HTTPError as err:
                return err.code

        self.assertEqual(status("/api/state"), 401)
        self.assertEqual(status("/api/state", {"X-Token": app.token}), 200)
        self.assertEqual(status("/api/state", {"X-Token": app.token, "Host": f"evil.test:{app.port}"}), 403)
        self.assertEqual(status("/unlock-callback", data=b'{"token":"guess","session":"x"}'), 403)
        self.assertEqual(status("/../bwdedupe/state.py"), 404)
        app.httpd.shutdown()


class PslTest(unittest.TestCase):
    def test_domains(self):
        cases = {
            "login.amazon.fr": "amazon.fr", "www.amazon.co.uk": "amazon.co.uk",
            "alice.github.io": "alice.github.io", "github.io": None, "192.168.1.1": None, "::1": None,
            "localhost": None, "router.lan": None, "a.b.www.ck": "www.ck", "x.y.ck": "x.y.ck",
            "www.münchen.de": "münchen.de", "shop.xn--mnchen-3ya.de": "münchen.de",
        }
        for host, expected in cases.items():
            self.assertEqual(registrable_domain(host), expected, host)


if __name__ == "__main__":
    unittest.main()
