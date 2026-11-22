<div align="center">

# Bitwarden Duplicate Merger

**Find and merge duplicate logins in your Bitwarden vault, with a review screen before anything changes.**

[![tests](https://github.com/ThomLaurent/bitwarden-duplicate-merger/actions/workflows/tests.yml/badge.svg)](https://github.com/ThomLaurent/bitwarden-duplicate-merger/actions/workflows/tests.yml)
[![release](https://img.shields.io/github/v/release/ThomLaurent/bitwarden-duplicate-merger?label=download)](https://github.com/ThomLaurent/bitwarden-duplicate-merger/releases/latest)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)
![platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
[![license](https://img.shields.io/badge/license-Unlicense-blue)](LICENSE)

English · [Français](README.fr.md) · [Español](README.es.md) · [Deutsch](README.de.md) · [简体中文](README.zh-CN.md)

<img src="docs/screenshots/review-conflict.png" alt="Review screen: a group of three Steam logins with two different passwords, where the user picks the item and password to keep" width="900">

</div>

After importing passwords from a browser or another password manager, a vault often holds the same account several times: `www.amazon.fr`, `login.amazon.fr` and `amazon.fr/ap/signin`, all with the same username and password. Bitwarden has no built-in way to merge them, and doing it by hand for hundreds of logins takes hours.

This tool groups those duplicates, suggests how to merge each group, lets you check and change every decision in a local web page, then applies only what you validated, through the official Bitwarden CLI.

## How it works

1. **Start the tool.** The Bitwarden CLI unlocks your vault and a page opens in your browser.
2. **Review the suggestions.** Logins with the same domain and username are grouped. Groups the rule cannot decide alone (different passwords, passkeys...) are flagged for you.
3. **Change anything**: which item to keep, name, password, TOTP, notes, URIs, which items to leave out. Group logins by hand when needed (`ebay.fr` and `ebay.com`).
4. **Stop and resume any time.** Decisions are saved to a file, even across reboots.
5. **Apply** all validated groups, or a few at a time. A report lists what was done, starting with what you decided differently from the rule.

<img src="docs/screenshots/report.png" alt="Merge report: counts of edited and trashed items, then the decisions that differ from the rule" width="700">

## Guarantees

- **Your master password never reaches the tool.** Only the Bitwarden CLI reads it; the tool receives the session key and keeps it in memory.
- **Secrets are never written to disk or logged.** Passwords, TOTP keys, field values and notes are compared in memory. The page shows one only when you click "show".
- **Nothing changes without your validation**, and only the groups you validated are applied.
- **No stale plan.** Right before each group is applied, the tool checks with Bitwarden that none of its items changed since your review. Changed groups are skipped and reported.
- **Reversible.** Duplicates go to the Bitwarden trash (30 days), kept items keep their ID, attachments and passkeys, and an encrypted backup is made before applying.
- **Local only.** The page is served on `127.0.0.1` with a random token. No network access other than `bw` talking to your Bitwarden server.
- **Small and readable.** About 2,000 lines of Python and JavaScript, standard library only, no dependency to audit.

## Quick start

1. Install the [Bitwarden CLI](https://bitwarden.com/help/cli/) (`bw`).
2. Download the executable for your system from the [latest release](https://github.com/ThomLaurent/bitwarden-duplicate-merger/releases/latest) and run it from a terminal:
   ```bash
   ./bw-dedupe-linux-x64
   ```
   Or run from source with any Python 3.10+, nothing to install:
   ```bash
   git clone https://github.com/ThomLaurent/bitwarden-duplicate-merger
   cd bitwarden-duplicate-merger
   python bw_dedupe.py
   ```
3. Unlock the vault when `bw` asks, then review in the browser page that opens.

Executables bundle their own Python, so they keep working whatever Python you have, as long as `bw` keeps its commands. Each one is built by GitHub Actions from this repository and can be checked with:

```bash
gh attestation verify bw-dedupe-linux-x64 --repo ThomLaurent/bitwarden-duplicate-merger
```

More: [usage guide](docs/USAGE.md) (review, rule, options, undo, troubleshooting).

## Project status

This tool is shared **as is** and will probably not be improved. I built it to clean my own vault, and I thought it better to share it openly than to keep it to myself. I hope it saves you the time and tokens of building the same thing, and above all the hours of merging hundreds of logins by hand.

Issues and pull requests may not get an answer. Forks are welcome: the code is in the public domain ([Unlicense](LICENSE)), and [AGENTS.md](AGENTS.md) explains it to you and to AI coding assistants.

Not affiliated with Bitwarden, Inc. "Bitwarden" is a trademark of Bitwarden, Inc.
