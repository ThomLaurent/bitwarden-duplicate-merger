"""Access to the vault through the official `bw` CLI, and parsing of login items."""

from __future__ import annotations

import base64
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import tldextract

ITEM_TYPE_LOGIN = 1
URI_MATCH_DOMAIN = 0
WEB_SCHEMES = {"http", "https"}

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
    domain = getattr(ext, "top_domain_under_public_suffix", None)
    if domain is None:
        domain = ext.registered_domain
    return (scheme, domain.lower()) if domain else (None, None)


@dataclass
class Login:
    raw: dict
    domain: str | None = None
    domains: set[str] = field(default_factory=set)
    uris: list[dict] = field(default_factory=list)

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
    def notes(self) -> str:
        return (self.raw.get("notes") or "").strip()

    @property
    def revision(self) -> str:
        return self.raw.get("revisionDate") or ""

    @property
    def passkeys(self) -> int:
        return len(self.login.get("fido2Credentials") or [])

    @property
    def attachments(self) -> int:
        return len(self.raw.get("attachments") or [])

    def summary(self, folders: dict[str, str]) -> dict:
        """Non-secret description of the item, safe to send to the UI and to write to disk."""
        return {
            "id": self.id,
            "name": self.name,
            "username": self.username,
            "domain": self.domain,
            "domains": sorted(self.domains),
            "uris": self.uris,
            "revision": self.revision,
            "folder": folders.get(self.raw.get("folderId") or "", ""),
            "favorite": bool(self.raw.get("favorite")),
            "reprompt": bool(self.raw.get("reprompt")),
            "hasPassword": bool(self.password),
            "hasTotp": bool(self.totp),
            "notesLength": len(self.notes),
            "fields": [f.get("name") or "(unnamed)" for f in self.raw.get("fields") or []],
            "attachments": self.attachments,
            "passkeys": self.passkeys,
        }


def parse_login(raw: dict) -> Login:
    item = Login(raw=raw)
    for uri in item.login.get("uris") or []:
        value = ((uri or {}).get("uri") or "").strip()
        if not value:
            continue
        scheme, domain = parse_web_uri(value)
        if domain:
            item.domains.add(domain)
        item.uris.append({"uri": value, "match": uri.get("match"), "scheme": scheme, "domain": domain})
    if len(item.domains) == 1:
        item.domain = next(iter(item.domains))
    return item


def personal_logins(items: list[dict]) -> dict[str, Login]:
    return {
        raw["id"]: parse_login(raw)
        for raw in items
        if raw.get("type") == ITEM_TYPE_LOGIN and not raw.get("deletedDate") and not raw.get("organizationId")
    }


class BwError(RuntimeError):
    pass


class Bw:
    def __init__(self, exe: str, session: str | None = None):
        self.exe = exe
        self.session = session

    def env(self) -> dict[str, str]:
        # The session key goes through the environment, never the command line.
        env = dict(os.environ)
        if self.session:
            env["BW_SESSION"] = self.session
        return env

    def run(self, *args: str, stdin: str | None = None) -> str:
        proc = subprocess.run([self.exe, "--nointeraction", *args], input=stdin, capture_output=True,
                              text=True, encoding="utf-8", env=self.env())
        if proc.returncode != 0:
            # Only the command verb and bw's own error are reported, never the payload.
            raise BwError(f"bw {' '.join(args[:3])}: {proc.stderr.strip()[:300] or 'failed'}")
        return proc.stdout

    def status(self) -> dict:
        return json.loads(self.run("status"))

    def lock(self) -> None:
        self.run("lock")

    def sync(self) -> None:
        self.run("sync")

    def list_items(self) -> list[dict]:
        return json.loads(self.run("list", "items"))

    def list_folders(self) -> dict[str, str]:
        return {f["id"]: f.get("name") or "" for f in json.loads(self.run("list", "folders")) if f.get("id")}

    def edit_item(self, item_id: str, payload: dict) -> dict | None:
        encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
        out = self.run("edit", "item", item_id, stdin=encoded)
        try:
            return json.loads(out)
        except ValueError:
            return None

    def delete_item(self, item_id: str) -> None:
        self.run("delete", "item", item_id)

    def export_backup(self, path: Path) -> None:
        # Attached to the terminal on purpose: some bw versions ask for the master password here.
        proc = subprocess.run([self.exe, "export", "--format", "encrypted_json", "--output", str(path)],
                              env=self.env())
        if proc.returncode != 0 or not path.exists():
            raise BwError("bw export: encrypted backup failed")
