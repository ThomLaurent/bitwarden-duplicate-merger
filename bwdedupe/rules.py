"""Duplicate detection rule, merge decisions and the payload sent to `bw edit`."""

from __future__ import annotations

import copy
import secrets
from collections import Counter, defaultdict

from .vault import URI_MATCH_DOMAIN, Login

NOTES_SEPARATOR = "\n\n----\n\n"

KIND_RULE = "rule"          # the rule knows how to merge it
KIND_CONFLICT = "conflict"  # same domain and username, but different secrets
KIND_SKIPPED = "skipped"    # the rule refuses to merge it automatically
KIND_MANUAL = "manual"      # group created by the user
KIND_RENAME = "rename"      # single item renamed after its domain at the user's request

ACTION_MERGE = "merge"
ACTION_IGNORE = "ignore"


def new_group_id() -> str:
    return "g-" + secrets.token_hex(6)


def letter(index: int) -> str:
    return chr(ord("A") + index) if index < 26 else f"#{index + 1}"


def secret_labels(values: dict[str, str]) -> dict[str, str]:
    """Map item id to a letter shared by items holding the same secret, without exposing it."""
    order: dict[str, str] = {}
    labels = {}
    for item_id, value in values.items():
        if not value:
            labels[item_id] = ""
            continue
        if value not in order:
            order[value] = letter(len(order))
        labels[item_id] = order[value]
    return labels


def main_domain(items: list[Login]) -> str:
    counts = Counter(d for i in items for d in i.domains)
    return counts.most_common(1)[0][0] if counts else ""


def rule_uris(items: list[Login], domain: str) -> list[dict]:
    """One base-domain URI per domain (the main one first), plus the non-web URIs (apps, IPs...)."""
    schemes = {u["scheme"] for i in items for u in i.uris if u["domain"]}
    scheme = "http" if schemes == {"http"} else "https"
    domains = [domain] if domain else []
    domains += sorted({u["domain"] for i in items for u in i.uris if u["domain"]} - {domain})
    uris = [{"uri": f"{scheme}://{d}", "match": URI_MATCH_DOMAIN} for d in domains]
    seen = set()
    for i in items:
        for u in i.uris:
            if not u["domain"] and u["uri"] not in seen:
                seen.add(u["uri"])
                uris.append({"uri": u["uri"], "match": u["match"]})
    return uris


def default_decision(items: list[Login], domain: str, action: str | None) -> dict:
    """Prefilled decision: keep the item with attachments or the most recent one."""
    ordered = sorted(items, key=lambda i: i.revision, reverse=True)
    with_files = [i for i in ordered if i.attachments]
    keep = with_files[0] if with_files else ordered[0]
    totp_from = keep if keep.totp else next((i for i in ordered if i.totp), None)
    notes_from = []
    seen_notes = set()
    for i in [keep, *[o for o in ordered if o is not keep]]:
        if i.notes and i.notes not in seen_notes:
            seen_notes.add(i.notes)
            notes_from.append(i.id)
    return {
        "action": action,
        "keep": keep.id,
        "include": [i.id for i in ordered],
        "name": domain or keep.name,
        "uris": rule_uris(ordered, domain),
        "usernameFrom": keep.id,
        "passwordFrom": keep.id,
        "totpFrom": totp_from.id if totp_from else None,
        "notesFrom": notes_from,
    }


def make_group(kind: str, items: list[Login], reason: str = "", action: str | None = None,
               domain: str | None = None) -> dict:
    domain = domain if domain is not None else main_domain(items)
    decision = default_decision(items, domain, action)
    return {
        "id": new_group_id(),
        "kind": kind,
        "domain": domain,
        "reason": reason,
        "items": decision["include"][:],
        "revisions": {i.id: i.revision for i in items},
        "suggestion": copy.deepcopy(decision),
        "decision": decision,
        "status": "todo",
        "note": "",
    }


def classify(members: list[Login]) -> tuple[str, str]:
    passwords = {m.password for m in members}
    if len(passwords) > 1:
        return KIND_CONFLICT, f"{len(passwords)} different passwords"
    totps = {m.totp for m in members if m.totp}
    if len(totps) > 1:
        return KIND_CONFLICT, f"{len(totps)} different TOTP keys"
    if any(m.passkeys for m in members):
        return KIND_SKIPPED, "passkey present"
    if sum(1 for m in members if m.attachments) > 1:
        return KIND_SKIPPED, "attachments on several items"
    return KIND_RULE, ""


def suggest_groups(logins: list[Login]) -> list[dict]:
    """Apply the rule: same registrable domain, same username (case-insensitive), same secrets."""
    buckets: dict[tuple[str, str], list[Login]] = defaultdict(list)
    for item in logins:
        if item.domain:
            buckets[(item.domain, item.user_key)].append(item)
    groups = []
    for (domain, _), members in sorted(buckets.items()):
        if len(members) < 2:
            continue
        kind, reason = classify(members)
        groups.append(make_group(kind, members, reason, ACTION_MERGE if kind == KIND_RULE else None, domain))
    return groups


