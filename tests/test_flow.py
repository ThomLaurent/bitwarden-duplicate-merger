"""End-to-end tests against a fake `bw` CLI. Run with: python -m unittest discover tests"""

from __future__ import annotations

import hashlib
import io
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
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import bw_dedupe  # noqa: E402
import demo_vault  # noqa: E402
from bwdedupe import bwcli, server, unlock  # noqa: E402
from bwdedupe.demo import DemoBw  # noqa: E402
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


class DemoTest(unittest.TestCase):
    def test_demo_vault_merges_in_memory(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        s = Session(DemoBw(), folder / "work.json", folder / "reports")
        s.open()
        g = next(g for g in s.groups if g["domain"] == "netflix.com")
        s.update_group(g["id"], g["decision"], "validated")
        s.start_apply([g["id"]], True)
        while s.progress["running"]:
            time.sleep(0.05)
        self.assertEqual(s.data["runs"][-1]["counts"]["stale"], 0)
        self.assertTrue(next(i for i in s.bw.vault.items if i["id"] == "nf-2").get("deletedDate"))
        self.assertFalse(any(i.get("deletedDate") for i in demo_vault.ITEMS))


def bw_zip(name="bw") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("README.txt", "not this one")
        z.writestr(name, "#!/bin/sh\necho 2026.11.0\n")
    return buf.getvalue()


def release(tag, assets, **extra):
    return {"tag_name": tag, "draft": False, "prerelease": False, **extra,
            "assets": [{"name": n, "browser_download_url": f"https://dl.test/{n}", "size": 42_000_000, **a}
                       for n, a in assets.items()]}


class BwCliTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.archive = bw_zip()
        self.digest = "sha256:" + hashlib.sha256(self.archive).hexdigest()

    def test_platforms(self):
        self.assertEqual(bwcli.asset_platform("win32", "ARM64"), "windows")
        self.assertEqual(bwcli.asset_platform("darwin", "arm64"), "macos-arm64")
        self.assertEqual(bwcli.asset_platform("darwin", "x86_64"), "macos")
        self.assertEqual(bwcli.asset_platform("linux", "aarch64"), "linux-arm64")
        self.assertEqual(bwcli.asset_platform("linux", "x86_64"), "linux")

    def test_pick_release(self):
        releases = [
            release("desktop-v2026.11.1", {"bw-windows-2026.11.1.zip": {"digest": self.digest}}),
            release("cli-v2026.12.0", {"bw-windows-2026.12.0.zip": {"digest": self.digest}}, prerelease=True),
            release("cli-v2026.11.0", {"bw-oss-windows-2026.11.0.zip": {"digest": "sha256:AA"},
                                       "bw-windows-2026.11.0.zip": {"digest": "sha256:BB"},
                                       "bw-linux-2026.11.0.zip": {}}),
            release("cli-v2026.10.0", {"bw-macos-arm64-2026.10.0.zip": {"digest": "sha256:cc"}}),
        ]
        win = bwcli.pick_release(releases, "windows")
        self.assertEqual((win.version, win.url, win.sha256), ("2026.11.0", "https://dl.test/bw-windows-2026.11.0.zip", "bb"))
        self.assertEqual(bwcli.pick_release(releases, "macos-arm64").version, "2026.10.0")
        with self.assertRaises(bwcli.DownloadError):
            bwcli.pick_release(releases, "linux")
        releases[2]["assets"].append({"name": "bw-linux-sha256-2026.11.0.txt", "browser_download_url": "https://dl.test/sum"})
        with mock.patch.object(bwcli, "fetch", return_value=b"DD  bw-linux-2026.11.0.zip\n"):
            self.assertEqual(bwcli.pick_release(releases, "linux").sha256, "dd")

    def test_install_checks_the_hash(self):
        target = self.dir / "cache" / "bw"
        good = bwcli.Release("2026.11.0", "https://dl.test/bw.zip", self.digest[len("sha256:"):], 0)
        with mock.patch.object(bwcli, "fetch", return_value=self.archive):
            with self.assertRaises(bwcli.DownloadError):
                bwcli.install(bwcli.Release("2026.11.0", good.url, "00" * 32, 0), target)
            self.assertFalse(target.exists())
            bwcli.install(good, target)
        self.assertEqual(target.read_text(), "#!/bin/sh\necho 2026.11.0\n")
        self.assertTrue(os.access(target, os.X_OK) or os.name == "nt")
        self.assertEqual(bwcli.version_file(target).read_text(), "2026.11.0")

    def test_resolve(self):
        cached = self.dir / "bw"
        with mock.patch.object(bwcli, "cached_exe", return_value=cached), \
                mock.patch.object(bwcli.shutil, "which", return_value=None), \
                mock.patch.object(bwcli, "latest_release",
                                  return_value=bwcli.Release("2026.11.0", "u", self.digest[len("sha256:"):], 0)), \
                mock.patch.object(bwcli, "fetch", return_value=self.archive), \
                mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(bwcli.resolve("/opt/bw", False), "/opt/bw")
            self.assertIsNone(bwcli.resolve(None, False))
            with mock.patch("builtins.input", return_value="n"):
                self.assertIsNone(bwcli.resolve(None, True))
            with mock.patch("builtins.input", return_value="D"):
                self.assertEqual(bwcli.resolve(None, True), bwcli.DEMO)
            self.assertFalse(cached.exists())
            with mock.patch("builtins.input", return_value=""):
                self.assertEqual(bwcli.resolve(None, True), str(cached))
            with mock.patch("builtins.input", side_effect=AssertionError("asked again")):
                self.assertEqual(bwcli.resolve(None, False), str(cached))


class UnlockTest(unittest.TestCase):
    def test_choose_server(self):
        cases = {("",): None, ("1",): None, ("2",): "https://vault.bitwarden.eu",
                 ("3", "https://vault.example.com"): "https://vault.example.com", ("3", ""): None}
        for answers, expected in cases.items():
            bw = mock.Mock()
            with mock.patch("sys.stdout", io.StringIO()):
                unlock.choose_server(bw, mock.Mock(side_effect=list(answers)))
            calls = [mock.call("config", "server", expected)] if expected else []
            self.assertEqual(bw.run.call_args_list, calls, answers)


class DataFolderTest(unittest.TestCase):
    def test_double_clicked_executable_keeps_files_next_to_it(self):
        home = Path(tempfile.gettempdir()).resolve()
        exe = home / "tools" / "bw-dedupe"
        with mock.patch.object(Path, "home", return_value=home), mock.patch.object(Path, "cwd", return_value=home), \
                mock.patch.object(sys, "executable", str(exe)):
            self.assertEqual(bw_dedupe.data_folder(), Path())
            with mock.patch.object(sys, "frozen", True, create=True):
                self.assertEqual(bw_dedupe.data_folder(), exe.parent)
        with mock.patch.object(sys, "frozen", True, create=True):
            self.assertEqual(bw_dedupe.data_folder(), Path())


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
