#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["tldextract>=5.1"]
# ///
"""Merge duplicate Bitwarden login items through the official `bw` CLI.

Dry-run by default; pass --apply to modify the vault.
Secrets (passwords, TOTP keys, hidden field values, notes) are only compared in memory.
They are never printed, logged or written to the report. Payloads go to `bw` through stdin,
not through the command line.
"""

from __future__ import annotations

import argparse
import base64
import copy
import datetime as dt
import html
import json
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import tldextract

ITEM_TYPE_LOGIN = 1
URI_MATCH_DOMAIN = 0
WEB_SCHEMES = {"http", "https"}
NOTES_SEPARATOR = "\n\n----\n\n"
STATUS_PLANNED = "planned"
STATUS_OK = "ok"

# Bundled Public Suffix List snapshot only: no network access besides bw itself.
_extractor = tldextract.TLDExtract(suffix_list_urls=(), include_psl_private_domains=True, cache_dir=None)


def parse_web_uri(uri: str) -> tuple[str | None, str | None]:
    """Return (scheme, registrable domain) for a web URI, (None, None) otherwise."""
    raw = (uri or "").strip()
    if not raw:
        return None, None
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parts = urlsplit(raw)
        host = parts.hostname
    except ValueError:
        return None, None
    scheme = parts.scheme.lower()
    if scheme not in WEB_SCHEMES or not host:
        return None, None
    ext = _extractor(host)
    if hasattr(ext, "top_domain_under_public_suffix"):
        domain = ext.top_domain_under_public_suffix
    else:
        domain = ext.registered_domain
    return (scheme, domain.lower()) if domain else (None, None)


@dataclass
class Login:
    raw: dict
    domain: str | None = None
    domains: set[str] = field(default_factory=set)
    schemes: set[str] = field(default_factory=set)
    web_uris: list[str] = field(default_factory=list)
    other_uris: list[dict] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.raw["id"]

    @property
    def name(self) -> str:
        return self.raw.get("name") or ""

    @property
    def login(self) -> dict:
        return self.raw.get("login") or {}

    @property
    def username(self) -> str:
        return (self.login.get("username") or "").strip()

    @property
    def user_key(self) -> str:
        return self.username.casefold()

    @property
    def password(self) -> str:
        return self.login.get("password") or ""

    @property
    def totp(self) -> str:
        return (self.login.get("totp") or "").strip()

    @property
    def revision(self) -> str:
        return self.raw.get("revisionDate") or ""

    @property
    def has_passkey(self) -> bool:
        return bool(self.login.get("fido2Credentials"))

    @property
    def has_attachments(self) -> bool:
        return bool(self.raw.get("attachments"))


def parse_login(raw: dict) -> Login:
    item = Login(raw=raw)
    for uri in item.login.get("uris") or []:
        value = (uri or {}).get("uri") or ""
        scheme, domain = parse_web_uri(value)
        if domain:
            item.domains.add(domain)
            item.schemes.add(scheme)
            item.web_uris.append(value.strip())
        elif value.strip():
            item.other_uris.append(uri)
    if len(item.domains) == 1:
        item.domain = next(iter(item.domains))
    return item


@dataclass
class Merge:
    domain: str
    master: Login
    duplicates: list[Login]
    payload: dict
    changes: list[str]
    status: str = STATUS_PLANNED
    deleted_ids: list[str] = field(default_factory=list)


@dataclass
class Rename:
    item: Login
    new_name: str
    payload: dict
    status: str = STATUS_PLANNED


@dataclass
class Issue:
    domain: str
    username: str
    reason: str
    items: list[tuple[Login, str]]


@dataclass
class Plan:
    total_items: int = 0
    total_logins: int = 0
    merges: list[Merge] = field(default_factory=list)
    renames: list[Rename] = field(default_factory=list)
    conflicts: list[Issue] = field(default_factory=list)
    skipped: list[Issue] = field(default_factory=list)
    ignored: Counter = field(default_factory=Counter)

    @property
    def deletions(self) -> int:
        return sum(len(m.duplicates) for m in self.merges)


def letter(index: int) -> str:
    return chr(ord("A") + index) if index < 26 else f"#{index + 1}"


