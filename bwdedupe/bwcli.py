"""Find the Bitwarden CLI, or download the official build from Bitwarden's GitHub releases."""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import shutil
import ssl
import sys
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

RELEASES_API = "https://api.github.com/repos/bitwarden/clients/releases?per_page=100"
MANUAL_INSTALL = "https://bitwarden.com/help/cli/"
DEMO = "demo"
REFRESH_SECONDS = 30 * 24 * 3600
# Used when the bundled OpenSSL has no default CA file on this machine (seen with frozen executables).
CA_BUNDLES = ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt",
              "/etc/ssl/ca-bundle.pem")


class DownloadError(RuntimeError):
    pass


@dataclass
class Release:
    version: str
    url: str
    sha256: str
    size: int


def cache_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "bw-dedupe"


def cached_exe() -> Path:
    return cache_dir() / ("bw.exe" if sys.platform == "win32" else "bw")


def asset_platform(system: str = sys.platform, machine: str = platform.machine()) -> str:
    if system == "win32":
        # Only an x64 build exists; Windows on ARM runs it through emulation.
        return "windows"
    name = "macos" if system == "darwin" else "linux"
    return f"{name}-arm64" if machine.lower() in ("arm64", "aarch64") else name


def ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    paths = ssl.get_default_verify_paths()
    if not (paths.cafile and os.path.isfile(paths.cafile)) and not (paths.capath and os.path.isdir(paths.capath)):
        for bundle in CA_BUNDLES:
            if os.path.isfile(bundle):
                context.load_verify_locations(bundle)
                break
    return context


def fetch(url: str, accept: str = "application/vnd.github+json") -> bytes:
    request = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "bw-dedupe"})
    with urllib.request.urlopen(request, timeout=120, context=ssl_context()) as response:
        return response.read()


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) if p.isdigit() else 0 for p in version.split("."))


def pick_release(releases: list[dict], plat: str) -> Release:
    """Newest stable CLI release with a zip for this platform and a SHA-256 published by GitHub or Bitwarden."""
    for rel in releases:
        tag = rel.get("tag_name") or ""
        if not tag.startswith("cli-v") or rel.get("draft") or rel.get("prerelease"):
            continue
        version = tag[len("cli-v"):]
        assets = {a.get("name"): a for a in rel.get("assets") or []}
        for prefix in ("bw", "bw-bit", "bw-oss"):
            asset = assets.get(f"{prefix}-{plat}-{version}.zip")
            if not asset:
                continue
            digest = asset.get("digest") or ""
            if digest.startswith("sha256:"):
                sha256 = digest[len("sha256:"):]
            else:
                checksum = assets.get(f"{prefix}-{plat}-sha256-{version}.txt")
                if not checksum:
                    continue
                sha256 = fetch(checksum["browser_download_url"], "application/octet-stream").decode().split()[0]
            return Release(version, asset["browser_download_url"], sha256.lower(), int(asset.get("size") or 0))
    raise DownloadError(f"no Bitwarden CLI release found for {plat}")


def latest_release() -> Release:
    return pick_release(json.loads(fetch(RELEASES_API)), asset_platform())


def install(release: Release, target: Path) -> None:
    data = fetch(release.url, "application/octet-stream")
    if hashlib.sha256(data).hexdigest() != release.sha256:
        raise DownloadError("the download does not match its published SHA-256, nothing was installed")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        member = next((m for m in archive.infolist()
                       if not m.is_dir() and m.filename.rsplit("/", 1)[-1] in ("bw", "bw.exe")), None)
        if member is None:
            raise DownloadError("no bw executable in the downloaded archive")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        with archive.open(member) as src, open(tmp, "wb") as dst:
            shutil.copyfileobj(src, dst)
    tmp.chmod(0o755)
    os.replace(tmp, target)
    version_file(target).write_text(release.version, encoding="utf-8")


def version_file(exe: Path) -> Path:
    return exe.with_name("bw-version.txt")


def refresh(exe: Path) -> None:
    """Update a bw downloaded by this tool once it is a month old. Failures keep the current one."""
    stamp = version_file(exe)
    try:
        if time.time() - stamp.stat().st_mtime < REFRESH_SECONDS:
            return
        current = stamp.read_text(encoding="utf-8").strip()
    except OSError:
        current = ""
    try:
        release = latest_release()
        if version_key(release.version) > version_key(current):
            print(f"Updating the Bitwarden CLI to {release.version}...", flush=True)
            install(release, exe)
        else:
            stamp.touch()
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, DownloadError):
        pass


def resolve(explicit: str | None, interactive: bool) -> str | None:
    """Path of the bw executable: --bw, then PATH, then a copy downloaded earlier, then a new download.

    Returns DEMO when the user picks the demo vault instead of downloading bw.
    """
    if explicit:
        return explicit
    found = shutil.which("bw")
    if found:
        return found
    exe = cached_exe()
    if exe.is_file():
        refresh(exe)
        return str(exe)
    if not interactive:
        print(f"The Bitwarden CLI (bw) was not found. Start the tool from a terminal to download it, "
              f"install it ({MANUAL_INSTALL}), or pass --bw.", file=sys.stderr)
        return None
    print("This tool works through the official Bitwarden command-line tool (bw), which is not installed.\n"
          "  Y  download it from Bitwarden's official releases on GitHub, then open your vault\n"
          "  D  try the tool on a made-up demo vault first\n"
          "  N  quit")
    answer = input("Your choice [Y/d/n]: ").strip().lower()
    if answer in ("d", "demo"):
        return DEMO
    if answer not in ("", "y", "yes"):
        print(f"Install it yourself ({MANUAL_INSTALL}) or pass --bw <path>.", file=sys.stderr)
        return None
    try:
        print("Looking for the latest version...", flush=True)
        release = latest_release()
        size = f" ({release.size // 1_000_000} MB)" if release.size else ""
        print(f"Downloading the Bitwarden CLI {release.version}{size}...", flush=True)
        install(release, exe)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, DownloadError) as err:
        print(f"Download failed: {err}\nInstall it yourself ({MANUAL_INSTALL}) or pass --bw <path>.",
              file=sys.stderr)
        return None
    print(f"Bitwarden CLI saved to {exe}", flush=True)
    return str(exe)
