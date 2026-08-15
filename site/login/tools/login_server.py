#!/usr/bin/env python3
"""Stdlib HTTP server for the HUM.org SQL login site.

Use this when PHP is not installed. It serves the same SQLite schema as
the PHP pages and binds to 127.0.0.1 by default.
"""

from __future__ import annotations

import argparse
import http.cookies
import http.server
import mimetypes
import sys
import urllib.parse
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import authlib
import templates

LOGIN_ROOT = authlib.LOGIN_ROOT
STATIC_PREFIXES = ("/assets/", "/xml/", "/docs/")


def parse_args() -> argparse.Namespace:
    config = authlib.load_config()
    parser = argparse.ArgumentParser(description="Serve the SQL login website with stdlib HTTP.")
    parser.add_argument("--database", default=str(config.database_path))
    parser.add_argument("--host", default=config.bind_host)
    parser.add_argument("--port", type=int, default=config.bind_port)
    return parser.parse_args()


def parse_form(body: bytes) -> dict[str, str]:
    parsed = urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[0] if values else "" for key, values in parsed.items()}


def cookie_header(name: str, value: str, max_age: int) -> str:
    cookie = http.cookies.SimpleCookie()
    cookie[name] = value
    cookie[name]["path"] = "/"
    cookie[name]["httponly"] = True
    cookie[name]["samesite"] = "Lax"
    cookie[name]["max-age"] = str(max_age)
    return cookie.output(header="")


def clear_cookie(name: str) -> str:
    return cookie_header(name, "", 0)