def merge_payload(master: Login, others: list[Login], domain: str, new_name: str) -> tuple[dict, list[str]]:
    group = [master, *others]
    payload = copy.deepcopy(master.raw)
    login = payload.setdefault("login", {})
    changes: list[str] = []

    if payload.get("name") != new_name:
        changes.append(f"name: \"{master.name}\" becomes \"{new_name}\"")
        payload["name"] = new_name

    all_schemes = set().union(*(g.schemes for g in group))
    scheme = "http" if all_schemes == {"http"} else "https"
    new_uris = [{"match": URI_MATCH_DOMAIN, "uri": f"{scheme}://{domain}"}]
    seen_other = set()
    for g in group:
        for uri in g.other_uris:
            key = uri.get("uri", "").strip()
            if key not in seen_other:
                seen_other.add(key)
                new_uris.append({"match": uri.get("match"), "uri": key})
    old_count = sum(len(g.web_uris) + len(g.other_uris) for g in group)
    changes.append(f"URIs: {old_count} in total replaced by {len(new_uris)} "
                   f"({scheme}://{domain} with \"base domain\" match detection)")
    login["uris"] = new_uris

    totp = next((g.totp for g in group if g.totp), "")
    if totp and not master.totp:
        login["totp"] = totp
        changes.append("TOTP key taken from a duplicate")

    notes = []
    for g in group:
        text = (g.raw.get("notes") or "").strip()
        if text and text not in notes:
            notes.append(text)
    if len(notes) > 1 or (notes and not (master.raw.get("notes") or "").strip()):
        payload["notes"] = NOTES_SEPARATOR.join(notes)
        changes.append(f"notes merged ({len(notes)} distinct notes)")

    fields = list(payload.get("fields") or [])
    field_keys = {(f.get("name"), f.get("value"), f.get("type")) for f in fields}
    added = []
    for g in others:
        for f in g.raw.get("fields") or []:
            key = (f.get("name"), f.get("value"), f.get("type"))
            if key not in field_keys:
                field_keys.add(key)
                fields.append(f)
                added.append(f.get("name") or "(unnamed)")
    if added:
        payload["fields"] = fields
        changes.append(f"{len(added)} custom field(s) added: {', '.join(added)}")

    if not payload.get("favorite") and any(g.raw.get("favorite") for g in others):
        payload["favorite"] = True
        changes.append("marked as favorite")

    if not payload.get("folderId"):
        folder = next((g.raw.get("folderId") for g in others if g.raw.get("folderId")), None)
        if folder:
            payload["folderId"] = folder
            changes.append("folder taken from a duplicate")

    reprompt = max(int(g.raw.get("reprompt") or 0) for g in group)
    if reprompt != int(payload.get("reprompt") or 0):
        payload["reprompt"] = reprompt
        changes.append("master password re-prompt enabled")

    return payload, changes


def build_plan(items: list[dict], rename_all: bool) -> Plan:
    plan = Plan(total_items=len(items))
    logins: list[Login] = []
    for raw in items:
        if raw.get("type") != ITEM_TYPE_LOGIN or raw.get("deletedDate"):
            continue
        if raw.get("organizationId"):
            plan.ignored["organization item"] += 1
            continue
        logins.append(parse_login(raw))
    plan.total_logins = len(logins)

    groups: dict[tuple[str, str], list[Login]] = defaultdict(list)
    for item in logins:
        if len(item.domains) > 1:
            plan.skipped.append(Issue(", ".join(sorted(item.domains)), item.username,
                                      "several domains in a single item", [(item, "")]))
        elif item.domain:
            groups[(item.domain, item.user_key)].append(item)
        else:
            plan.ignored["no usable web URI (app, IP, localhost, empty)"] += 1

    blocked_ids: set[str] = set()
    for (domain, _), members in sorted(groups.items()):
        if len(members) < 2:
            continue
        members.sort(key=lambda m: m.revision, reverse=True)
        username = members[0].username

        by_password: dict[str, list[Login]] = defaultdict(list)
        for m in members:
            by_password[m.password].append(m)
        if len(by_password) > 1:
            labels = {pwd: letter(i) for i, pwd in enumerate(by_password)}
            tagged = [(m, f"password {labels[m.password]}") for m in members]
            plan.conflicts.append(Issue(domain, username, f"{len(by_password)} different passwords", tagged))
            blocked_ids.update(m.id for m in members)
            continue

        totps = {m.totp for m in members if m.totp}
        if len(totps) > 1:
            labels = {t: letter(i) for i, t in enumerate(totps)}
            tagged = [(m, f"TOTP {labels[m.totp]}" if m.totp else "no TOTP") for m in members]
            plan.conflicts.append(Issue(domain, username, f"{len(totps)} different TOTP keys", tagged))
            blocked_ids.update(m.id for m in members)
            continue

        if any(m.has_passkey for m in members):
            plan.skipped.append(Issue(domain, username, "passkey present: merge manually",
                                      [(m, "passkey" if m.has_passkey else "") for m in members]))
            blocked_ids.update(m.id for m in members)
            continue

        with_files = [m for m in members if m.has_attachments]
        if len(with_files) > 1:
            plan.skipped.append(Issue(domain, username, "attachments on several items",
                                      [(m, "attachments" if m.has_attachments else "") for m in members]))
            blocked_ids.update(m.id for m in members)
            continue

        master = with_files[0] if with_files else members[0]
        dups = [m for m in members if m is not master]
        payload, changes = merge_payload(master, dups, domain, domain)
        plan.merges.append(Merge(domain, master, dups, payload, changes))

    if rename_all:
        deleted_ids = {d.id for m in plan.merges for d in m.duplicates}
        merged_ids = {m.master.id for m in plan.merges}
        for s in logins:
            if not s.domain or s.id in deleted_ids or s.id in merged_ids or s.id in blocked_ids:
                continue
            if s.name != s.domain:
                payload = copy.deepcopy(s.raw)
                payload["name"] = s.domain
                plan.renames.append(Rename(s, s.domain, payload))
    return plan


