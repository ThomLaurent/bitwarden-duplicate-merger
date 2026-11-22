"""Work session: decisions saved to the work file, reconciliation with the vault, and apply runs.

The work file and the reports only hold non-secret data: item ids, names, usernames, URIs,
revision dates and decisions. Secrets are read from the vault in memory when a change is applied.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import os
import threading
import time
from pathlib import Path

from . import report
from .rules import (ACTION_IGNORE, ACTION_MERGE, KIND_MANUAL, KIND_RENAME, build_payload,
                    describe_differences, make_group, secret_labels, suggest_groups, validate)
from .vault import Bw, BwError, Login, parse_login, personal_logins

WORKFILE_VERSION = 1
RESYNC_SECONDS = 30
OPEN_STATUSES = ("todo", "validated", "stale", "failed")


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


class SessionError(RuntimeError):
    pass


class Session:
    def __init__(self, bw: Bw, workfile: Path, reports_dir: Path):
        self.bw = bw
        self.workfile = workfile
        self.reports_dir = reports_dir
        self.lock = threading.RLock()
        self.items: dict[str, Login] = {}
        self.folders: dict[str, str] = {}
        self.unlocked = False
        self.data: dict = {}
        self.progress: dict = {"running": False}
        self.last_sync = 0.0

    # Work file

    def load_workfile(self, user_id: str) -> None:
        if self.workfile.exists():
            data = json.loads(self.workfile.read_text(encoding="utf-8"))
            if data.get("userId") not in (None, user_id):
                raise SessionError(f"{self.workfile} belongs to another Bitwarden account: "
                                   "move it away or pass --workfile")
            self.data = data
        else:
            self.data = {"version": WORKFILE_VERSION, "userId": user_id, "created": now(),
                         "groups": [], "released": [], "runs": []}

    def save(self) -> None:
        self.data["updated"] = now()
        tmp = self.workfile.with_name(self.workfile.name + ".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.workfile)

    @property
    def groups(self) -> list[dict]:
        return self.data["groups"]

    def group(self, group_id: str) -> dict:
        for g in self.groups:
            if g["id"] == group_id:
                return g
        raise SessionError("unknown group")

    # Vault

    def open(self) -> None:
        with self.lock:
            status = self.bw.status()
            if status.get("status") != "unlocked":
                self.unlocked = False
                return
            self.load_workfile(status.get("userId") or "")
            self.refresh_items()
            self.unlocked = True
            self.reconcile()
            self.save()

    def refresh_items(self) -> None:
        self.bw.sync()
        self.items = personal_logins(self.bw.list_items())
        self.folders = self.bw.list_folders()
        self.last_sync = time.monotonic()

    def reconcile(self) -> None:
        """Flag decisions on items changed since, and suggest groups for new items."""
        kept = []
        for g in self.groups:
            if g["status"] not in OPEN_STATUSES:
                kept.append(g)
                continue
            gone = [i for i in g["items"] if i not in self.items]
            changed = [i for i in g["items"] if i in self.items and self.items[i].revision != g["revisions"].get(i)]
            if gone:
                self.drop_items(g, gone)
            if not g["items"] or (len(g["items"]) < 2 and g["kind"] != KIND_RENAME):
                continue
            if gone or changed:
                g["status"] = "stale"
                g["note"] = f"{len(gone) + len(changed)} item(s) changed in the vault since your last review"
                g["revisions"] = {i: self.items[i].revision for i in g["items"]}
            kept.append(g)
        self.data["groups"] = kept
        claimed = {i for g in kept if g["status"] in OPEN_STATUSES for i in g["items"]}
        claimed.update(self.data["released"])
        free = [item for item_id, item in self.items.items() if item_id not in claimed]
        self.groups.extend(suggest_groups(free))

    @staticmethod
    def drop_items(g: dict, ids: list[str]) -> None:
        g["items"] = [i for i in g["items"] if i not in ids]
        for decision in (g["decision"], g["suggestion"]):
            decision["include"] = [i for i in decision["include"] if i not in ids]
            decision["notesFrom"] = [i for i in decision["notesFrom"] if i not in ids]
            fallback = decision["include"][0] if decision["include"] else (g["items"][0] if g["items"] else None)
            for key in ("keep", "usernameFrom", "passwordFrom"):
                if decision.get(key) in ids:
                    decision[key] = fallback
            if decision.get("totpFrom") in ids:
                decision["totpFrom"] = None
            if not decision["include"] and fallback:
                decision["include"] = [fallback]
        for i in ids:
            g["revisions"].pop(i, None)

    # UI state

    def item_view(self, item_id: str) -> dict:
        item = self.items.get(item_id)
        return item.summary(self.folders) if item else {"id": item_id, "missing": True}

    def group_view(self, g: dict) -> dict:
        view = copy.deepcopy(g)
        present = {i: self.items[i] for i in g["items"] if i in self.items}
        view["passwordLabels"] = secret_labels({i: m.password for i, m in present.items()})
        view["totpLabels"] = secret_labels({i: m.totp for i, m in present.items()})
        view["notesLabels"] = secret_labels({i: m.notes for i, m in present.items()})
        return view

    def state(self) -> dict:
        with self.lock:
            if not self.unlocked:
                return {"unlocked": False, "progress": self.progress}
            in_group = {}
            for g in self.groups:
                if g["status"] in OPEN_STATUSES:
                    for i in g["items"]:
                        in_group[i] = g["id"]
            items = {}
            for item_id, item in self.items.items():
                view = item.summary(self.folders)
                view["groupId"] = in_group.get(item_id)
                view["released"] = item_id in self.data["released"]
                items[item_id] = view
            return {
                "unlocked": True,
                "workfile": str(self.workfile.resolve()),
                "items": items,
                "groups": [self.group_view(g) for g in self.groups],
                "runs": [{k: r[k] for k in ("id", "started", "finished", "counts", "report", "backup")}
                         for r in reversed(self.data["runs"])],
                "progress": self.progress,
            }

    def secret(self, item_id: str, kind: str) -> str:
        with self.lock:
            item = self.items.get(item_id)
            if not item:
                raise SessionError("unknown item")
            if kind == "password":
                return item.password
            if kind == "totp":
                return item.totp
            if kind == "notes":
                return item.notes
            raise SessionError("unknown secret")

    # Edits from the UI

    def ensure_idle(self) -> None:
        if self.progress.get("running"):
            raise SessionError("changes are being applied")

    def update_group(self, group_id: str, decision: dict, status: str) -> None:
        with self.lock:
            self.ensure_idle()
            g = self.group(group_id)
            if g["status"] not in OPEN_STATUSES:
                raise SessionError("this group was already applied")
            if status not in ("todo", "validated"):
                raise SessionError("invalid status")
            if status == "validated":
                error = validate(decision, g)
                if error:
                    raise SessionError(error)
            g["decision"] = decision
            g["status"] = status
            g["note"] = ""
            self.save()

    def reset_group(self, group_id: str) -> None:
        with self.lock:
            self.ensure_idle()
            g = self.group(group_id)
            g["decision"] = copy.deepcopy(g["suggestion"])
            if g["kind"] == KIND_MANUAL:
                g["decision"]["action"] = ACTION_MERGE
            g["status"] = "todo"
            g["note"] = ""
            self.save()

    def release(self, item_ids: list[str]) -> None:
        """Take items out of their open groups; they will not be grouped automatically again."""
        for g in list(self.groups):
            if g["status"] not in OPEN_STATUSES:
                continue
            ids = [i for i in item_ids if i in g["items"]]
            if not ids:
                continue
            self.drop_items(g, ids)
            if not g["items"] or (len(g["items"]) < 2 and g["kind"] != KIND_RENAME):
                self.groups.remove(g)
                self.data["released"].extend(i for i in g["items"] if i not in self.data["released"])
            elif g["status"] == "validated":
                g["status"] = "todo"
        self.data["released"].extend(i for i in item_ids if i not in self.data["released"])

    def remove_item(self, group_id: str, item_id: str) -> None:
        with self.lock:
            self.ensure_idle()
            g = self.group(group_id)
            if item_id not in g["items"]:
                raise SessionError("item not in this group")
            self.release([item_id])
            self.save()

    def create_group(self, item_ids: list[str]) -> str:
        with self.lock:
            self.ensure_idle()
            items = [self.items[i] for i in dict.fromkeys(item_ids) if i in self.items]
            if len(items) < 2:
                raise SessionError("select at least two logins")
            self.release([i.id for i in items])
            self.data["released"] = [i for i in self.data["released"] if i not in {x.id for x in items}]
            g = make_group(KIND_MANUAL, items)
            g["decision"]["action"] = ACTION_MERGE
            self.groups.append(g)
            self.save()
            return g["id"]

    def rename(self, item_ids: list[str]) -> int:
        with self.lock:
            self.ensure_idle()
            claimed = {i for g in self.groups if g["status"] in OPEN_STATUSES for i in g["items"]}
            count = 0
            for item_id in item_ids:
                item = self.items.get(item_id)
                if not item or not item.domain or item_id in claimed or item.name == item.domain:
                    continue
                g = make_group(KIND_RENAME, [item], domain=item.domain)
                for decision in (g["decision"], g["suggestion"]):
                    decision["uris"] = [{"uri": u["uri"], "match": u["match"]} for u in item.uris]
                g["suggestion"]["name"] = item.name
                g["decision"]["action"] = ACTION_MERGE
                g["status"] = "validated"
                self.groups.append(g)
                count += 1
            self.save()
            return count

    # Apply

    def start_apply(self, group_ids: list[str], backup: bool) -> None:
        with self.lock:
            self.ensure_idle()
            todo = [g["id"] for g in self.groups if g["id"] in set(group_ids) and g["status"] == "validated"]
            if not todo:
                raise SessionError("no validated group selected")
            self.progress = {"running": True, "done": 0, "total": len(todo), "phase": "starting", "runId": None}
        threading.Thread(target=self.apply, args=(todo, backup), daemon=True).start()

    def apply(self, group_ids: list[str], backup: bool) -> None:
        started = dt.datetime.now()
        stamp = started.strftime("%Y%m%d-%H%M%S")
        run = {"id": "run-" + stamp, "started": now(), "finished": None, "backup": None,
               "results": [], "report": None, "counts": {}}
        try:
            self.reports_dir.mkdir(parents=True, exist_ok=True)
            if backup:
                self.progress["phase"] = "backup (check the terminal if bw asks for your master password)"
                path = self.reports_dir / f"bw-backup-{stamp}.json"
                self.bw.export_backup(path)
                run["backup"] = str(path.resolve())
            with self.lock:
                self.progress["phase"] = "syncing"
                self.refresh_items()
                run["counts"]["loginsBefore"] = len(self.items)
            for done, group_id in enumerate(group_ids):
                with self.lock:
                    g = self.group(group_id)
                    self.progress.update(phase=f"{g['domain'] or g['decision']['name']}", done=done)
                    if time.monotonic() - self.last_sync > RESYNC_SECONDS:
                        self.refresh_items()
                    run["results"].append(self.apply_group(g, run["id"]))
                    self.save()
        except BwError as err:
            self.progress["error"] = run["error"] = str(err)
        except Exception as err:  # noqa: BLE001 - the run record must still be written
            self.progress["error"] = run["error"] = f"unexpected error: {type(err).__name__}"
        finally:
            with self.lock:
                run["finished"] = now()
                outcomes = [r["outcome"] for r in run["results"]]
                run["counts"].update({
                    "loginsAfter": len(self.items),
                    "groups": len(run["results"]),
                    "edited": sum(1 for r in run["results"] if r["edited"]),
                    "trashed": sum(len(r["trashed"]) for r in run["results"]),
                    "byYou": sum(1 for r in run["results"] if r["differences"]),
                    "stale": outcomes.count("stale"),
                    "failed": outcomes.count("failed") + outcomes.count("partial"),
                })
                if run["results"] or run["backup"]:
                    path = self.reports_dir / f"bw-dedupe-report-{stamp}.html"
                    path.write_text(report.render(run), encoding="utf-8")
                    run["report"] = str(path.resolve())
                    self.data["runs"].append(run)
                    self.save()
                self.progress.update(running=False, done=len(run["results"]), phase="finished",
                                     runId=run["id"] if run["report"] else None)

    def apply_group(self, g: dict, run_id: str) -> dict:
        d = g["decision"]
        g["runId"] = run_id
        names = {i: (self.items[i].name if i in self.items else i) for i in g["items"]}
        result = {"groupId": g["id"], "domain": g["domain"], "kind": g["kind"], "reason": g["reason"],
                  "outcome": "", "message": "", "differences": describe_differences(g, names),
                  "before": [], "after": None, "trashed": [], "edited": False}
        for i in g["items"]:
            item = self.items.get(i)
            role = "untouched"
            if d["action"] == ACTION_MERGE and i in d["include"]:
                role = "kept" if i == d["keep"] else "trashed"
            result["before"].append({"id": i, "name": names[i], "username": item.username if item else "",
                                     "uris": [u["uri"] for u in item.uris] if item else [], "role": role})

        changed = [i for i in g["items"] if i not in self.items or self.items[i].revision != g["revisions"].get(i)]
        if changed:
            g["status"] = "stale"
            g["note"] = "not applied: item(s) changed in the vault after your review"
            g["revisions"] = {i: self.items[i].revision for i in g["items"] if i in self.items}
            result.update(outcome="stale", message=g["note"])
            return result

        if d["action"] == ACTION_IGNORE:
            g["status"] = "applied"
            self.data["released"].extend(i for i in g["items"] if i not in self.data["released"])
            result.update(outcome="untouched", message="left untouched")
            return result

        keep = self.items[d["keep"]]
        payload = build_payload(d, self.items)
        result["after"] = {"name": payload["name"], "username": self.items[d["usernameFrom"]].username,
                           "uris": [u["uri"] for u in payload["login"]["uris"]]}
        try:
            edited = self.bw.edit_item(keep.id, payload)
        except BwError as err:
            g["status"] = "failed"
            g["note"] = f"edit failed, nothing deleted: {err}"
            result.update(outcome="failed", message=g["note"])
            return result
        result["edited"] = True
        if edited and keep.passkeys and len((edited.get("login") or {}).get("fido2Credentials") or []) < keep.passkeys:
            g["status"] = "failed"
            g["note"] = "passkey lost by bw edit: restore it from the backup; nothing deleted"
            result.update(outcome="failed", message=g["note"])
            return result
        if edited and edited.get("id") == keep.id:
            self.items[keep.id] = parse_login(edited)
            g["revisions"][keep.id] = self.items[keep.id].revision
        errors = []
        for i in d["include"]:
            if i == keep.id:
                continue
            try:
                self.bw.delete_item(i)
                result["trashed"].append(i)
                self.items.pop(i, None)
            except BwError as err:
                errors.append(str(err))
        excluded = [i for i in g["items"] if i not in d["include"]]
        self.data["released"].extend(i for i in excluded if i not in self.data["released"])
        g["status"] = "failed" if errors else "applied"
        g["note"] = "; ".join(errors)
        result.update(outcome="partial" if errors else "applied", message=g["note"])
        return result

    def run(self, run_id: str) -> dict:
        for r in self.data["runs"]:
            if r["id"] == run_id:
                return r
        raise SessionError("unknown run")
