"""Local web server for the UI. Bound to 127.0.0.1 and protected by a random token."""

from __future__ import annotations

import hmac
import json
import mimetypes
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import report, unlock
from .state import Session, SessionError
from .vault import BwError

WEB_DIR = Path(__file__).with_name("web")


class App:
    def __init__(self, session: Session, exe: str, lock_on_quit: bool, demo: bool = False):
        self.session = session
        self.exe = exe
        self.demo = demo
        self.lock_on_quit = lock_on_quit
        self.token = secrets.token_urlsafe(32)
        self.unlock_token: str | None = None
        self.unlock_error = ""
        self.httpd: ThreadingHTTPServer | None = None
        self.port = 0

    def serve(self, port: int) -> None:
        app = self

        class Handler(RequestHandler):
            pass

        Handler.app = app
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.port = self.httpd.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/#t={self.token}"

    def request_unlock(self) -> None:
        self.unlock_token = secrets.token_urlsafe(24)
        self.unlock_error = ""
        try:
            unlock.open_helper_window(self.exe, f"http://127.0.0.1:{self.port}/unlock-callback", self.unlock_token)
        except (BwError, OSError) as err:
            self.unlock_token = None
            self.unlock_error = f"could not open a terminal window ({err}). Run the tool from a terminal instead."

    def receive_session(self, token: str, key: str) -> None:
        if not self.unlock_token or not hmac.compare_digest(token, self.unlock_token):
            raise PermissionError
        self.unlock_token = None
        if not key:
            self.unlock_error = "unlock cancelled or failed"
            return
        self.session.bw.session = key
        try:
            self.session.open()
            if not self.session.unlocked:
                self.unlock_error = "the vault is still locked"
        except (BwError, SessionError) as err:
            self.unlock_error = str(err)

    def shutdown(self) -> None:
        if self.lock_on_quit and self.session.bw.session:
            try:
                self.session.bw.lock()
            except BwError:
                pass
        threading.Thread(target=self.httpd.shutdown, daemon=True).start()


class RequestHandler(BaseHTTPRequestHandler):
    app: App
    server_version = "bw-dedupe"
    sys_version = ""

    def log_message(self, *args) -> None:
        # Requests are never logged.
        pass

    def send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, status: int = 200) -> None:
        self.send(status, json.dumps(data).encode("utf-8"), "application/json")

    def fail(self, status: int, message: str) -> None:
        self.send_json({"error": message}, status)

    def host_ok(self) -> bool:
        # Rejects DNS rebinding: only our own loopback address is accepted.
        return self.headers.get("Host") in (f"127.0.0.1:{self.app.port}", f"localhost:{self.app.port}")

    def authorized(self) -> bool:
        token = self.headers.get("X-Token") or ""
        return hmac.compare_digest(token, self.app.token)

    def body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1_000_000:
            raise ValueError("request too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:
        if not self.host_ok():
            return self.fail(HTTPStatus.FORBIDDEN, "forbidden")
        url = urlsplit(self.path)
        if not url.path.startswith("/api/"):
            return self.static(url.path)
        if not self.authorized():
            return self.fail(HTTPStatus.UNAUTHORIZED, "unauthorized")
        s = self.app.session
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path == "/api/state":
                data = s.state()
                data["unlockPending"] = bool(self.app.unlock_token)
                data["unlockError"] = self.app.unlock_error
                data["demo"] = self.app.demo
                return self.send_json(data)
            if url.path == "/api/secret":
                return self.send_json({"value": s.secret(query.get("item", ""), query.get("kind", ""))})
            if url.path == "/api/report":
                with s.lock:
                    body = report.render(s.run(query.get("run", ""))).encode("utf-8")
                return self.send(200, body, "text/html; charset=utf-8")
        except SessionError as err:
            return self.fail(HTTPStatus.BAD_REQUEST, str(err))
        self.fail(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:
        if not self.host_ok():
            return self.fail(HTTPStatus.FORBIDDEN, "forbidden")
        path = urlsplit(self.path).path
        try:
            data = self.body()
        except ValueError:
            return self.fail(HTTPStatus.BAD_REQUEST, "invalid request")
        if path == "/unlock-callback":
            try:
                self.app.receive_session(str(data.get("token", "")), str(data.get("session", "")))
            except PermissionError:
                return self.fail(HTTPStatus.FORBIDDEN, "forbidden")
            return self.send_json({"ok": True})
        if not self.authorized():
            return self.fail(HTTPStatus.UNAUTHORIZED, "unauthorized")
        s = self.app.session
        try:
            if path == "/api/unlock":
                self.app.request_unlock()
            elif path == "/api/group/update":
                s.update_group(data["id"], data["decision"], data["status"])
            elif path == "/api/group/reset":
                s.reset_group(data["id"])
            elif path == "/api/group/remove-item":
                s.remove_item(data["id"], data["item"])
            elif path == "/api/group/create":
                return self.send_json({"id": s.create_group(list(data["items"]))})
            elif path == "/api/rename":
                return self.send_json({"count": s.rename(list(data["items"]))})
            elif path == "/api/refresh":
                with s.lock:
                    s.ensure_idle()
                    s.refresh_items()
                    s.reconcile()
                    s.save()
            elif path == "/api/apply":
                s.start_apply(list(data["groups"]), bool(data.get("backup", True)))
            elif path == "/api/quit":
                self.send_json({"ok": True})
                self.app.shutdown()
                return
            else:
                return self.fail(HTTPStatus.NOT_FOUND, "not found")
        except (SessionError, BwError, KeyError, TypeError) as err:
            return self.fail(HTTPStatus.BAD_REQUEST, str(err) or "invalid request")
        self.send_json({"ok": True})

    def static(self, path: str) -> None:
        name = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (WEB_DIR / name).resolve()
        if WEB_DIR.resolve() not in target.parents or not target.is_file():
            return self.fail(HTTPStatus.NOT_FOUND, "not found")
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type.endswith("javascript"):
            content_type += "; charset=utf-8"
        self.send(200, target.read_bytes(), content_type)