class BwError(RuntimeError):
    pass


class Bw:
    def __init__(self, exe: str):
        self.exe = exe

    def run(self, *args: str, stdin: str | None = None) -> str:
        proc = subprocess.run([self.exe, "--nointeraction", *args], input=stdin, capture_output=True,
                              text=True, encoding="utf-8")
        if proc.returncode != 0:
            # Only the command verb and bw's own error are reported, never the payload.
            raise BwError(f"bw {' '.join(args[:3])}: {proc.stderr.strip()[:300] or 'failed'}")
        return proc.stdout

    def status(self) -> str:
        return json.loads(self.run("status")).get("status", "unknown")

    def sync(self) -> None:
        self.run("sync")

    def list_items(self) -> list[dict]:
        return json.loads(self.run("list", "items"))

    def edit_item(self, item_id: str, payload: dict) -> None:
        encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
        self.run("edit", "item", item_id, stdin=encoded)

    def delete_item(self, item_id: str) -> None:
        self.run("delete", "item", item_id)

    def export_backup(self, path: Path) -> None:
        # Interactive on purpose: some bw versions ask for the master password here.
        proc = subprocess.run([self.exe, "export", "--format", "encrypted_json", "--output", str(path)])
        if proc.returncode != 0 or not path.exists():
            raise BwError("bw export: encrypted backup failed")


def apply_plan(bw: Bw, plan: Plan) -> None:
    total = len(plan.merges) + len(plan.renames)
    done = 0
    for merge in plan.merges:
        done += 1
        print(f"  [{done}/{total}] merge {merge.domain}", flush=True)
        try:
            bw.edit_item(merge.master.id, merge.payload)
        except BwError as err:
            merge.status = f"edit failed, nothing deleted ({err})"
            continue
        errors = []
        for dup in merge.duplicates:
            try:
                bw.delete_item(dup.id)
                merge.deleted_ids.append(dup.id)
            except BwError as err:
                errors.append(str(err))
        merge.status = STATUS_OK if not errors else f"partial: {'; '.join(errors)}"
    for rename in plan.renames:
        done += 1
        print(f"  [{done}/{total}] rename {rename.new_name}", flush=True)
        try:
            bw.edit_item(rename.item.id, rename.payload)
            rename.status = STATUS_OK
        except BwError as err:
            rename.status = f"failed ({err})"


def mask_username(value: str) -> str:
    if not value:
        return ""
    local, at, host = value.partition("@")
    return (local[:1] + "***" + at + host) if at else value[:1] + "***"