class LoginHandler(http.server.BaseHTTPRequestHandler):
    server_version = "HUMLogin/1.0"
    database_path = authlib.DEFAULT_DATABASE
    config = authlib.AuthConfig()

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def conn(self):
        connection = authlib.open_database(self.database_path)
        authlib.apply_schema(connection)
        return connection

    def client_ip(self) -> str:
        return self.client_address[0]

    def read_session_token(self) -> str | None:
        raw = self.headers.get("Cookie", "")
        jar = http.cookies.SimpleCookie()
        try:
            jar.load(raw)
        except http.cookies.CookieError:
            return None
        morsel = jar.get(self.config.cookie_name)
        return morsel.value if morsel else None

    def current_user(self, conn):
        return authlib.load_session_user(conn, self.read_session_token())

    def send_html(
        self,
        html: str,
        status: int = 200,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None:
        payload = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in extra_headers or []:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def send_xml(self, xml_text: str) -> None:
        payload = xml_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def redirect(self, location: str, extra_headers: list[tuple[str, str]] | None = None) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        for key, value in extra_headers or []:
            self.send_header(key, value)
        self.end_headers()

    def send_static(self, url_path: str) -> None:
        relative = url_path.lstrip("/")
        target = (LOGIN_ROOT / relative).resolve()
        if not str(target).startswith(str(LOGIN_ROOT.resolve())) or not target.is_file():
            self.send_error(404)
            return
        data = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if target.suffix == ".xhtml":
            content_type = "application/xhtml+xml"
        elif target.suffix == ".xml":
            content_type = "application/xml"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ("/assets/login.css", "/assets/login.js") or path.startswith(STATIC_PREFIXES):
            self.send_static(path)
            return
        conn = self.conn()
        try:
            user = self.current_user(conn)
            if path in ("/", "/index.html", "/index.php"):
                self.send_html(templates.landing())
                return
            if path in ("/login", "/login.php"):
                if user:
                    self.redirect("/dashboard")
                    return
                csrf = authlib.issue_csrf(conn)
                self.send_html(templates.page("Sign in", templates.auth_form("/login", "Sign in", csrf, submit="Sign in", form_id="login-form"), user))
                return
            if path in ("/register", "/register.php"):
                if user:
                    self.redirect("/dashboard")
                    return
                csrf = authlib.issue_csrf(conn)
                self.send_html(
                    templates.page(
                        "Register",
                        templates.auth_form("/register", "Create account", csrf, submit="Register", form_id="register-form"),
                        user,
                    )
                )
                return
            if path in ("/dashboard", "/dashboard.php"):
                if user is None:
                    self.redirect("/login")
                    return
                self.send_html(templates.page("Dashboard", templates.dashboard(user), user))
                return
            if path in ("/account", "/account.php"):
                if user is None:
                    self.redirect("/login")
                    return
                csrf = authlib.issue_csrf(conn)
                self.send_html(templates.page("Account", templates.account_form(user, csrf), user))
                return
            if path in ("/api/session.xml", "/api/session.php"):
                self.send_xml(templates.session_xml(user))
                return
            self.send_error(404)
        finally:
            conn.close()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 32_768:
            self.send_error(413)
            return
        form = parse_form(self.rfile.read(length))
        conn = self.conn()
        try:
            if path in ("/logout", "/logout.php"):
                authlib.destroy_session(conn, self.read_session_token())
                self.redirect("/", [("Set-Cookie", clear_cookie(self.config.cookie_name).strip())])
                return
            if not authlib.consume_csrf(conn, form.get("csrf")):
                self.send_html(templates.page("Request rejected", "<section class='panel'><p>The form token was missing or expired. Reload and try again.</p></section>"), 400)
                return
            if path in ("/login", "/login.php"):
                try:
                    user = authlib.authenticate(
                        conn,
                        form.get("username", "").strip(),
                        form.get("password", ""),
                        self.client_ip(),
                        self.config,
                    )
                except PermissionError as exc:
                    csrf = authlib.issue_csrf(conn)
                    body = templates.auth_form("/login", "Sign in", csrf, submit="Sign in", form_id="login-form")
                    self.send_html(templates.page("Sign in", body, error=str(exc)), 401)
                    return
                token = authlib.create_session(
                    conn,
                    user.id,
                    self.client_ip(),
                    self.headers.get("User-Agent", ""),
                    self.config,
                )
                self.redirect("/dashboard", [("Set-Cookie", cookie_header(self.config.cookie_name, token, self.config.session_ttl).strip())])
                return
            if path in ("/register", "/register.php"):
                if form.get("password") != form.get("confirm"):
                    csrf = authlib.issue_csrf(conn)
                    body = templates.auth_form("/register", "Create account", csrf, submit="Register", form_id="register-form")
                    self.send_html(templates.page("Register", body, error="Passwords do not match."), 400)
                    return
                try:
                    user = authlib.create_user(
                        conn,
                        form.get("username", "").strip(),
                        form.get("email", "").strip(),
                        form.get("password", ""),
                        form.get("username", "").strip(),
                        self.config,
                    )
                except ValueError as exc:
                    csrf = authlib.issue_csrf(conn)
                    body = templates.auth_form("/register", "Create account", csrf, submit="Register", form_id="register-form")
                    self.send_html(templates.page("Register", body, error=str(exc)), 400)
                    return
                token = authlib.create_session(
                    conn,
                    user.id,
                    self.client_ip(),
                    self.headers.get("User-Agent", ""),
                    self.config,
                )
                self.redirect("/dashboard", [("Set-Cookie", cookie_header(self.config.cookie_name, token, self.config.session_ttl).strip())])
                return
            if path in ("/account", "/account.php"):
                user = self.current_user(conn)
                if user is None:
                    self.redirect("/login")
                    return
                try:
                    authlib.update_display_name(conn, user.id, form.get("display_name", ""))
                    if form.get("new_password"):
                        authlib.change_password(
                            conn,
                            user.id,
                            form.get("current_password", ""),
                            form.get("new_password", ""),
                            self.config,
                        )
                except (ValueError, PermissionError) as exc:
                    csrf = authlib.issue_csrf(conn)
                    fresh = authlib.get_user_by_id(conn, user.id)
                    self.send_html(templates.page("Account", templates.account_form(fresh or user, csrf), user, error=str(exc)), 400)
                    return
                self.redirect("/dashboard")
                return
            self.send_error(404)
        finally:
            conn.close()


def serve(host: str, port: int, database: Path) -> None:
    config = authlib.load_config()
    LoginHandler.database_path = database
    LoginHandler.config = config
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    server = http.server.ThreadingHTTPServer((host, port), LoginHandler)
    print(f"login server http://{host}:{port} database={database}")
    server.serve_forever()


def main() -> int:
    args = parse_args()
    database = Path(args.database)
    conn = authlib.open_database(database)
    authlib.apply_schema(conn)
    conn.close()
    serve(args.host, args.port, database)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
