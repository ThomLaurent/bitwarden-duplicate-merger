"""Vault unlock flow. Only `bw` reads the master password; this tool only receives the session key."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .vault import Bw, BwError


def prompt_session(exe: str) -> str | None:
    """Run `bw login` or `bw unlock` in the current terminal and return the session key."""
    status = Bw(exe).status().get("status")
    args = ["login", "--raw"] if status == "unauthenticated" else ["unlock", "--raw"]
    # bw prompts on stderr, so only the session key is captured.
    proc = subprocess.run([exe, *args], stdout=subprocess.PIPE, text=True)
    key = proc.stdout.strip()
    return key if proc.returncode == 0 and key else None


def run_helper(exe: str, callback: str, token: str) -> int:
    """Entry point of the terminal window opened by the tool."""
    print("Bitwarden duplicate merger: unlock your vault.\n"
          "Your master password is read by the Bitwarden CLI only.\n")
    try:
        key = prompt_session(exe)
    except BwError as err:
        print(err, file=sys.stderr)
        key = None
    body = json.dumps({"token": token, "session": key or ""}).encode("utf-8")
    request = urllib.request.Request(callback, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(request, timeout=10).close()
    except OSError as err:
        print(f"Could not reach the tool: {err}", file=sys.stderr)
        time.sleep(10)
        return 1
    print("Vault unlocked, back to the browser." if key else "Unlock cancelled or failed.")
    time.sleep(3)
    return 0 if key else 1


def open_helper_window(exe: str, callback: str, token: str) -> None:
    script = Path(sys.argv[0]).resolve()
    cmd = [sys.executable, str(script), "--bw", exe, "--unlock-helper", callback, token]
    if sys.platform == "win32":
        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
        return
    line = " ".join(shlex.quote(c) for c in cmd)
    if sys.platform == "darwin":
        script_text = f'tell application "Terminal" to do script "{line}"\ntell application "Terminal" to activate'
        subprocess.Popen(["osascript", "-e", script_text])
        return
    for term, flag in (("x-terminal-emulator", "-e"), ("gnome-terminal", "--"), ("konsole", "-e"),
                       ("xfce4-terminal", "-x"), ("kitty", ""), ("alacritty", "-e"), ("xterm", "-e")):
        path = shutil.which(term)
        if path:
            subprocess.Popen([path, *([flag] if flag else []), *cmd])
            return
    raise BwError("no terminal emulator found: run the tool from a terminal instead")
