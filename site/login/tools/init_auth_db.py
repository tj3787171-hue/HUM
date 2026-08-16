#!/usr/bin/env python3
"""Initialize and inspect the HUM.org lab SQLite login database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import authlib


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create and seed the SQL login database.")
    parser.add_argument(
        "--database",
        default=str(authlib.DEFAULT_DATABASE),
        help="SQLite database path (default: site/login/var/auth.sqlite).",
    )
    parser.add_argument(
        "--schema",
        default=str(authlib.DEFAULT_SCHEMA),
        help="SQL schema file to apply.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Create tables from schema.sql.")
    seed = sub.add_parser("seed", help="Create a local lab user if missing.")
    seed.add_argument("--username", default="labuser")
    seed.add_argument("--email", default="labuser@hum.local")
    seed.add_argument("--password", required=True, help="Lab-only password; not stored in git.")
    seed.add_argument("--display-name", default="Lab User")
    add_user = sub.add_parser("add-user", help="Register one user.")
    add_user.add_argument("--username", required=True)
    add_user.add_argument("--email", required=True)
    add_user.add_argument("--password", required=True)
    add_user.add_argument("--display-name", default="")
    sub.add_parser("status", help="Print user and session counts.")
    return parser.parse_args()


def with_db(database: str, schema: str):
    conn = authlib.open_database(Path(database))
    authlib.apply_schema(conn, Path(schema))
    return conn


def main() -> int:
    args = parse_args()
    conn = with_db(args.database, args.schema)
    try:
        if args.command == "init":
            print(f"schema applied: {args.database}")
            return 0
        if args.command == "seed":
            existing = authlib.get_user_by_username(conn, args.username)
            if existing:
                print(f"seed skipped: {args.username} already exists")
                return 0
            user = authlib.create_user(
                conn,
                args.username,
                args.email,
                args.password,
                args.display_name,
            )
            print(f"seeded user: {user.username}")
            return 0
        if args.command == "add-user":
            user = authlib.create_user(
                conn,
                args.username,
                args.email,
                args.password,
                args.display_name or args.username,
            )
            print(f"created user: {user.username}")
            return 0
        if args.command == "status":
            users = authlib.user_count(conn)
            sessions = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
            print(f"users={users} sessions={sessions} database={args.database}")
            return 0
        print("unknown command", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
