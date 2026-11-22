"""Registrable domain lookup with the bundled Public Suffix List (https://publicsuffix.org).

The list is read from `public_suffix_list.dat` next to this file, private domains included,
so that `alice.github.io` and `bob.github.io` stay distinct. Update that file to refresh it.
"""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from pathlib import Path

LIST_FILE = Path(__file__).with_name("public_suffix_list.dat")


def _ascii(name: str) -> str:
    try:
        return name.encode("idna").decode("ascii")
    except UnicodeError:
        return name


@lru_cache(maxsize=1)
def _rules() -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    exact, wildcard, exception = set(), set(), set()
    for line in LIST_FILE.read_text(encoding="utf-8").splitlines():
        rule = line.strip().split()[0] if line.strip() else ""
        if not rule or rule.startswith("//"):
            continue
        rule = rule.lower()
        if rule.startswith("!"):
            exception.add(_ascii(rule[1:]))
        elif rule.startswith("*."):
            wildcard.add(_ascii(rule[2:]))
        else:
            exact.add(_ascii(rule))
    return frozenset(exact), frozenset(wildcard), frozenset(exception)


def registrable_domain(host: str) -> str | None:
    """Return the registrable domain of a host, or None for IPs, single labels and unknown suffixes."""
    host = (host or "").strip().rstrip(".").lower()
    if not host:
        return None
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        pass
    labels = _ascii(host).split(".")
    if any(not label for label in labels):
        return None
    exact, wildcard, exception = _rules()
    suffix_len = 0
    for i in range(len(labels)):
        name = ".".join(labels[i:])
        if name in exception:
            suffix_len = len(labels) - i - 1
            break
        parent = ".".join(labels[i + 1:])
        if name in exact or (parent and parent in wildcard):
            suffix_len = len(labels) - i
            break
    if not suffix_len or suffix_len >= len(labels):
        return None
    domain = ".".join(labels[-suffix_len - 1:])
    try:
        return domain.encode("ascii").decode("idna")
    except UnicodeError:
        return domain