def render_report(plan: Plan, mode: str, started: dt.datetime, backup: Path | None, mask: bool) -> str:
    e = html.escape
    user = (lambda v: e(mask_username(v))) if mask else (lambda v: e(v))
    applied = mode == "apply"

    def status_cell(status: str) -> str:
        cls = "ok" if status == STATUS_OK else ("todo" if status == STATUS_PLANNED else "err")
        return f'<span class="st {cls}">{e(status)}</span>'

    edited = len(plan.merges) + len(plan.renames)
    deleted = sum(len(m.deleted_ids) for m in plan.merges) if applied else plan.deletions
    failures = [m for m in plan.merges if m.status not in (STATUS_OK, STATUS_PLANNED)] + \
               [r for r in plan.renames if r.status not in (STATUS_OK, STATUS_PLANNED)]
    after = plan.total_logins - deleted

    out = [f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>bw-dedupe report</title>
<style>
:root{{--bg:#fafafa;--fg:#1d1d1f;--muted:#6b6b70;--card:#fff;--line:#e3e3e6;--ok:#1f7a3a;--warn:#9a5b00;--err:#b42318;--accent:#175cd3}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151517;--fg:#ececee;--muted:#9a9aa0;--card:#1e1e21;--line:#2e2e33;--ok:#5cc27a;--warn:#e0a040;--err:#f07068;--accent:#7aa7ff}}}}
body{{background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,sans-serif;margin:0;padding:24px 16px}}
main{{max-width:1100px;margin:auto}} h1{{margin:0 0 4px}} h2{{margin:32px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}}
.muted{{color:var(--muted)}} .banner{{padding:10px 14px;border-radius:8px;margin:12px 0;border:1px solid var(--line);background:var(--card)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:16px 0}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px}}
.kpi b{{display:block;font-size:22px}} .kpi.del b{{color:var(--err)}} .kpi.mod b{{color:var(--accent)}} .kpi.warn b{{color:var(--warn)}}
details{{background:var(--card);border:1px solid var(--line);border-radius:8px;margin:6px 0;padding:8px 12px}}
summary{{cursor:pointer}} table{{border-collapse:collapse;width:100%;margin:6px 0}} td,th{{text-align:left;padding:4px 8px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}}
.keep{{color:var(--ok);font-weight:600}} .drop{{color:var(--err);font-weight:600}} code{{font-size:12px}}
.st{{font-size:12px;padding:1px 6px;border-radius:4px;border:1px solid currentColor}} .st.ok{{color:var(--ok)}} .st.todo{{color:var(--muted)}} .st.err{{color:var(--err)}}
pre{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px;overflow-x:auto}}
</style></head><body><main>
<h1>bw-dedupe report</h1>
<div class="muted">{e(started.strftime('%Y-%m-%d %H:%M:%S'))} · mode <b>{'APPLIED' if applied else 'PREVIEW (no changes made)'}</b></div>
<div class="banner">This report contains no password, TOTP key, custom field value or note content.
{'Encrypted backup: <code>' + e(str(backup)) + '</code>.' if backup else ''}
Deleted items stay in the Bitwarden trash for 30 days.</div>
<h2>Vault impact</h2>
<div class="grid">
<div class="kpi"><span class="muted">Logins before</span><b>{plan.total_logins}</b></div>
<div class="kpi"><span class="muted">Logins after</span><b>{after}</b></div>
<div class="kpi del"><span class="muted">{'Deleted' if applied else 'To delete'} (trash)</span><b>{deleted}</b></div>
<div class="kpi mod"><span class="muted">{'Modified' if applied else 'To modify'}</span><b>{edited}</b></div>
<div class="kpi warn"><span class="muted">Conflicts to review</span><b>{len(plan.conflicts)}</b></div>
<div class="kpi warn"><span class="muted">Skipped (manual merge)</span><b>{len(plan.skipped)}</b></div>
{f'<div class="kpi del"><span class="muted">Failures</span><b>{len(failures)}</b></div>' if applied else ''}
</div>"""]
    if plan.ignored:
        out.append("<p class='muted'>Not processed: " +
                   ", ".join(f"{e(k)}: {v}" for k, v in plan.ignored.items()) + "</p>")

    out.append(f"<h2>Merges ({len(plan.merges)})</h2>")
    for m in plan.merges:
        rows = [f"<tr><td class='keep'>kept</td><td>{e(m.master.name)}</td><td>{user(m.master.username)}</td>"
                f"<td>{e(m.master.revision[:19])}</td><td>{'<br>'.join(e(u) for u in m.master.web_uris)}</td>"
                f"<td><code>{e(m.master.id)}</code></td></tr>"]
        for d in m.duplicates:
            rows.append(f"<tr><td class='drop'>deleted</td><td>{e(d.name)}</td><td>{user(d.username)}</td>"
                        f"<td>{e(d.revision[:19])}</td><td>{'<br>'.join(e(u) for u in d.web_uris)}</td>"
                        f"<td><code>{e(d.id)}</code></td></tr>")
        out.append(f"""<details><summary><b>{e(m.payload['name'])}</b> · {len(m.duplicates) + 1} items
merged into 1 · {status_cell(m.status)}</summary>
<table><tr><th></th><th>Name</th><th>Username</th><th>Modified</th><th>URIs</th><th>ID</th></tr>{''.join(rows)}</table>
<div>Changes to the kept item:<ul>{''.join(f'<li>{e(c)}</li>' for c in m.changes)}</ul></div></details>""")

    if plan.renames:
        out.append(f"<h2>Renames only ({len(plan.renames)})</h2><table><tr><th>Before</th><th>After</th><th>Status</th></tr>")
        for r in plan.renames:
            out.append(f"<tr><td>{e(r.item.name)}</td><td>{e(r.new_name)}</td><td>{status_cell(r.status)}</td></tr>")
        out.append("</table>")

    for title, issues, hint in (
        ("Conflicts: unchanged, review manually", plan.conflicts,
         "Same domain and username, but different secrets. Letters show which items share the same secret "
         "without revealing it. Most recent first."),
        ("Skipped: unchanged", plan.skipped, "")):
        out.append(f"<h2>{e(title)} ({len(issues)})</h2>")
        if hint and issues:
            out.append(f"<p class='muted'>{e(hint)}</p>")
        for issue in issues:
            rows = "".join(
                f"<tr><td>{e(tag)}</td><td>{e(i.name)}</td><td>{user(i.username)}</td><td>{e(i.revision[:19])}</td>"
                f"<td>{'<br>'.join(e(u) for u in i.web_uris)}</td><td><code>{e(i.id)}</code></td></tr>"
                for i, tag in issue.items)
            out.append(f"<details><summary><b>{e(issue.domain)}</b> · {user(issue.username) or '(no username)'} · "
                       f"{e(issue.reason)}</summary><table><tr><th></th><th>Name</th><th>Username</th>"
                       f"<th>Modified</th><th>URIs</th><th>ID</th></tr>{rows}</table></details>")

    restored = [i for m in plan.merges for i in m.deleted_ids]
    if restored:
        out.append("<h2>Undo deletions</h2><p class='muted'>Restores the duplicates from the trash "
                   "(kept items keep their changes; the encrypted backup allows a full rollback).</p><pre>")
        out.append("\n".join(f"bw restore item {e(i)}" for i in restored))
        out.append("</pre>")
    out.append("</main></body></html>")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge duplicate Bitwarden logins (same registrable domain, username and password).")
    parser.add_argument("--apply", action="store_true", help="apply the changes after preview and confirmation")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt with --apply")
    parser.add_argument("--no-backup", action="store_true", help="skip the encrypted export before --apply")
    parser.add_argument("--rename-all", action="store_true", help="also rename non-duplicated logins after their domain")
    parser.add_argument("--mask-usernames", action="store_true", help="mask usernames in the report")
    parser.add_argument("--report", type=Path, help="path of the HTML report")
    parser.add_argument("--bw", default=shutil.which("bw"), help="path of the bw executable")
    args = parser.parse_args()

    if not args.bw:
        print("bw not found in PATH. Install the Bitwarden CLI or pass --bw.", file=sys.stderr)
        return 2
    bw = Bw(args.bw)
    started = dt.datetime.now()
    stamp = started.strftime("%Y%m%d-%H%M%S")
    report_path = args.report or Path(f"bw-dedupe-report-{stamp}.html")

    try:
        status = bw.status()
        if status != "unlocked":
            print(f"Vault is {status}. Run `bw login`, then `bw unlock` and export BW_SESSION.", file=sys.stderr)
            return 2
        bw.sync()
        plan = build_plan(bw.list_items(), args.rename_all)
    except BwError as err:
        print(err, file=sys.stderr)
        return 1

    print(f"Logins: {plan.total_logins} · merges: {len(plan.merges)} · deletions: {plan.deletions} · "
          f"renames only: {len(plan.renames)} · conflicts: {len(plan.conflicts)} · skipped: {len(plan.skipped)}")

    mode = "dry-run"
    backup = None
    if args.apply and (plan.merges or plan.renames):
        preview_path = report_path.with_name(report_path.stem + "-preview.html")
        preview_path.write_text(render_report(plan, mode, started, None, args.mask_usernames), encoding="utf-8")
        print(f"Preview of the changes: {preview_path.resolve()}")
        if not args.yes and input("Review the preview, then type \"yes\" to apply this plan: ").strip().lower() != "yes":
            print("Cancelled, nothing changed.")
            return 0
        mode = "apply"
        try:
            if not args.no_backup:
                backup = Path(f"bw-backup-{stamp}.json")
                print(f"Encrypted backup to {backup}")
                bw.export_backup(backup)
            apply_plan(bw, plan)
        except BwError as err:
            print(err, file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("\nInterrupted: the report lists what was done.", file=sys.stderr)
        finally:
            report_path.write_text(render_report(plan, mode, started, backup, args.mask_usernames), encoding="utf-8")
            print(f"Report: {report_path.resolve()}")
        return 0

    report_path.write_text(render_report(plan, mode, started, backup, args.mask_usernames), encoding="utf-8")
    print(f"Report: {report_path.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