def build_payload(decision: dict, items: dict[str, Login]) -> dict:
    """Full item sent to `bw edit`, built in memory from fresh vault data."""
    keep = items[decision["keep"]]
    members = [items[i] for i in decision["include"]]
    payload = copy.deepcopy(keep.raw)
    login = payload.setdefault("login", {})
    payload["name"] = decision["name"]
    login["uris"] = [{"uri": u["uri"], "match": u.get("match")} for u in decision["uris"]]
    login["username"] = items[decision["usernameFrom"]].login.get("username")
    login["password"] = items[decision["passwordFrom"]].login.get("password")
    totp_from = decision.get("totpFrom")
    login["totp"] = items[totp_from].login.get("totp") if totp_from else None

    notes = []
    for item_id in decision["notesFrom"]:
        text = items[item_id].notes
        if text and text not in notes:
            notes.append(text)
    payload["notes"] = NOTES_SEPARATOR.join(notes) or None

    fields = list(payload.get("fields") or [])
    keys = {(f.get("name"), f.get("value"), f.get("type")) for f in fields}
    for m in members:
        for f in m.raw.get("fields") or []:
            key = (f.get("name"), f.get("value"), f.get("type"))
            if key not in keys:
                keys.add(key)
                fields.append(f)
    payload["fields"] = fields or None

    payload["favorite"] = any(m.raw.get("favorite") for m in members)
    if not payload.get("folderId"):
        payload["folderId"] = next((m.raw.get("folderId") for m in members if m.raw.get("folderId")), None)
    payload["reprompt"] = max(int(m.raw.get("reprompt") or 0) for m in members)
    return payload


def validate(decision: dict, group: dict) -> str | None:
    """Return an error message if the decision cannot be applied."""
    if decision.get("action") not in (ACTION_MERGE, ACTION_IGNORE):
        return "choose to merge or to leave untouched"
    if decision["action"] == ACTION_IGNORE:
        return None
    include = set(decision.get("include") or [])
    if not include <= set(group["items"]):
        return "unknown item in the group"
    if decision.get("keep") not in include:
        return "the kept item must be part of the merge"
    for key in ("usernameFrom", "passwordFrom"):
        if decision.get(key) not in include:
            return "username and password must come from an item of the merge"
    if decision.get("totpFrom") and decision["totpFrom"] not in include:
        return "the TOTP key must come from an item of the merge"
    if not set(decision.get("notesFrom") or []) <= include:
        return "notes must come from items of the merge"
    if not (decision.get("name") or "").strip():
        return "the name cannot be empty"
    for u in decision.get("uris") or []:
        if not (u.get("uri") or "").strip():
            return "empty URI"
    return None


def describe_differences(group: dict, names: dict[str, str]) -> list[str]:
    """What the user decided differently from the rule, in plain words."""
    s, d = group["suggestion"], group["decision"]

    def label(item_id: str | None) -> str:
        return f'"{names.get(item_id, item_id)}"' if item_id else "none"

    out = []
    if group["kind"] == KIND_MANUAL:
        out.append("group created by you")
    elif group["kind"] == KIND_RENAME:
        out.append("rename requested by you")
    elif s["action"] is None:
        out.append(f"the rule did not decide ({group['reason']})")
    if d["action"] == ACTION_IGNORE:
        if s["action"] != ACTION_IGNORE:
            out.append("left untouched by you")
        return out
    if s["action"] == ACTION_IGNORE:
        out.append("merged by you")
    undecided = s["action"] is None or group["kind"] in (KIND_MANUAL, KIND_RENAME)
    if (d["keep"] != s["keep"] or undecided) and len(group["items"]) > 1:
        out.append(f"kept item: {label(d['keep'])}")
    excluded = [i for i in group["items"] if i not in d["include"]]
    if set(d["include"]) != set(s["include"]) and excluded:
        out.append("left out of the merge: " + ", ".join(label(i) for i in excluded))
    if d["name"] != s["name"]:
        out.append(f'name "{d["name"]}" instead of "{s["name"]}"')
    if [(u["uri"], u.get("match")) for u in d["uris"]] != [(u["uri"], u.get("match")) for u in s["uris"]]:
        out.append("URIs edited by you")
    for key, what in (("usernameFrom", "username"), ("passwordFrom", "password"), ("totpFrom", "TOTP key")):
        if not d.get(key) and not s.get(key):
            continue
        if d.get(key) != s.get(key) or (undecided and len(d["include"]) > 1):
            out.append(f"{what} taken from {label(d.get(key))}")
    if d["notesFrom"] != s["notesFrom"]:
        out.append("notes kept from: " + (", ".join(label(i) for i in d["notesFrom"]) or "none"))
    return out
