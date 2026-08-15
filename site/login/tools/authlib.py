#!/usr/bin/env python3
"""Shared SQLite login helpers for the HUM.org lab login site.

Password hashes use a portable PBKDF2-SHA256 string so PHP and Python
can verify the same rows. Never log or print password hashes.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

LOGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = LOGIN_ROOT / "sql" / "schema.sql"
DEFAULT_CONFIG = LOGIN_ROOT / "xml" / "auth-config.xml"
DEFAULT_DATABASE = LOGIN_ROOT / "var" / "auth.sqlite"

PASSWORD_PREFIX = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 210000
DEFAULT_SALT_BYTES = 16
DEFAULT_HASH_BYTES = 32
DEFAULT_MIN_PASSWORD = 10
DEFAULT_SESSION_TTL = 43200
DEFAULT_THROTTLE_FAILURES = 5
DEFAULT_THROTTLE_WINDOW = 900
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,31}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GENERIC_AUTH_ERROR = "Invalid username or password."
GENERIC_THROTTLE_ERROR = "Too many failed sign-in attempts. Try again later."


@dataclass(frozen=True)
class AuthConfig:
    site_name: str = "HUM.org Lab Login"
    database_path: Path = DEFAULT_DATABASE
    cookie_name: str = "hum_session"
    session_ttl: int = DEFAULT_SESSION_TTL
    iterations: int = DEFAULT_ITERATIONS
    min_password: int = DEFAULT_MIN_PASSWORD
    salt_bytes: int = DEFAULT_SALT_BYTES
    hash_bytes: int = DEFAULT_HASH_BYTES
    max_failures: int = DEFAULT_THROTTLE_FAILURES
    window_seconds: int = DEFAULT_THROTTLE_WINDOW
    bind_host: str = "127.0.0.1"
    bind_port: int = 8088


@dataclass(frozen=True)
class User:
    id: int
    username: str
    email: str
    display_name: str
    created_at: str
    last_login_at: str | None
    is_active: bool


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_stamp(moment: datetime | None = None) -> str:
    value = moment or utc_now()
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _local_tag(tag: str) -> str:
    return tag.split("}", 1)[-1]


def load_config(path: Path | None = None) -> AuthConfig:
    config_path = path or DEFAULT_CONFIG
    values: dict[str, Any] = {}
    if config_path.is_file():
        root = ET.parse(config_path).getroot()
        for child in root:
            name = _local_tag(child.tag)
            if name == "site":
                values["site_name"] = child.attrib.get("name", AuthConfig.site_name)
            elif name == "database":
                raw = child.attrib.get("path", str(DEFAULT_DATABASE))
                db_path = Path(raw)
                values["database_path"] = db_path if db_path.is_absolute() else LOGIN_ROOT / db_path
            elif name == "session":
                values["cookie_name"] = child.attrib.get("cookieName", AuthConfig.cookie_name)
                values["session_ttl"] = int(child.attrib.get("ttlSeconds", DEFAULT_SESSION_TTL))
            elif name == "password":
                values["iterations"] = int(child.attrib.get("iterations", DEFAULT_ITERATIONS))
                values["min_password"] = int(child.attrib.get("minLength", DEFAULT_MIN_PASSWORD))
                values["salt_bytes"] = int(child.attrib.get("saltBytes", DEFAULT_SALT_BYTES))
                values["hash_bytes"] = int(child.attrib.get("hashBytes", DEFAULT_HASH_BYTES))
            elif name == "throttle":
                values["max_failures"] = int(child.attrib.get("maxFailures", DEFAULT_THROTTLE_FAILURES))
                values["window_seconds"] = int(child.attrib.get("windowSeconds", DEFAULT_THROTTLE_WINDOW))
            elif name == "bind":
                values["bind_host"] = child.attrib.get("host", AuthConfig.bind_host)
                values["bind_port"] = int(child.attrib.get("port", AuthConfig.bind_port))
    return AuthConfig(**values)


def hash_password(password: str, config: AuthConfig | None = None) -> str:
    settings = config or AuthConfig()
    salt = os.urandom(settings.salt_bytes)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        settings.iterations,
        dklen=settings.hash_bytes,
    )
    return f"{PASSWORD_PREFIX}${settings.iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != PASSWORD_PREFIX:
        return False
    try:
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected = bytes.fromhex(parts[3])
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=len(expected),
    )
    return hmac.compare_digest(actual, expected)


def validate_username(username: str) -> str | None:
    if not USERNAME_RE.fullmatch(username):
        return "Username must start with a letter and be 3-32 letters, digits, or underscores."
    return None


def validate_email(email: str) -> str | None:
    if len(email) > 254 or not EMAIL_RE.fullmatch(email):
        return "Enter a valid email address."
    return None


def validate_password(password: str, config: AuthConfig | None = None) -> str | None:
    settings = config or AuthConfig()
    if len(password) < settings.min_password:
        return f"Password must be at least {settings.min_password} characters."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must include at least one letter and one number."
    return None


def open_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def apply_schema(conn: sqlite3.Connection, schema_path: Path | None = None) -> None:
    sql = (schema_path or DEFAULT_SCHEMA).read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=int(row["id"]),
        username=str(row["username"]),
        email=str(row["email"]),
        display_name=str(row["display_name"] or row["username"]),
        created_at=str(row["created_at"]),
        last_login_at=row["last_login_at"],
        is_active=bool(row["is_active"]),
    )


def get_user_by_username(conn: sqlite3.Connection, username: str) -> User | None:
    row = conn.execute(
        "SELECT id, username, email, display_name, created_at, last_login_at, is_active "
        "FROM users WHERE username = ? AND is_active = 1",
        (username,),
    ).fetchone()
    return _row_to_user(row) if row else None


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> User | None:
    row = conn.execute(
        "SELECT id, username, email, display_name, created_at, last_login_at, is_active "
        "FROM users WHERE id = ? AND is_active = 1",
        (user_id,),
    ).fetchone()
    return _row_to_user(row) if row else None


def create_user(
    conn: sqlite3.Connection,
    username: str,
    email: str,
    password: str,
    display_name: str | None = None,
    config: AuthConfig | None = None,
) -> User:
    settings = config or AuthConfig()
    username_error = validate_username(username)
    if username_error:
        raise ValueError(username_error)
    email_error = validate_email(email)
    if email_error:
        raise ValueError(email_error)
    password_error = validate_password(password, settings)
    if password_error:
        raise ValueError(password_error)
    existing = conn.execute(
        "SELECT username, email FROM users WHERE username = ? OR email = ?",
        (username, email),
    ).fetchone()
    if existing:
        raise ValueError("That username or email is already registered.")
    conn.execute(
        "INSERT INTO users (username, email, password_hash, display_name) VALUES (?, ?, ?, ?)",
        (username, email, hash_password(password, settings), display_name or username),
    )
    conn.commit()
    user = get_user_by_username(conn, username)
    if user is None:
        raise RuntimeError("User insert succeeded but the row could not be read.")
    return user


def count_recent_failures(
    conn: sqlite3.Connection,
    username: str,
    ip_address: str,
    window_seconds: int,
) -> int:
    cutoff = utc_stamp(utc_now() - timedelta(seconds=window_seconds))
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM login_attempts "
        "WHERE username = ? AND ip_address = ? AND success = 0 AND created_at >= ?",
        (username, ip_address, cutoff),
    ).fetchone()
    return int(row["n"]) if row else 0


def record_attempt(
    conn: sqlite3.Connection,
    username: str,
    ip_address: str,
    success: bool,
) -> None:
    conn.execute(
        "INSERT INTO login_attempts (username, ip_address, success) VALUES (?, ?, ?)",
        (username, ip_address, 1 if success else 0),
    )
    conn.commit()


def authenticate(
    conn: sqlite3.Connection,
    username: str,
    password: str,
    ip_address: str,
    config: AuthConfig | None = None,
) -> User:
    settings = config or AuthConfig()
    if count_recent_failures(conn, username, ip_address, settings.window_seconds) >= settings.max_failures:
        raise PermissionError(GENERIC_THROTTLE_ERROR)
    row = conn.execute(
        "SELECT id, username, email, password_hash, display_name, created_at, last_login_at, is_active "
        "FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    ok = bool(row) and bool(row["is_active"]) and verify_password(password, str(row["password_hash"]))
    record_attempt(conn, username, ip_address, ok)
    if not ok:
        raise PermissionError(GENERIC_AUTH_ERROR)
    conn.execute(
        "UPDATE users SET last_login_at = ? WHERE id = ?",
        (utc_stamp(), int(row["id"])),
    )
    conn.commit()
    user = get_user_by_id(conn, int(row["id"]))
    if user is None:
        raise PermissionError(GENERIC_AUTH_ERROR)
    return user


def create_session(
    conn: sqlite3.Connection,
    user_id: int,
    ip_address: str,
    user_agent: str,
    config: AuthConfig | None = None,
) -> str:
    settings = config or AuthConfig()
    token = secrets.token_hex(32)
    expires = utc_stamp(utc_now() + timedelta(seconds=settings.session_ttl))
    conn.execute(
        "INSERT INTO sessions (id, user_id, expires_at, ip_address, user_agent) VALUES (?, ?, ?, ?, ?)",
        (token, user_id, expires, ip_address, user_agent[:300]),
    )
    conn.commit()
    return token


def load_session_user(conn: sqlite3.Connection, token: str | None) -> User | None:
    if not token:
        return None
    row = conn.execute(
        "SELECT user_id, expires_at FROM sessions WHERE id = ?",
        (token,),
    ).fetchone()
    if row is None:
        return None
    if str(row["expires_at"]) < utc_stamp():
        conn.execute("DELETE FROM sessions WHERE id = ?", (token,))
        conn.commit()
        return None
    return get_user_by_id(conn, int(row["user_id"]))


def destroy_session(conn: sqlite3.Connection, token: str | None) -> None:
    if not token:
        return
    conn.execute("DELETE FROM sessions WHERE id = ?", (token,))
    conn.commit()


def issue_csrf(conn: sqlite3.Connection, ttl_seconds: int = 7200) -> str:
    token = secrets.token_hex(32)
    conn.execute(
        "INSERT INTO csrf_tokens (token, expires_at) VALUES (?, ?)",
        (token, utc_stamp(utc_now() + timedelta(seconds=ttl_seconds))),
    )
    conn.commit()
    return token


def consume_csrf(conn: sqlite3.Connection, token: str | None) -> bool:
    if not token:
        return False
    row = conn.execute(
        "SELECT expires_at FROM csrf_tokens WHERE token = ?",
        (token,),
    ).fetchone()
    conn.execute("DELETE FROM csrf_tokens WHERE token = ?", (token,))
    conn.commit()
    if row is None:
        return False
    return str(row["expires_at"]) >= utc_stamp()


def update_display_name(conn: sqlite3.Connection, user_id: int, display_name: str) -> None:
    name = display_name.strip()
    if not name or len(name) > 80:
        raise ValueError("Display name must be 1-80 characters.")
    conn.execute("UPDATE users SET display_name = ? WHERE id = ?", (name, user_id))
    conn.commit()


def change_password(
    conn: sqlite3.Connection,
    user_id: int,
    current_password: str,
    new_password: str,
    config: AuthConfig | None = None,
) -> None:
    settings = config or AuthConfig()
    row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None or not verify_password(current_password, str(row["password_hash"])):
        raise PermissionError("Current password is incorrect.")
    password_error = validate_password(new_password, settings)
    if password_error:
        raise ValueError(password_error)
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(new_password, settings), user_id),
    )
    conn.commit()


def user_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    return int(row["n"]) if row else 0
