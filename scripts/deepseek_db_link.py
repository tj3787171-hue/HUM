#!/usr/bin/env python3
"""Link DeepSeek backup exports into a local SQLite database.

This tool is intentionally format-tolerant so it can index arbitrary backup
folders while extracting chat-like data from common JSON/JSONL structures.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MESSAGE_ROLE_KEYS = ("role", "sender", "from", "author")
MESSAGE_CONTENT_KEYS = ("content", "text", "message", "body")
CONVERSATION_CONTAINER_KEYS = ("messages", "conversation", "chat", "thread")


@dataclass
class ImportStats:
    files_indexed: int = 0
    conversations_imported: int = 0
    messages_imported: int = 0
    json_files_parsed: int = 0
    jsonl_files_parsed: int = 0
    parse_errors: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Index a DeepSeek backup directory into SQLite.",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to DeepSeek backup/export directory (mounted SSD path is fine).",
    )
    parser.add_argument(
        "--database",
        default="data/deepseek_backup.db",
        help="SQLite database file path (default: data/deepseek_backup.db).",
    )
    parser.add_argument(
        "--compute-sha256",
        action="store_true",
        help="Compute SHA256 for each file (slower on large backups).",
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden files/directories while scanning.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def compute_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as infile:
        while True:
            chunk = infile.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode = WAL;
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS source_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            relative_path TEXT NOT NULL UNIQUE,
            absolute_path TEXT NOT NULL,
            extension TEXT,
            size_bytes INTEGER NOT NULL,
            mtime_epoch REAL NOT NULL,
            sha256 TEXT,
            indexed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_key TEXT NOT NULL UNIQUE,
            title TEXT,
            source_file_id INTEGER NOT NULL REFERENCES source_files(id) ON DELETE CASCADE,
            raw_json TEXT
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            message_index INTEGER NOT NULL,
            role TEXT,
            content TEXT,
            timestamp TEXT,
            raw_json TEXT,
            UNIQUE(conversation_id, message_index)
        );

        CREATE INDEX IF NOT EXISTS idx_messages_conversation_id
            ON messages(conversation_id);
        CREATE INDEX IF NOT EXISTS idx_conversations_source_file_id
            ON conversations(source_file_id);
        """
    )


def is_hidden_path(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts if part not in (".", ".."))


def iter_files(source_root: Path, include_hidden: bool) -> list[Path]:
    files: list[Path] = []
    for root, dirnames, filenames in os.walk(source_root):
        root_path = Path(root)
        if not include_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for filename in filenames:
            candidate = root_path / filename
            if not include_hidden and is_hidden_path(candidate.relative_to(source_root)):
                continue
            if candidate.is_file():
                files.append(candidate)
    files.sort()
    return files


def upsert_source_file(
    conn: sqlite3.Connection,
    source_root: Path,
    file_path: Path,
    sha256: str | None,
) -> int:
    stat = file_path.stat()
    relative_path = file_path.relative_to(source_root).as_posix()
    extension = file_path.suffix.lower() or None
    indexed_at = utc_now()

    conn.execute(
        """
        INSERT INTO source_files (
            relative_path, absolute_path, extension, size_bytes, mtime_epoch, sha256, indexed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(relative_path) DO UPDATE SET
            absolute_path = excluded.absolute_path,
            extension = excluded.extension,
            size_bytes = excluded.size_bytes,
            mtime_epoch = excluded.mtime_epoch,
            sha256 = excluded.sha256,
            indexed_at = excluded.indexed_at
        """,
        (
            relative_path,
            str(file_path.resolve()),
            extension,
            int(stat.st_size),
            float(stat.st_mtime),
            sha256,
            indexed_at,
        ),
    )
    source_file_id = conn.execute(
        "SELECT id FROM source_files WHERE relative_path = ?",
        (relative_path,),
    ).fetchone()[0]
    return int(source_file_id)


def clear_file_import_data(conn: sqlite3.Connection, source_file_id: int) -> None:
    conversation_ids = [
        row[0]
        for row in conn.execute(
            "SELECT id FROM conversations WHERE source_file_id = ?",
            (source_file_id,),
        ).fetchall()
    ]
    for conversation_id in conversation_ids:
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
    conn.execute("DELETE FROM conversations WHERE source_file_id = ?", (source_file_id,))


