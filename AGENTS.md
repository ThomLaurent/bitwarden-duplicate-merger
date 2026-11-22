# AGENTS.md

Guide for AI coding assistants and contributors. Read this before changing code.

## What the tool does

Local web UI to review and merge duplicate Bitwarden logins through the official `bw` CLI.
User-facing docs: `README.md` (pitch, quick start) and `docs/USAGE.md` (full behavior).

## Layout

| Path | Role |
|---|---|
| `bw_dedupe.py` | Entry point: arguments, terminal unlock, starts the server. |
| `bwdedupe/vault.py` | `Bw` wrapper around the `bw` CLI, `Login` parsing, non-secret item summaries. |
| `bwdedupe/psl.py` + `public_suffix_list.dat` | Registrable domain lookup with the bundled Public Suffix List. |
| `bwdedupe/rules.py` | Duplicate rule, default decisions, `build_payload` for `bw edit`, `describe_differences` for the report. |
| `bwdedupe/state.py` | `Session`: work file, reconciliation with the vault, UI edits, apply runs. |
| `bwdedupe/report.py` | Final HTML report of a run. |
| `bwdedupe/server.py` | HTTP server on 127.0.0.1, token auth, JSON API used by the UI. |
| `bwdedupe/unlock.py` | Unlock in the terminal, or in a terminal window that posts the session key back. |
| `bwdedupe/web/` | UI: vanilla JS (`app.js`), no build step, no external resource. |
| `tests/` | `unittest` suite, `fake_bw.py` (stand-in CLI), `demo_vault.py` (made-up data). |
| `docs/i18n/` | Translated READMEs. |
| `tools/screenshots.cjs` | Regenerates `docs/screenshots/` with Playwright. |
| `packaging/bw-dedupe.spec` | PyInstaller spec for the standalone executables. |
| `.github/workflows/` | `tests.yml` (CI), `release.yml` (executables on `v*` tags, with build attestations). |

## Data model

- A **group** (in the work file) has `items` (ids), `revisions` (id to `revisionDate` at review time), `suggestion` and `decision` (same shape), `kind` (`rule`, `conflict`, `skipped`, `manual`, `rename`) and `status` (`todo`, `validated`, `stale`, `failed`, `applied`).
- A **decision**: `action` (`merge`, `ignore` or `null` when the rule cannot decide), `keep`, `include`, `name`, `uris`, `usernameFrom`, `passwordFrom`, `totpFrom`, `notesFrom`. Secrets are referenced by the item they come from, never copied.
- `released`: item ids the user took out; the rule no longer suggests them.
- `runs`: one record per apply, rendered by `report.render`.

## Invariants (do not break)

1. No secret (password, TOTP, field value, note content, passkey, session key) is written to disk, logged, printed, or put on a command line. The work file and reports hold ids, names, usernames, URIs, dates and decisions only. `/api/secret` is the only way the UI reads a secret, on explicit click.
2. Payloads go to `bw edit` as base64 on stdin. The session key goes to `bw` through the `BW_SESSION` environment variable.
3. Before applying a group, compare each item's `revisionDate` with `group["revisions"]`. Any difference: skip the group, mark it `stale`.
4. Edit the kept item first; delete (trash) the others only if the edit succeeded and kept passkeys survived.
5. The server binds 127.0.0.1, checks the `Host` header and the `X-Token` header, and does not log requests.
6. Standard library only, Python 3.10+. Do not add dependencies: the tool must keep working years after download.
7. UI code renders vault values with `textContent` (the `h()` helper), never `innerHTML`.

## Commands

```bash
python -m unittest discover -s tests -v          # tests, no network, fake bw
python tests/demo_vault.py /tmp/demo.json         # demo vault for manual runs
FAKE_VAULT=/tmp/demo.json BW_SESSION=fake-session python bw_dedupe.py --bw ./tests/fake_bw.py
pyinstaller --distpath dist packaging/bw-dedupe.spec   # standalone executable
```

Screenshots: start the tool on the demo vault with `--no-browser`, then `node tools/screenshots.cjs <printed url> docs/screenshots` (needs `playwright`).

Refresh the Public Suffix List: download https://publicsuffix.org/list/public_suffix_list.dat over `bwdedupe/public_suffix_list.dat`.

## Conventions

- English everywhere (code, comments, UI, docs). Translated READMEs: `docs/i18n/README.<lang>.md`, keep them in sync with `README.md` when its content changes.
- Comments only where a reader of the code needs them.
- Any behavior change: update `docs/USAGE.md` and add or adjust a test in `tests/test_flow.py`.
