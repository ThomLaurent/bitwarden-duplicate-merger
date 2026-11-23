<div align="center">

# Bitwarden Duplicate Merger

**Findet und führt doppelte Zugangsdaten in deinem Bitwarden-Tresor zusammen, mit einer Prüfansicht vor jeder Änderung.**

[![tests](https://github.com/ThomLaurent/bitwarden-duplicate-merger/actions/workflows/tests.yml/badge.svg)](https://github.com/ThomLaurent/bitwarden-duplicate-merger/actions/workflows/tests.yml)
[![release](https://img.shields.io/github/v/release/ThomLaurent/bitwarden-duplicate-merger?label=download)](https://github.com/ThomLaurent/bitwarden-duplicate-merger/releases/latest)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)
[![license](https://img.shields.io/badge/license-Unlicense-blue)](../../LICENSE)

[English](../../README.md) · [Français](README.fr.md) · [Español](README.es.md) · Deutsch · [简体中文](README.zh-CN.md)

<img src="../screenshots/review-conflict.png" alt="Prüfansicht: drei Steam-Zugangsdaten mit zwei verschiedenen Passwörtern" width="900">

</div>

Nach einem Import aus dem Browser oder einem anderen Passwortmanager enthält ein Tresor oft dasselbe Konto mehrfach: `www.amazon.de`, `login.amazon.de` und `amazon.de/ap/signin`, mit gleichem Benutzernamen und Passwort. Bitwarden kann sie nicht zusammenführen, und bei Hunderten von Einträgen dauert das von Hand Stunden.

Dieses Tool gruppiert die Duplikate, schlägt für jede Gruppe eine Zusammenführung vor, lässt dich jede Entscheidung auf einer lokalen Webseite prüfen und ändern und wendet dann nur das an, was du bestätigt hast, über die offizielle Bitwarden-CLI.

## Ablauf

1. **Tool starten.** Die Bitwarden-CLI entsperrt den Tresor und eine Seite öffnet sich im Browser.
2. **Vorschläge prüfen.** Zugangsdaten mit gleicher Domain und gleichem Benutzernamen werden gruppiert. Gruppen, die die Regel nicht allein entscheiden kann (verschiedene Passwörter, Passkeys...), werden markiert.
3. **Alles anpassen**: behaltener Eintrag, Name, Passwort, TOTP, Notizen, URIs, auszulassende Einträge. Bei Bedarf manuell gruppieren (`ebay.de` und `ebay.com`).
4. **Jederzeit unterbrechen und fortsetzen.** Entscheidungen werden in einer Datei gespeichert, auch über Neustarts hinweg.
5. **Anwenden**: alle bestätigten Gruppen oder nur einige. Ein Bericht zeigt das Ergebnis, beginnend mit den Entscheidungen, die von der Regel abweichen.

## Garantien

- **Dein Master-Passwort erreicht das Tool nie.** Nur die Bitwarden-CLI liest es; das Tool erhält den Sitzungsschlüssel und hält ihn im Speicher.
- **Keine Geheimnisse auf der Festplatte oder in Logs.** Passwörter, TOTP-Schlüssel, Felder und Notizen werden im Speicher verglichen. Die Seite zeigt einen Wert nur, wenn du auf "show" klickst.
- **Nichts ändert sich ohne deine Bestätigung**, und nur bestätigte Gruppen werden angewendet.
- **Kein veralteter Plan.** Direkt vor jeder Gruppe prüft das Tool bei Bitwarden, dass sich seit deiner Prüfung nichts geändert hat. Sonst wird die Gruppe übersprungen und gemeldet.
- **Umkehrbar.** Duplikate landen im Bitwarden-Papierkorb (30 Tage), behaltene Einträge behalten ID, Anhänge und Passkeys, und vor dem Anwenden wird ein verschlüsseltes Backup erstellt.
- **Nur lokal.** Die Seite läuft auf `127.0.0.1` mit einem Zufallstoken. Kein Netzwerkzugriff außer `bw` zu deinem Bitwarden-Server und dem unten beschriebenen Download von `bw`.
- **Offizielle Bitwarden-CLI.** Ist `bw` nicht installiert, bietet das Tool an, es aus den Bitwarden-Releases auf GitHub herunterzuladen, und prüft die SHA-256-Prüfsumme. Diese Kopie hält es aktuell und prüft dafür einmal im Monat.
- **Klein und lesbar.** Rund 2.300 Zeilen Python und JavaScript, nur Standardbibliothek, keine Abhängigkeiten zu prüfen.

## Schnellstart

<details open>
<summary><b>Windows</b></summary>

1. Lade **`bw-dedupe-windows-x64.exe`** aus dem [neuesten Release](https://github.com/ThomLaurent/bitwarden-duplicate-merger/releases/latest) herunter.
2. Leg die Datei in einen eigenen Ordner, zum Beispiel einen neuen Ordner `bw-dedupe` unter Dokumente. Deine Entscheidungen und Berichte werden daneben gespeichert.
3. Doppelklicke sie. Zeigt Windows „Der Computer wurde durch Windows geschützt“, klicke auf **Weitere Informationen** und dann auf **Trotzdem ausführen**: Die Datei ist nicht signiert.
4. Ein schwarzes Fenster öffnet sich. Beim ersten Start bietet es an, das offizielle Bitwarden-Kommandozeilentool herunterzuladen: Drücke die Eingabetaste.
5. Melde dich in diesem Fenster bei Bitwarden an: E-Mail, Master-Passwort und, falls du sie nutzt, den Code der zweistufigen Anmeldung. Beim Tippen des Passworts erscheint nichts, das ist normal.
6. Die Prüfseite öffnet sich in deinem Browser.

</details>

<details>
<summary><b>macOS</b></summary>

1. Lade **`bw-dedupe-macos-arm64`** aus dem [neuesten Release](https://github.com/ThomLaurent/bitwarden-duplicate-merger/releases/latest) herunter. Es läuft auf Macs mit Apple-Chip (M1 oder neuer); auf einem Intel-Mac starte es aus dem Quellcode.
2. Öffne die App Terminal und führe diese Befehle nacheinander aus. Der zweite erlaubt macOS, eine nicht signierte Datei zu starten.
   ```bash
   cd ~/Downloads
   ```
   ```bash
   chmod +x bw-dedupe-macos-arm64 && xattr -d com.apple.quarantine bw-dedupe-macos-arm64
   ```
   ```bash
   ./bw-dedupe-macos-arm64
   ```
3. Beim ersten Start bietet das Tool an, das offizielle Bitwarden-Kommandozeilentool herunterzuladen: Drücke die Eingabetaste.
4. Melde dich im Terminal bei Bitwarden an: E-Mail, Master-Passwort und, falls du sie nutzt, den Code der zweistufigen Anmeldung. Beim Tippen des Passworts erscheint nichts, das ist normal.
5. Die Prüfseite öffnet sich in deinem Browser.

</details>

<details>
<summary><b>Linux</b></summary>

Lade **`bw-dedupe-linux-x64`** aus dem [neuesten Release](https://github.com/ThomLaurent/bitwarden-duplicate-merger/releases/latest) herunter, dann im Terminal:

```bash
chmod +x bw-dedupe-linux-x64
```
```bash
./bw-dedupe-linux-x64
```

Beim ersten Start bietet das Tool an, die offizielle Bitwarden-CLI herunterzuladen. Melde dich an, wenn `bw` danach fragt, und prüfe auf der geöffneten Seite.

</details>

<details>
<summary><b>Aus dem Quellcode</b> (jedes System mit Python 3.10+)</summary>

Ohne Installation:

```bash
git clone https://github.com/ThomLaurent/bitwarden-duplicate-merger
```
```bash
cd bitwarden-duplicate-merger
```
```bash
python bw_dedupe.py
```

</details>

**Erst ausprobieren** mit einem erfundenen Tresor, ohne Bitwarden-CLI oder Konto: Starte es im Terminal mit `--demo`, zum Beispiel `python bw_dedupe.py --demo`. Es wird nichts in einem Tresor gespeichert.

Die ausführbaren Dateien bringen ihr eigenes Python mit und funktionieren daher unabhängig von deiner Python-Version, solange `bw` seine Befehle beibehält. Jede wird von GitHub Actions aus diesem Repository gebaut und lässt sich prüfen mit:

```bash
gh attestation verify bw-dedupe-windows-x64.exe --repo ThomLaurent/bitwarden-duplicate-merger
```

Mehr (auf Englisch): [Benutzerhandbuch](../USAGE.md).

## Projektstatus

Dieses Tool wird **so wie es ist** geteilt und wird wahrscheinlich nicht weiterentwickelt. Ich habe es gebaut, um meinen eigenen Tresor aufzuräumen, und wollte es lieber offen teilen als für mich behalten. Ich hoffe, es erspart dir Zeit und Tokens für einen Nachbau und vor allem die Stunden, Hunderte von Einträgen von Hand zusammenzuführen.

Issues und Pull Requests bleiben möglicherweise unbeantwortet. Forks sind willkommen: Der Code ist gemeinfrei ([Unlicense](../../LICENSE)), und [AGENTS.md](../../AGENTS.md) erklärt ihn dir und KI-Programmierassistenten.

Nicht mit Bitwarden, Inc. verbunden. "Bitwarden" ist eine Marke von Bitwarden, Inc.