def message_like(record: Any) -> bool:
    if not isinstance(record, dict):
        return False
    has_role = any(key in record for key in MESSAGE_ROLE_KEYS)
    has_content = any(key in record for key in MESSAGE_CONTENT_KEYS)
    return has_role and has_content


def normalize_message(record: dict[str, Any]) -> dict[str, Any]:
    role = next((record.get(key) for key in MESSAGE_ROLE_KEYS if key in record), None)
    content = next((record.get(key) for key in MESSAGE_CONTENT_KEYS if key in record), None)
    timestamp = (
        record.get("timestamp")
        or record.get("created_at")
        or record.get("time")
        or record.get("ts")
    )
    if isinstance(content, (dict, list)):
        content = json.dumps(content, ensure_ascii=False)
    elif content is not None:
        content = str(content)
    return {
        "role": None if role is None else str(role),
        "content": content,
        "timestamp": None if timestamp is None else str(timestamp),
        "raw_json": json.dumps(record, ensure_ascii=False),
    }


def find_conversations(payload: Any, base_key: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    def add_conversation(conv_key: str, node: Any, messages: list[Any], title: Any = None) -> None:
        if conv_key in seen_keys:
            return
        normalized_messages = [normalize_message(m) for m in messages if message_like(m)]
        if not normalized_messages:
            return
        seen_keys.add(conv_key)
        results.append(
            {
                "conversation_key": conv_key,
                "title": None if title is None else str(title),
                "messages": normalized_messages,
                "raw_json": json.dumps(node, ensure_ascii=False),
            }
        )

    def walk(node: Any, path_parts: list[str]) -> None:
        path_key = ".".join(path_parts) if path_parts else "root"

        if isinstance(node, dict):
            handled_message_keys: set[str] = set()
            # Direct message arrays under known keys.
            for key in CONVERSATION_CONTAINER_KEYS:
                maybe_messages = node.get(key)
                if isinstance(maybe_messages, list) and any(message_like(item) for item in maybe_messages):
                    conv_id = (
                        node.get("id")
                        or node.get("conversation_id")
                        or node.get("chat_id")
                        or f"{base_key}::{path_key}.{key}"
                    )
                    add_conversation(str(conv_id), node, maybe_messages, node.get("title") or node.get("name"))
                    handled_message_keys.add(key)

            for key, value in node.items():
                if key in handled_message_keys:
                    # Avoid duplicate extraction from the same message list.
                    continue
                walk(value, [*path_parts, str(key)])
            return

        if isinstance(node, list):
            if node and all(message_like(item) for item in node):
                add_conversation(f"{base_key}::{path_key}", node, node)
            else:
                for idx, item in enumerate(node):
                    walk(item, [*path_parts, str(idx)])

    walk(payload, [])
    return results


def import_json_file(
    conn: sqlite3.Connection,
    file_path: Path,
    source_root: Path,
    source_file_id: int,
    stats: ImportStats,
) -> None:
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        stats.parse_errors += 1
        return

    relative_key = file_path.relative_to(source_root).as_posix()
    conversations = find_conversations(payload, relative_key)
    for conversation in conversations:
        conn.execute(
            """
            INSERT INTO conversations (conversation_key, title, source_file_id, raw_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                conversation["conversation_key"],
                conversation["title"],
                source_file_id,
                conversation["raw_json"],
            ),
        )
        conversation_id = conn.execute(
            "SELECT id FROM conversations WHERE conversation_key = ?",
            (conversation["conversation_key"],),
        ).fetchone()[0]

        for index, message in enumerate(conversation["messages"]):
            conn.execute(
                """
                INSERT INTO messages (
                    conversation_id, message_index, role, content, timestamp, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(conversation_id),
                    index,
                    message["role"],
                    message["content"],
                    message["timestamp"],
                    message["raw_json"],
                ),
            )
            stats.messages_imported += 1
        stats.conversations_imported += 1
    stats.json_files_parsed += 1


def import_jsonl_file(
    conn: sqlite3.Connection,
    file_path: Path,
    source_root: Path,
    source_file_id: int,
    stats: ImportStats,
) -> None:
    grouped: dict[str, list[dict[str, Any]]] = {}

    try:
        with file_path.open("r", encoding="utf-8") as infile:
            for line_number, line in enumerate(infile, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    stats.parse_errors += 1
                    continue
                if not isinstance(payload, dict):
                    continue
                if not message_like(payload):
                    # Accept lines where message is nested.
                    nested = payload.get("message")
                    if not isinstance(nested, dict) or not message_like(nested):
                        continue
                    payload = nested

                relative = file_path.relative_to(source_root).as_posix()
                conversation_key = (
                    payload.get("conversation_id")
                    or payload.get("chat_id")
                    or payload.get("thread_id")
                    or f"{relative}::jsonl"
                )
                grouped.setdefault(str(conversation_key), []).append(payload)
    except Exception:
        stats.parse_errors += 1
        return

    for conversation_key, messages in grouped.items():
        conn.execute(
            """
            INSERT INTO conversations (conversation_key, title, source_file_id, raw_json)
            VALUES (?, ?, ?, ?)
            """,
            (conversation_key, None, source_file_id, None),
        )
        conversation_id = conn.execute(
            "SELECT id FROM conversations WHERE conversation_key = ?",
            (conversation_key,),
        ).fetchone()[0]
        for index, message in enumerate(messages):
            normalized = normalize_message(message)
            conn.execute(
                """
                INSERT INTO messages (
                    conversation_id, message_index, role, content, timestamp, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(conversation_id),
                    index,
                    normalized["role"],
                    normalized["content"],
                    normalized["timestamp"],
                    normalized["raw_json"],
                ),
            )
            stats.messages_imported += 1
        stats.conversations_imported += 1
    stats.jsonl_files_parsed += 1


def import_file_content(
    conn: sqlite3.Connection,
    file_path: Path,
    source_root: Path,
    source_file_id: int,
    stats: ImportStats,
) -> None:
    suffix = file_path.suffix.lower()
    if suffix == ".json":
        import_json_file(conn, file_path, source_root, source_file_id, stats)
    elif suffix == ".jsonl":
        import_jsonl_file(conn, file_path, source_root, source_file_id, stats)


def run_import(
    source_root: Path,
    db_path: Path,
    compute_hash: bool,
    include_hidden: bool,
) -> ImportStats:
    stats = ImportStats()
    ensure_parent_dir(db_path)

    conn = sqlite3.connect(db_path)
    try:
        create_schema(conn)
        files = iter_files(source_root, include_hidden=include_hidden)
        for file_path in files:
            file_sha = compute_sha256(file_path) if compute_hash else None
            source_file_id = upsert_source_file(conn, source_root, file_path, file_sha)
            clear_file_import_data(conn, source_file_id)
            import_file_content(conn, file_path, source_root, source_file_id, stats)
            stats.files_indexed += 1
        conn.commit()
    finally:
        conn.close()
    return stats


def main() -> int:
    args = parse_args()
    source_root = Path(args.source).expanduser().resolve()
    db_path = Path(args.database).expanduser().resolve()

    if not source_root.exists():
        print(f"Error: source path does not exist: {source_root}")
        return 1
    if not source_root.is_dir():
        print(f"Error: source path is not a directory: {source_root}")
        return 1

    stats = run_import(
        source_root=source_root,
        db_path=db_path,
        compute_hash=args.compute_sha256,
        include_hidden=args.include_hidden,
    )

    print(f"Source:   {source_root}")
    print(f"Database: {db_path}")
    print("Import complete:")
    print(f"  files indexed:          {stats.files_indexed}")
    print(f"  json files parsed:      {stats.json_files_parsed}")
    print(f"  jsonl files parsed:     {stats.jsonl_files_parsed}")
    print(f"  conversations imported: {stats.conversations_imported}")
    print(f"  messages imported:      {stats.messages_imported}")
    print(f"  parse errors:           {stats.parse_errors}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
