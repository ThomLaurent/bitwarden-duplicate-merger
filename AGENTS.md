# AGENTS.md

Guide for AI coding assistants and contributors. Read this before changing code.

## What the tool does

Local web UI to review and merge duplicate Bitwarden logins through the official `bw` CLI.
User-facing docs: `README.md` (pitch, quick start) and `docs/USAGE.md` (full behavior).

## Layout

| Path | Role |
|---|---|
| `bw_dedupe.py` | Entry point: arguments, terminal unlock, starts the server. |
| `bwdedupe/bwcli.py` | Finds `bw`, or downloads the official build from Bitwarden's GitHub releases (SHA-256 checked). |
| `bwdedupe/demo.py` | Made-up vault and in-process `bw` stand-in for `--demo`, shared with the tests. |
| `bwdedupe/vault.py` | `Bw` wrapper around the `bw` CLI, `Login` parsing, non-secret item summaries. |
| `bwdedupe/psl.py` + `public_suffix_list.dat` | Registrable domain lookup with the bundled Public Suffix List. |
| `bwdedupe/rules.py` | Duplicate rule, default decisions, `build_payload` for `bw edit`, `describe_differences` for the report. |
| `bwdedupe/state.py` | `Session`: work file, reconciliation with the vault, UI edits, apply runs. |
| `bwdedupe/report.py` | Final HTML report of a run. |
| `bwdedupe/server.py` | HTTP server on 127.0.0.1, token auth, JSON API used by the UI. |
| `bwdedupe/unlock.py` | Unlock in the terminal, or in a terminal window that posts the session key back. |
| `bwdedupe/web/` | UI: vanilla JS (`app.js`), no build step, no external resource. |
| `tests/` | `unittest` suite, `fake_bw.py` (stand-in CLI over a JSON file), `demo_vault.py` (writes the demo vault to a file). |
| `docs/translations/` | Translated READMEs. |
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
8. No network access besides `bw`, except `bwcli.py`: it downloads `bw` from Bitwarden's GitHub releases only (asking first, then a monthly update) and checks the SHA-256 before saving it.

## Commands

```bash
python -m unittest discover -s tests -v          # tests, no network, fake bw
python bw_dedupe.py --demo                        # made-up vault, in memory
python tests/demo_vault.py /tmp/demo.json         # same vault in a file, to test the unlock flow
FAKE_VAULT=/tmp/demo.json python bw_dedupe.py --bw ./tests/fake_bw.py   # master password: master
pyinstaller --distpath dist packaging/bw-dedupe.spec   # standalone executable
```

Test an executable without a release: Actions, `release`, Run workflow. It builds the three executables and attaches them to the run, without publishing anything. Or build for your own system with `pip install pyinstaller==6.11.1` and the `pyinstaller` command above.

Screenshots: a release refreshes `docs/screenshots/` and commits them to `main`. By hand: start the tool with `--demo --no-browser`, then `node tools/screenshots.cjs <printed url> docs/screenshots` (needs `playwright`). The demo badge is hidden in screenshots.

Refresh the Public Suffix List: download https://publicsuffix.org/list/public_suffix_list.dat over `bwdedupe/public_suffix_list.dat`.

## Conventions

- English everywhere (code, comments, UI, docs). Translated READMEs: `docs/translations/README.<lang>.md`, keep them in sync with `README.md` when its content changes.
- Comments only where a reader of the code needs them.
- Any behavior change: update `docs/USAGE.md` and add or adjust a test in `tests/test_flow.py`.
- Work left for later goes in a GitHub issue on this repository, not in a TODO in code or docs. No project board for now.
