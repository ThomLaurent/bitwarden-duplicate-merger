# bitwarden-duplicate-merger

Merges duplicate Bitwarden logins: same domain, same username and same password, but a different subdomain or URL.

The script uses the official `bw` CLI and edits the vault in place. Item IDs, attachments, passkeys and history are preserved.

## Privacy

- Passwords, TOTP keys, custom field values and note contents are only compared in memory. They are never printed, logged or written to the report.
- Modified items are sent to `bw` through standard input, never as command-line arguments.
- The script makes no network access other than through `bw`. It uses the Public Suffix List bundled with `tldextract`.
- The HTML reports contain item names, usernames, URIs and IDs. Keep them local. `--mask-usernames` masks usernames.

## Requirements

- [Bitwarden CLI](https://bitwarden.com/help/cli/) (`bw`) in the PATH, or its path passed with `--bw`.
- [uv](https://docs.astral.sh/uv/): it installs `tldextract` automatically on first run.
  Without uv: Python 3.10+ and `pip install tldextract`, then `python bw_dedupe.py` instead of `uv run bw_dedupe.py`.

## Usage

1. Log in and unlock the vault.

   PowerShell:
   ```powershell
   bw login
   $env:BW_SESSION = bw unlock --raw
   ```
   Bash:
   ```bash
   bw login
   export BW_SESSION="$(bw unlock --raw)"
   ```

2. Dry run: generates a report without changing anything.
   ```bash
   uv run bw_dedupe.py
   ```

3. Apply:
   ```bash
   uv run bw_dedupe.py --apply
   ```
   The script:
   1. writes the preview `bw-dedupe-report-<date>-preview.html`;
   2. waits for you to type `yes` (any other answer cancels without touching anything);
   3. makes an encrypted backup `bw-backup-<date>.json`;
   4. applies exactly the plan shown in the preview;
   5. writes `bw-dedupe-report-<date>.html` with the status of each change.

4. Lock the vault when done:
   ```bash
   bw lock
   ```

### Options

| Option | Effect |
|---|---|
| `--apply` | Applies the changes after preview and confirmation. Without it, the script does a dry run. |
| `--yes` | Skips the confirmation. Avoid it on the first run. |
| `--no-backup` | Skips the encrypted backup before applying. |
| `--rename-all` | Also renames non-duplicated logins after their domain. |
| `--mask-usernames` | Masks usernames in the report (`m***@gmail.com`). |
| `--report <path>` | Path of the HTML report. |
| `--bw <path>` | Path of the `bw` executable. |

## Rules

### Duplicates

Two logins are duplicates when they have:
- the same registrable domain: `login.amazon.fr` and `www.amazon.fr/ap/signin` both give `amazon.fr`. Private suffixes are respected: `alice.github.io` and `bob.github.io` stay separate;
- the same username, ignoring surrounding whitespace and case;
- the same password.

### Merge

- **Kept item**: the one with attachments if there is one, otherwise the most recently modified.
- **Name**: the domain, for example `amazon.fr`.
- **URIs**: a single `https://<domain>` URI with "base domain" match detection, plus app URIs (`androidapp://`, etc.). `http` is kept only if all the original URIs used `http`.
- **Taken from duplicates**: distinct notes (separated by `----`), missing custom fields, TOTP key if the kept item has none, favorite, folder, master password re-prompt.
- **Duplicates**: moved to the Bitwarden trash, recoverable for 30 days.

### Items never modified

They are all listed in the report:

| Case | Reason |
|---|---|
| Same domain and username, different passwords | Conflict: one may be outdated, review manually. Labels `password A` / `password B` show which items share the same password without revealing it. |
| Same domain, username and password, different TOTP keys | Conflict. |
| Group containing a passkey | Copying passkeys through the CLI is considered risky. |
| Attachments on several items of the group | The CLI cannot move an attachment. |
| Item pointing to several domains | Ambiguous domain. |
| Organization item | Only the personal vault is processed. |
| No usable web URI (app only, IP, `localhost`) | No domain. |

## Undo

- **Restore deleted duplicates**: the final report lists the `bw restore item <id>` commands.
- **Full rollback**, including kept items: re-import `bw-backup-<date>.json`. This export is encrypted with the account key and can only be imported into the same account. Delete it once you have checked the result.

## Errors

The console only shows the ID of the affected item and the `bw` error message. A failed edit means nothing is deleted in that group. A `Ctrl+C` during apply still writes the report with what was done.
