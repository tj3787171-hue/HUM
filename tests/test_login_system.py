"""Tests for the site/login SQLite login desk."""

from __future__ import annotations

import http.cookiejar
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "site" / "login" / "tools"
LOGIN = ROOT / "site" / "login"
sys.path.insert(0, str(TOOLS))

import authlib  # noqa: E402


EXPECTED_FILES = (
    "sql/schema.sql",
    "includes/config.php",
    "includes/db.php",
    "includes/auth.php",
    "includes/csrf.php",
    "includes/layout.php",
    "index.php",
    "index.html",
    "login.php",
    "register.php",
    "logout.php",
    "dashboard.php",
    "account.php",
    "api/session.php",
    "assets/login.css",
    "assets/login.js",
    "xml/auth-config.xml",
    "xml/sitemap.xml",
    "docs/login-system.xhtml",
    "docs/login-system.rtf",
    "docs/login-system.doc",
    "tools/authlib.py",
    "tools/init_auth_db.py",
    "tools/login_server.py",
    "README.md",
    ".htaccess",
)


def _init_db(path: Path) -> sqlite3.Connection:
    conn = authlib.open_database(path)
    authlib.apply_schema(conn)
    return conn


class TestLoginTree(unittest.TestCase):
    def test_required_files_exist(self) -> None:
        for relative in EXPECTED_FILES:
            with self.subTest(relative=relative):
                self.assertTrue((LOGIN / relative).is_file())

    def test_schema_defines_core_tables(self) -> None:
        sql = (LOGIN / "sql" / "schema.sql").read_text(encoding="utf-8")
        for table in ("users", "sessions", "login_attempts", "csrf_tokens"):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", sql)

    def test_php_uses_bound_parameters(self) -> None:
        auth = (LOGIN / "includes" / "auth.php").read_text(encoding="utf-8")
        self.assertIn("prepare(", auth)
        self.assertNotIn('$_POST[', auth)
        self.assertIn("pbkdf2_sha256", auth)

    def test_xml_documents_parse(self) -> None:
        for relative in ("xml/auth-config.xml", "xml/sitemap.xml", "docs/login-system.xhtml"):
            with self.subTest(relative=relative):
                ET.parse(LOGIN / relative)

    def test_lab_nav_links_to_login(self) -> None:
        index = (ROOT / "site" / "index.php").read_text(encoding="utf-8")
        self.assertIn('href="login/"', index)


class TestAuthlib(unittest.TestCase):
    def test_register_login_and_reject_bad_password(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "auth.sqlite"
            conn = _init_db(db)
            user = authlib.create_user(conn, "labuser", "lab@hum.local", "LabOnly1234")
            self.assertEqual(user.username, "labuser")
            row = conn.execute("SELECT password_hash FROM users WHERE username = ?", ("labuser",)).fetchone()
            self.assertIsNotNone(row)
            self.assertTrue(str(row["password_hash"]).startswith("pbkdf2_sha256$"))
            self.assertNotIn("LabOnly1234", str(row["password_hash"]))

            signed = authlib.authenticate(conn, "labuser", "LabOnly1234", "127.0.0.1")
            self.assertEqual(signed.id, user.id)

            with self.assertRaises(PermissionError):
                authlib.authenticate(conn, "labuser", "wrong-password-1", "127.0.0.1")
            conn.close()

    def test_sql_injection_username_is_literal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "auth.sqlite"
            conn = _init_db(db)
            authlib.create_user(conn, "labuser", "lab@hum.local", "LabOnly1234")
            with self.assertRaises(PermissionError):
                authlib.authenticate(conn, "labuser' OR 1=1 --", "LabOnly1234", "127.0.0.1")
            self.assertEqual(authlib.user_count(conn), 1)
            conn.close()

    def test_init_cli_seed_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "auth.sqlite"
            init = subprocess.run(
                [sys.executable, str(TOOLS / "init_auth_db.py"), "--database", str(db), "init"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(init.returncode, 0, init.stderr)
            seed = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS / "init_auth_db.py"),
                    "--database",
                    str(db),
                    "seed",
                    "--password",
                    "LabOnly1234",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(seed.returncode, 0, seed.stderr)
            self.assertIn("seeded user: labuser", seed.stdout)
            status = subprocess.run(
                [sys.executable, str(TOOLS / "init_auth_db.py"), "--database", str(db), "status"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("users=1", status.stdout)


class TestLoginServer(unittest.TestCase):
    def test_register_login_dashboard_and_session_xml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "auth.sqlite"
            proc = subprocess.Popen(
                [
                    sys.executable,
                    str(TOOLS / "login_server.py"),
                    "--database",
                    str(db),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8765",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                self._wait_for_server("http://127.0.0.1:8765/")
                jar = http.cookiejar.CookieJar()
                opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

                login_page = opener.open("http://127.0.0.1:8765/register").read().decode("utf-8")
                csrf = self._csrf(login_page)
                body = urllib.parse.urlencode(
                    {
                        "csrf": csrf,
                        "username": "webuser",
                        "email": "webuser@hum.local",
                        "password": "WebPass1234",
                        "confirm": "WebPass1234",
                    }
                ).encode("utf-8")
                dashboard = opener.open(
                    urllib.request.Request(
                        "http://127.0.0.1:8765/register",
                        data=body,
                        method="POST",
                    )
                ).read().decode("utf-8")
                self.assertIn("Signed in", dashboard)
                self.assertIn("webuser", dashboard)

                session_xml = opener.open("http://127.0.0.1:8765/api/session.xml").read()
                root = ET.fromstring(session_xml)
                self.assertEqual(root.attrib.get("authenticated"), "true")

                opener.open(
                    urllib.request.Request("http://127.0.0.1:8765/logout", data=b"", method="POST")
                )
                anon = opener.open("http://127.0.0.1:8765/api/session.xml").read()
                self.assertIn(b'authenticated="false"', anon)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)

    def _wait_for_server(self, url: str, timeout: float = 8.0) -> None:
        deadline = time.time() + timeout
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                urllib.request.urlopen(url, timeout=0.5)
                return
            except Exception as exc:  # noqa: BLE001 - wait loop
                last_error = exc
                time.sleep(0.1)
        raise AssertionError(f"login server did not start: {last_error}")

    def _csrf(self, html: str) -> str:
        marker = 'name="csrf" value="'
        start = html.index(marker) + len(marker)
        end = html.index('"', start)
        return html[start:end]


if __name__ == "__main__":
    unittest.main()
