# bitwarden-duplicate-merger

Finds duplicate Bitwarden logins (same domain and username, different subdomain or URL), suggests how to merge them, and lets you review every change in a local web page before anything is applied.

The tool uses the official `bw` CLI and edits the vault in place. Item IDs, attachments, passkeys and history of the kept items are preserved.

## How it works

1. Start the tool. It unlocks the vault through `bw` and opens a page in your browser.
2. The rule groups the duplicates and suggests a merge for each group. Groups it cannot decide (different passwords, passkeys...) are flagged.
3. Review each group: change anything you want, then validate it.
4. Quit whenever you want. Decisions are saved and the review resumes where you left it, even after a reboot.
5. Apply the validated groups, all at once or a few at a time. A report shows what was done, starting with the changes that differ from the rule.

## Privacy

- Your master password is only read by the Bitwarden CLI. The tool only receives the session key, keeps it in memory and passes it to `bw` through the environment, never on the command line.
- Passwords, TOTP keys, custom field values and note contents are never written to disk or logged. The page shows them only when you click "show" on an item.
- The page is served on `127.0.0.1` only and protected by a random token.
- The work file and the reports contain item names, usernames, URIs and IDs. Keep them local.
- No network access other than through `bw`. The Public Suffix List bundled with `tldextract` is used.

## Requirements

- [Bitwarden CLI](https://bitwarden.com/help/cli/) (`bw`) in the PATH, or its path passed with `--bw`.
- [uv](https://docs.astral.sh/uv/): it installs `tldextract` automatically on first run.
  Without uv: Python 3.10+ and `pip install tldextract`, then `python bw_dedupe.py` instead of `uv run bw_dedupe.py`.

## Usage

```bash
uv run bw_dedupe.py
```

- If the vault is locked, `bw` asks for your master password in the terminal (and for your email and two-step login code the first time).
- If the tool is not started from a terminal, or the vault gets locked while you work, it opens a terminal window for `bw` and gets the session key back once you are done.
- Run it again from the same folder to resume.
- The vault is locked when you quit, unless `BW_SESSION` was already set or `--keep-unlocked` is passed.

### Review

Each group lists its items with:
- **Keep**: the item that is edited and stays in the vault. Its ID, attachments and passkeys are preserved.
- **Merge**: unchecked items are left untouched. Checked ones go to the Bitwarden trash.
- Letters (`A`, `B`...) in the Password, TOTP and Notes columns: items with the same letter hold the same value. The value itself is only shown with "show".

The **Result** section sets the name, username, password, TOTP key, notes and URIs of the kept item. Custom fields of all merged items, favorite, folder and master password re-prompt are merged automatically.

Other actions:
- **Leave untouched**: nothing changes, and the rule no longer suggests these items.
- **✕** on an item: takes it out of the group. The rule no longer suggests it.
- **All logins** tab: select logins to group them by hand (for example `amazon.fr` and `amazon.com`), or rename them after their domain.
- Shortcuts: `J` / `K` next / previous group, `V` validate and go to the next one, `/` search.

### Apply

**Apply validated** applies the validated groups only. Before each group, the tool syncs with Bitwarden and checks that none of its items changed since your review. Changed groups are skipped, listed in the report and come back to review.

An encrypted backup (`bw export --format encrypted_json`) is made first unless you uncheck it. `bw` may ask for your master password in the terminal for it.

### Reports

Each run writes `bw-dedupe-reports/bw-dedupe-report-<date>.html`, which opens without the tool. The **History** tab reopens them. A report shows:
- what differs from the rule: groups you created, resolved or changed, with your decisions;
- what was not applied (item changed in the vault, `bw` error);
- the merges applied as suggested;
- the `bw restore item <id>` commands to bring trashed items back.

### Options

| Option | Effect |
|---|---|
| `--workfile <path>` | Work file holding your decisions. Default: `bw-dedupe-session.json`. |
| `--reports <path>` | Folder for reports and backups. Default: `bw-dedupe-reports`. |
| `--port <n>` | Local port. Default: random. |
| `--no-browser` | Does not open the browser; open the printed link yourself. |
| `--keep-unlocked` | Does not lock the vault when quitting. |
| `--bw <path>` | Path of the `bw` executable. |

## Rule

Two logins are suggested as duplicates when they have:
- the same registrable domain: `login.amazon.fr` and `www.amazon.fr/ap/signin` both give `amazon.fr`. Private suffixes are respected: `alice.github.io` and `bob.github.io` stay separate;
- the same username, ignoring surrounding whitespace and case.

Suggested merge:
- **Kept item**: the one with attachments if there is one, otherwise the most recently modified.
- **Name**: the domain, for example `amazon.fr`. Bitwarden already shows the username next to it.
- **URIs**: a single `https://<domain>` URI with "base domain" match detection, plus app URIs (`androidapp://`, etc.). `http` is kept only if all the original URIs used `http`.
- **Taken from the others**: distinct notes (separated by `----`), missing custom fields, TOTP key if the kept item has none.

The rule does not decide, and leaves the group to you, when:

| Case | Why |
|---|---|
| Different passwords | One may be outdated. |
| Different TOTP keys | Same. |
| A passkey in the group | Passkeys cannot be moved; the tool checks the kept item still has its passkey after the edit. |
| Attachments on several items | The CLI cannot move an attachment. |

Never suggested: items with several domains, organization items, items without a usable web URI (app only, IP, `localhost`). The first and last can still be grouped by hand.

## Undo

- **Trashed items**: restore them from the Bitwarden trash within 30 days, or with the commands in the report.
- **Full rollback**, including kept items: re-import the encrypted backup. It can only be imported into the same account. Delete it once you have checked the result.
