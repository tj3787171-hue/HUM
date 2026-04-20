#!/usr/bin/env python3
"""Create and populate a local project evidence SQLite database.

This tool stores:
- paper/document metadata
- binary evidence references with SHA-256 hashes
- normalized MAC-address-linked devices
- network matrix JSON snapshots + foreign assertions
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sqlite3
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


DEFAULT_DB = "data/project_evidence.db"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def normalize_mac(mac: str) -> str:
    cleaned = "".join(ch for ch in mac.lower() if ch in "0123456789abcdef")
    if len(cleaned) != 12:
        raise ValueError(f"invalid MAC address: {mac!r}")
    return ":".join(cleaned[i : i + 2] for i in range(0, 12, 2))


def mac_to_bytes(mac: str) -> bytes:
    normalized = normalize_mac(mac)
    return bytes(int(part, 16) for part in normalized.split(":"))


def normalize_property_hex(code: str) -> str:
    value = code.lower()
    if not value.startswith("0x"):
        raise ValueError("property code must be in 0x... hex format")
    digits = value[2:]
    if not digits or len(digits) > 16 or any(ch not in "0123456789abcdef" for ch in digits):
        raise ValueError(f"invalid property code: {code!r}")
    return "0x" + digits


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as infile:
        while True:
            chunk = infile.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def extract_database_arg(argv: list[str]) -> tuple[str, list[str]]:
    db_path = DEFAULT_DB
    cleaned: list[str] = []
    idx = 0
    while idx < len(argv):
        arg = argv[idx]
        if arg == "--database":
            if idx + 1 >= len(argv):
                raise ValueError("--database requires a value")
            db_path = argv[idx + 1]
            idx += 2
            continue
        if arg.startswith("--database="):
            db_path = arg.split("=", 1)[1]
            idx += 1
            continue
        cleaned.append(arg)
        idx += 1
    return db_path, cleaned


def ensure_column(conn: sqlite3.Connection, table: str, column: str, column_sql: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    names = {row[1] for row in rows}
    if column not in names:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_sql}")


def _tag_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _first_text(root: ET.Element, tag_name: str) -> str | None:
    for elem in root.iter():
        if _tag_name(elem.tag) == tag_name and elem.text:
            value = elem.text.strip()
            if value:
                return value
    return None


def parse_upnp_rootdesc(xml_text: str) -> dict[str, Any]:
    root = ET.fromstring(xml_text)
    services: list[dict[str, str]] = []
    for elem in root.iter():
        if _tag_name(elem.tag) != "service":
            continue
        service: dict[str, str] = {}
        for child in list(elem):
            name = _tag_name(child.tag)
            text = (child.text or "").strip()
            if text:
                service[name] = text
        if service:
            services.append(service)
    return {
        "friendly_name": _first_text(root, "friendlyName"),
        "manufacturer": _first_text(root, "manufacturer"),
        "model_name": _first_text(root, "modelName"),
        "model_number": _first_text(root, "modelNumber"),
        "udn": _first_text(root, "UDN"),
        "presentation_url": _first_text(root, "presentationURL"),
        "services": services,
    }


def fetch_text_from_url(url: str, timeout: int = 8) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # nosec: B310
        data = response.read()
    return data.decode("utf-8", errors="replace")


def resolve_upnp_input(
    xml_file: str | None,
    xml_url: str | None,
    source_url: str | None,
) -> tuple[str, str]:
    if not xml_file and not xml_url:
        raise ValueError("provide --xml-file or --xml-url")
    if xml_file and xml_url:
        raise ValueError("provide only one of --xml-file or --xml-url")
    if xml_file:
        xml_path = Path(xml_file).expanduser().resolve()
        if not xml_path.exists() or not xml_path.is_file():
            raise FileNotFoundError(f"XML file not found: {xml_path}")
        xml_text = xml_path.read_text(encoding="utf-8", errors="replace")
        resolved_source = source_url or str(xml_path)
        return xml_text, resolved_source
    xml_text = fetch_text_from_url(str(xml_url))
    resolved_source = source_url or str(xml_url)
    return xml_text, resolved_source


def resolve_authors(authors: str | None, author_list: list[str]) -> str | None:
    if authors:
        return authors
    if author_list:
        return ", ".join(author_list)
    return None


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode = WAL;
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS property_dictionary (
            property_hex TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            allowed_max_len INTEGER
        );

        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT,
            mac_bytes BLOB NOT NULL UNIQUE,
            mac_text TEXT NOT NULL UNIQUE,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            ipv6_link_local TEXT,
            gateway_udn TEXT,
            presentation_url TEXT
        );

        CREATE TABLE IF NOT EXISTS paper_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_key TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            authors TEXT,
            summary TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            source_path TEXT,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS evidence_blobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evidence_key TEXT NOT NULL UNIQUE,
            paper_id INTEGER REFERENCES paper_records(id) ON DELETE SET NULL,
            device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL,
            property_hex TEXT NOT NULL REFERENCES property_dictionary(property_hex),
            relation_to_paper TEXT,
            payload_path TEXT,
            payload_sha256 TEXT NOT NULL,
            payload_size_bytes INTEGER,
            captured_at TEXT NOT NULL,
            asserted_by TEXT,
            metadata_json TEXT
        );

        CREATE TABLE IF NOT EXISTS network_matrix_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matrix_key TEXT NOT NULL UNIQUE,
            captured_at TEXT NOT NULL,
            schema_version TEXT,
            network_id TEXT,
            source_path TEXT,
            payload_sha256 TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS gateway_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL,
            source_url TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            manufacturer TEXT,
            model_name TEXT,
            udn TEXT,
            raw_xml_excerpt TEXT,
            asserted_by TEXT,
            details_json TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_evidence_device_id ON evidence_blobs(device_id);
        CREATE INDEX IF NOT EXISTS idx_evidence_paper_id ON evidence_blobs(paper_id);
        CREATE INDEX IF NOT EXISTS idx_evidence_sha ON evidence_blobs(payload_sha256);
        CREATE INDEX IF NOT EXISTS idx_matrix_network_id ON network_matrix_snapshots(network_id);
        """
    )
    ensure_column(conn, "devices", "ipv6_link_local", "TEXT")
    ensure_column(conn, "paper_records", "summary", "TEXT")
    ensure_column(conn, "gateway_metadata", "asserted_by", "TEXT")
    ensure_column(conn, "gateway_metadata", "details_json", "TEXT")


def upsert_default_properties(conn: sqlite3.Connection) -> None:
    defaults = [
        ("0x0101", "identity_evidence", "Identity or attribution evidence", 10_000_000),
        ("0x0102", "network_matrix", "Network matrix JSON artifact", 10_000_000),
        ("0x0103", "paper_attachment", "Paper-related binary attachment", 100_000_000),
        ("0x0104", "gateway_metadata", "Gateway/router metadata capture", 1_000_000),
    ]
    conn.executemany(
        """
        INSERT INTO property_dictionary (property_hex, name, description, allowed_max_len)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(property_hex) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            allowed_max_len = excluded.allowed_max_len
        """,
        defaults,
    )


def upsert_property(
    conn: sqlite3.Connection, code: str, name: str, description: str | None, max_len: int | None
) -> None:
    property_hex = normalize_property_hex(code)
    conn.execute(
        """
        INSERT INTO property_dictionary (property_hex, name, description, allowed_max_len)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(property_hex) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            allowed_max_len = excluded.allowed_max_len
        """,
        (property_hex, name, description, max_len),
    )


def upsert_device(
    conn: sqlite3.Connection,
    mac: str,
    label: str | None,
    ipv6_link_local: str | None = None,
    gateway_udn: str | None = None,
    presentation_url: str | None = None,
) -> int:
    now = utc_now()
    mac_text = normalize_mac(mac)
    mac_raw = mac_to_bytes(mac_text)
    conn.execute(
        """
        INSERT INTO devices (
            label, mac_bytes, mac_text, first_seen, last_seen, ipv6_link_local, gateway_udn, presentation_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(mac_text) DO UPDATE SET
            label = COALESCE(excluded.label, devices.label),
            last_seen = excluded.last_seen,
            ipv6_link_local = COALESCE(excluded.ipv6_link_local, devices.ipv6_link_local),
            gateway_udn = COALESCE(excluded.gateway_udn, devices.gateway_udn),
            presentation_url = COALESCE(excluded.presentation_url, devices.presentation_url)
        """,
        (label, mac_raw, mac_text, now, now, ipv6_link_local, gateway_udn, presentation_url),
    )
    row = conn.execute("SELECT id FROM devices WHERE mac_text = ?", (mac_text,)).fetchone()
    return int(row[0])


def upsert_paper(
    conn: sqlite3.Connection,
    slug: str,
    title: str,
    authors: str | None,
    summary: str | None,
    source_path: str | None,
) -> int:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO paper_records (
            paper_key, title, authors, summary, created_at, updated_at, source_path, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT(paper_key) DO UPDATE SET
            title = excluded.title,
            authors = COALESCE(excluded.authors, paper_records.authors),
            summary = COALESCE(excluded.summary, paper_records.summary),
            updated_at = excluded.updated_at,
            source_path = COALESCE(excluded.source_path, paper_records.source_path)
        """,
        (slug, title, authors, summary, now, now, source_path),
    )
    row = conn.execute("SELECT id FROM paper_records WHERE paper_key = ?", (slug,)).fetchone()
    return int(row[0])


def get_paper_id(conn: sqlite3.Connection, slug: str) -> int:
    row = conn.execute("SELECT id FROM paper_records WHERE paper_key = ?", (slug,)).fetchone()
    if row is None:
        raise ValueError(f"unknown paper slug/key: {slug}")
    return int(row[0])


def property_exists(conn: sqlite3.Connection, property_hex: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM property_dictionary WHERE property_hex = ?",
        (property_hex,),
    ).fetchone()
    return row is not None


def upsert_evidence(
    conn: sqlite3.Connection,
    evidence_key: str,
    property_hex: str,
    payload_path: Path,
    paper_id: int | None,
    device_id: int | None,
    relation: str | None,
    asserted_by: str | None,
    metadata: dict[str, Any] | None,
) -> str:
    code = normalize_property_hex(property_hex)
    if not property_exists(conn, code):
        raise ValueError(f"unknown property code: {code}. Add it with add-property first.")
    sha = sha256_file(payload_path)
    size = payload_path.stat().st_size
    conn.execute(
        """
        INSERT INTO evidence_blobs (
            evidence_key, paper_id, device_id, property_hex, relation_to_paper, payload_path,
            payload_sha256, payload_size_bytes, captured_at, asserted_by, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(evidence_key) DO UPDATE SET
            paper_id = excluded.paper_id,
            device_id = excluded.device_id,
            property_hex = excluded.property_hex,
            relation_to_paper = excluded.relation_to_paper,
            payload_path = excluded.payload_path,
            payload_sha256 = excluded.payload_sha256,
            payload_size_bytes = excluded.payload_size_bytes,
            captured_at = excluded.captured_at,
            asserted_by = excluded.asserted_by,
            metadata_json = excluded.metadata_json
        """,
        (
            evidence_key,
            paper_id,
            device_id,
            code,
            relation,
            str(payload_path.resolve()),
            sha,
            int(size),
            utc_now(),
            asserted_by,
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )
    return sha


def upsert_network_matrix(
    conn: sqlite3.Connection,
    matrix_path: Path,
    matrix_key: str | None,
    source_ref: str | None,
) -> tuple[str, str]:
    payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("network JSON must be an object")
    payload_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    sha = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
    schema_version = str(payload.get("schema_version") or payload.get("version") or "")
    network_id = str(payload.get("network_id") or "")
    key = matrix_key or f"{(network_id or 'network')}-{sha[:12]}"
    src = source_ref or str(matrix_path.resolve())
    conn.execute(
        """
        INSERT INTO network_matrix_snapshots (
            matrix_key, captured_at, schema_version, network_id, source_path, payload_sha256, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(matrix_key) DO UPDATE SET
            captured_at = excluded.captured_at,
            schema_version = excluded.schema_version,
            network_id = excluded.network_id,
            source_path = excluded.source_path,
            payload_sha256 = excluded.payload_sha256,
            payload_json = excluded.payload_json
        """,
        (key, utc_now(), schema_version, network_id, src, sha, payload_text),
    )
    return key, sha


def ingest_gateway_metadata(
    conn: sqlite3.Connection,
    source_url: str,
    xml_text: str,
    device_mac: str | None,
    asserted_by: str | None,
) -> tuple[int, dict[str, Any]]:
    details = parse_upnp_rootdesc(xml_text)
    device_id: int | None = None
    if device_mac:
        device_id = upsert_device(
            conn,
            mac=device_mac,
            label=None,
            gateway_udn=details.get("udn"),
            presentation_url=details.get("presentation_url"),
        )
    excerpt = xml_text[:4000]
    conn.execute(
        """
        INSERT INTO gateway_metadata (
            device_id, source_url, captured_at, manufacturer, model_name, udn,
            raw_xml_excerpt, asserted_by, details_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            device_id,
            source_url,
            utc_now(),
            details.get("manufacturer"),
            details.get("model_name"),
            details.get("udn"),
            excerpt,
            asserted_by,
            json.dumps(details, ensure_ascii=False),
        ),
    )
    row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return int(row_id), details


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage project evidence database.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create schema and default property dictionary.")

    add_property = sub.add_parser("add-property", help="Insert or update property dictionary row.")
    add_property.add_argument("--code", required=True, help="Property hex code (e.g. 0x0101)")
    add_property.add_argument("--name", required=True, help="Property name")
    add_property.add_argument("--description", default=None, help="Optional description")
    add_property.add_argument("--max-len", type=int, default=None, help="Optional allowed payload size")

    add_device = sub.add_parser(
        "upsert-device",
        aliases=["add-device"],
        help="Insert or update a MAC-linked device.",
    )
    add_device.add_argument("--mac", required=True, help="MAC address")
    add_device.add_argument("--label", default=None, help="Human-friendly label")
    add_device.add_argument("--ipv6-link-local", default=None, help="Optional fe80::/64 link-local")
    add_device.add_argument("--gateway-udn", default=None, help="Optional gateway UDN/UUID")
    add_device.add_argument("--presentation-url", default=None, help="Optional presentation URL")

    add_paper = sub.add_parser("add-paper", help="Insert or update a paper record.")
    add_paper.add_argument("--slug", "--paper-key", dest="slug", required=True, help="Stable paper key")
    add_paper.add_argument("--title", required=True, help="Paper title")
    add_paper.add_argument("--author", action="append", default=[], help="Repeatable author entry")
    add_paper.add_argument("--authors", default=None, help="Comma-separated or free-form authors")
    add_paper.add_argument("--summary", default=None, help="Optional summary")
    add_paper.add_argument("--source-path", default=None, help="Optional source path")

    add_evidence = sub.add_parser("add-evidence", help="Insert or update evidence blob metadata.")
    add_evidence.add_argument("--evidence-key", required=True, help="Stable evidence key/id")
    add_evidence.add_argument("--property-hex", required=True, help="Property code from dictionary")
    add_evidence.add_argument(
        "--payload-file",
        "--payload-path",
        "--blob-file",
        dest="payload_file",
        required=True,
        help="Binary/file path",
    )
    add_evidence.add_argument("--paper-slug", "--paper-key", dest="paper_slug", default=None)
    add_evidence.add_argument("--device-mac", "--mac-address", dest="device_mac", default=None)
    add_evidence.add_argument("--relation", default=None, help="supports|contradicts|context")
    add_evidence.add_argument("--asserted-by", default=None, help="Actor asserting this evidence")
    add_evidence.add_argument("--source-kind", default=None, help="Optional source kind")
    add_evidence.add_argument("--source-ref", default=None, help="Optional source reference")
    add_evidence.add_argument("--metadata-json", default="{}", help="JSON object string")

    add_matrix = sub.add_parser(
        "ingest-network",
        aliases=["add-network-matrix"],
        help="Store a network matrix JSON snapshot.",
    )
    add_matrix.add_argument(
        "--network-json",
        "--source-path",
        dest="network_json",
        required=True,
        help="Path to network matrix JSON file",
    )
    add_matrix.add_argument("--matrix-key", default=None, help="Optional stable matrix key")
    add_matrix.add_argument("--source", default=None, help="Optional source reference/path override")

    ingest_upnp = sub.add_parser(
        "ingest-upnp-xml",
        aliases=["ingest-upnp"],
        help="Parse a UPnP rootDesc.xml and store gateway metadata.",
    )
    ingest_upnp.add_argument("--source-url", default=None, help="Source URL label for this capture")
    ingest_upnp.add_argument("--xml-file", default=None, help="Path to rootDesc.xml file")
    ingest_upnp.add_argument("--xml-url", default=None, help="URL to fetch rootDesc.xml")
    ingest_upnp.add_argument("--device-mac", default=None, help="Optional linked gateway device MAC")
    ingest_upnp.add_argument("--asserted-by", default=None, help="Actor recording this capture")

    handoff = sub.add_parser(
        "handoff",
        help="Run network + UPnP + paper + evidence ingestion in one command.",
    )
    handoff.add_argument("--network-json", required=True, help="Path to network matrix JSON file")
    handoff.add_argument("--network-source", default=None, help="Optional source reference for network")
    handoff.add_argument("--matrix-key", default=None, help="Optional stable matrix key")

    handoff.add_argument("--device-mac", default=None, help="Optional device MAC used for UPnP/evidence link")
    handoff.add_argument("--skip-upnp", action="store_true", help="Skip UPnP ingest stage")
    handoff.add_argument("--upnp-xml-file", default=None, help="Path to UPnP rootDesc.xml")
    handoff.add_argument("--upnp-xml-url", default=None, help="URL to fetch UPnP rootDesc.xml")
    handoff.add_argument("--upnp-source-url", default=None, help="Source URL label for UPnP capture")
    handoff.add_argument("--upnp-asserted-by", default=None, help="Actor recording the UPnP capture")

    handoff.add_argument("--paper-slug", required=True, help="Stable paper key/slug")
    handoff.add_argument("--paper-title", required=True, help="Paper title")
    handoff.add_argument("--paper-author", action="append", default=[], help="Repeatable paper author")
    handoff.add_argument("--paper-authors", default=None, help="Comma-separated or free-form authors")
    handoff.add_argument("--paper-summary", default=None, help="Optional paper summary")
    handoff.add_argument("--paper-source-path", default=None, help="Optional paper source path")

    handoff.add_argument("--evidence-key", required=True, help="Stable evidence key/id")
    handoff.add_argument(
        "--evidence-property-hex",
        default="0x0102",
        help="Property code for evidence record (default: 0x0102 network_matrix)",
    )
    handoff.add_argument(
        "--evidence-payload-file",
        default=None,
        help="Evidence payload path (defaults to --network-json)",
    )
    handoff.add_argument(
        "--evidence-relation",
        default="supports",
        help="Relation to paper (default: supports)",
    )
    handoff.add_argument("--evidence-asserted-by", default=None, help="Actor asserting evidence")
    handoff.add_argument(
        "--evidence-source-kind",
        default="handoff",
        help="Metadata source_kind for evidence (default: handoff)",
    )
    handoff.add_argument("--evidence-source-ref", default=None, help="Metadata source_ref for evidence")
    handoff.add_argument("--evidence-metadata-json", default="{}", help="Additional evidence metadata JSON object")
    handoff.add_argument("--dry-run", action="store_true", help="Validate inputs and print planned actions only")

    export_matrix = sub.add_parser("export-network-json", help="Export latest matrix JSON.")
    export_matrix.add_argument("--output", required=True, help="Output JSON file path")
    export_matrix.add_argument("--network-id", default=None, help="Optional network id filter")

    sub.add_parser("export-summary", help="Print JSON summary of key table counts.")
    sub.add_parser("list-devices", help="Print devices as JSON.")

    list_evidence = sub.add_parser("list-evidence", help="Print evidence rows as JSON.")
    list_evidence.add_argument("--limit", type=int, default=100, help="Max rows (default: 100)")

    list_gateway = sub.add_parser(
        "list-gateway-metadata",
        aliases=["list-gateway"],
        help="Print captured gateway metadata rows as JSON.",
    )
    list_gateway.add_argument("--limit", type=int, default=50, help="Max rows (default: 50)")

    return parser.parse_args(argv)


def cmd_export_summary(conn: sqlite3.Connection) -> None:
    counts = {
        "properties": conn.execute("SELECT COUNT(*) FROM property_dictionary").fetchone()[0],
        "devices": conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0],
        "papers": conn.execute("SELECT COUNT(*) FROM paper_records").fetchone()[0],
        "evidence_blobs": conn.execute("SELECT COUNT(*) FROM evidence_blobs").fetchone()[0],
        "network_snapshots": conn.execute("SELECT COUNT(*) FROM network_matrix_snapshots").fetchone()[0],
    }
    latest = conn.execute(
        """
        SELECT matrix_key, network_id, captured_at, payload_sha256
        FROM network_matrix_snapshots
        ORDER BY captured_at DESC
        LIMIT 1
        """
    ).fetchone()
    payload: dict[str, Any] = {"counts": counts}
    if latest:
        payload["latest_network_snapshot"] = {
            "matrix_key": latest[0],
            "network_id": latest[1],
            "captured_at": latest[2],
            "payload_sha256": latest[3],
        }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def cmd_list_devices(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT id, label, mac_text, ipv6_link_local, first_seen, last_seen, gateway_udn, presentation_url
        FROM devices
        ORDER BY id ASC
        """
    ).fetchall()
    payload = [
        {
            "id": row[0],
            "label": row[1],
            "mac_text": row[2],
            "ipv6_link_local": row[3],
            "first_seen": row[4],
            "last_seen": row[5],
            "gateway_udn": row[6],
            "presentation_url": row[7],
        }
        for row in rows
    ]
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def cmd_list_evidence(conn: sqlite3.Connection, limit: int) -> None:
    rows = conn.execute(
        """
        SELECT e.evidence_key, e.property_hex, e.payload_sha256, e.payload_size_bytes,
               e.captured_at, e.asserted_by, p.paper_key, d.mac_text
        FROM evidence_blobs e
        LEFT JOIN paper_records p ON e.paper_id = p.id
        LEFT JOIN devices d ON e.device_id = d.id
        ORDER BY e.captured_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    payload = [
        {
            "evidence_key": row[0],
            "property_hex": row[1],
            "payload_sha256": row[2],
            "payload_size_bytes": row[3],
            "captured_at": row[4],
            "asserted_by": row[5],
            "paper_key": row[6],
            "device_mac": row[7],
        }
        for row in rows
    ]
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def cmd_export_network_json(conn: sqlite3.Connection, output: Path, network_id: str | None) -> None:
    if network_id:
        row = conn.execute(
            """
            SELECT payload_json
            FROM network_matrix_snapshots
            WHERE network_id = ?
            ORDER BY captured_at DESC
            LIMIT 1
            """,
            (network_id,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT payload_json
            FROM network_matrix_snapshots
            ORDER BY captured_at DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        raise ValueError("no network snapshot found")
    ensure_parent(output)
    output.write_text(json.dumps(json.loads(row[0]), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Exported network JSON: {output}")


def cmd_list_gateway_metadata(conn: sqlite3.Connection, limit: int) -> None:
    rows = conn.execute(
        """
        SELECT id, source_url, captured_at, manufacturer, model_name, udn, asserted_by
        FROM gateway_metadata
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    payload = [
        {
            "id": row[0],
            "source_url": row[1],
            "captured_at": row[2],
            "manufacturer": row[3],
            "model_name": row[4],
            "udn": row[5],
            "asserted_by": row[6],
        }
        for row in rows
    ]
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main() -> int:
    db_arg, argv = extract_database_arg(sys.argv[1:])
    args = parse_args(argv)
    db_path = Path(db_arg).expanduser().resolve()

    ensure_parent(db_path)
    conn = sqlite3.connect(db_path)
    try:
        create_schema(conn)
        upsert_default_properties(conn)

        if args.command == "init":
            conn.commit()
            print(f"Initialized database: {db_path}")
            return 0

        if args.command == "add-property":
            upsert_property(conn, args.code, args.name, args.description, args.max_len)
            conn.commit()
            print(f"Property upserted: {normalize_property_hex(args.code)} ({args.name})")
            return 0

        if args.command in {"upsert-device", "add-device"}:
            device_id = upsert_device(
                conn,
                mac=args.mac,
                label=args.label,
                ipv6_link_local=args.ipv6_link_local,
                gateway_udn=args.gateway_udn,
                presentation_url=args.presentation_url,
            )
            conn.commit()
            print(f"Device upserted id={device_id} mac={normalize_mac(args.mac)}")
            return 0

        if args.command == "add-paper":
            authors = args.authors if args.authors else ", ".join(args.author) if args.author else None
            paper_id = upsert_paper(conn, args.slug, args.title, authors, args.summary, args.source_path)
            conn.commit()
            print(f"Paper upserted id={paper_id} slug={args.slug}")
            return 0

        if args.command == "add-evidence":
            payload = Path(args.payload_file).expanduser().resolve()
            if not payload.exists() or not payload.is_file():
                raise FileNotFoundError(f"payload file not found: {payload}")
            paper_id = get_paper_id(conn, args.paper_slug) if args.paper_slug else None
            device_id = upsert_device(conn, mac=args.device_mac, label=None) if args.device_mac else None
            metadata = json.loads(args.metadata_json)
            if not isinstance(metadata, dict):
                raise ValueError("--metadata-json must decode to a JSON object")
            if args.source_kind:
                metadata["source_kind"] = args.source_kind
            if args.source_ref:
                metadata["source_ref"] = args.source_ref
            sha = upsert_evidence(
                conn=conn,
                evidence_key=args.evidence_key,
                property_hex=args.property_hex,
                payload_path=payload,
                paper_id=paper_id,
                device_id=device_id,
                relation=args.relation,
                asserted_by=args.asserted_by,
                metadata=metadata,
            )
            conn.commit()
            print(f"Evidence upserted key={args.evidence_key} sha256={sha}")
            return 0

        if args.command in {"ingest-network", "add-network-matrix"}:
            source = Path(args.network_json).expanduser().resolve()
            if not source.exists() or not source.is_file():
                raise FileNotFoundError(f"network JSON file not found: {source}")
            matrix_key, sha = upsert_network_matrix(conn, source, args.matrix_key, args.source)
            conn.commit()
            print(f"Network snapshot upserted key={matrix_key} sha256={sha}")
            return 0

        if args.command == "handoff":
            network_json = Path(args.network_json).expanduser().resolve()
            if not network_json.exists() or not network_json.is_file():
                raise FileNotFoundError(f"network JSON file not found: {network_json}")

            evidence_payload = (
                Path(args.evidence_payload_file).expanduser().resolve()
                if args.evidence_payload_file
                else network_json
            )
            if not evidence_payload.exists() or not evidence_payload.is_file():
                raise FileNotFoundError(f"evidence payload file not found: {evidence_payload}")

            evidence_metadata = json.loads(args.evidence_metadata_json)
            if not isinstance(evidence_metadata, dict):
                raise ValueError("--evidence-metadata-json must decode to a JSON object")
            if args.evidence_source_kind:
                evidence_metadata["source_kind"] = args.evidence_source_kind
            if args.evidence_source_ref:
                evidence_metadata["source_ref"] = args.evidence_source_ref
            else:
                evidence_metadata.setdefault("source_ref", str(network_json.resolve()))

            upnp_plan: dict[str, Any] | None = None
            upnp_xml_text: str | None = None
            upnp_source_url: str | None = None
            if args.skip_upnp:
                upnp_plan = {"enabled": False}
            else:
                if not args.upnp_xml_file and not args.upnp_xml_url:
                    raise ValueError("provide --upnp-xml-file or --upnp-xml-url unless --skip-upnp is set")
                if args.upnp_xml_file and args.upnp_xml_url:
                    raise ValueError("provide only one of --upnp-xml-file or --upnp-xml-url")

                # Keep dry-run side-effect free by skipping remote URL fetches.
                if args.dry_run and args.upnp_xml_url:
                    upnp_source_url = args.upnp_source_url or str(args.upnp_xml_url)
                    upnp_plan = {
                        "enabled": True,
                        "source_url": upnp_source_url,
                        "note": "UPnP URL fetch skipped in dry-run mode",
                    }
                else:
                    upnp_xml_text, upnp_source_url = resolve_upnp_input(
                        args.upnp_xml_file,
                        args.upnp_xml_url,
                        args.upnp_source_url,
                    )
                    upnp_details = parse_upnp_rootdesc(upnp_xml_text)
                    upnp_plan = {
                        "enabled": True,
                        "source_url": upnp_source_url,
                        "manufacturer": upnp_details.get("manufacturer"),
                        "model_name": upnp_details.get("model_name"),
                        "udn": upnp_details.get("udn"),
                    }

            paper_authors = resolve_authors(args.paper_authors, args.paper_author)

            if args.dry_run:
                plan = {
                    "command": "handoff",
                    "database": str(db_path),
                    "network": {
                        "json": str(network_json),
                        "source": args.network_source or str(network_json),
                        "matrix_key": args.matrix_key,
                    },
                    "upnp": upnp_plan,
                    "paper": {
                        "slug": args.paper_slug,
                        "title": args.paper_title,
                        "authors": paper_authors,
                        "summary": args.paper_summary,
                        "source_path": args.paper_source_path,
                    },
                    "evidence": {
                        "key": args.evidence_key,
                        "property_hex": args.evidence_property_hex,
                        "payload_file": str(evidence_payload),
                        "relation": args.evidence_relation,
                        "asserted_by": args.evidence_asserted_by,
                        "device_mac": args.device_mac,
                        "metadata": evidence_metadata,
                    },
                }
                print(json.dumps(plan, indent=2, ensure_ascii=False))
                return 0

            matrix_key, matrix_sha = upsert_network_matrix(
                conn,
                network_json,
                args.matrix_key,
                args.network_source,
            )

            upnp_row_id: int | None = None
            if not args.skip_upnp and upnp_xml_text is not None and upnp_source_url is not None:
                upnp_row_id, _ = ingest_gateway_metadata(
                    conn=conn,
                    source_url=upnp_source_url,
                    xml_text=upnp_xml_text,
                    device_mac=args.device_mac,
                    asserted_by=args.upnp_asserted_by,
                )

            paper_id = upsert_paper(
                conn=conn,
                slug=args.paper_slug,
                title=args.paper_title,
                authors=paper_authors,
                summary=args.paper_summary,
                source_path=args.paper_source_path,
            )
            device_id = upsert_device(conn, mac=args.device_mac, label=None) if args.device_mac else None
            evidence_sha = upsert_evidence(
                conn=conn,
                evidence_key=args.evidence_key,
                property_hex=args.evidence_property_hex,
                payload_path=evidence_payload,
                paper_id=paper_id,
                device_id=device_id,
                relation=args.evidence_relation,
                asserted_by=args.evidence_asserted_by,
                metadata=evidence_metadata,
            )
            conn.commit()
            summary = {
                "matrix_key": matrix_key,
                "matrix_sha256": matrix_sha,
                "gateway_metadata_id": upnp_row_id,
                "paper_id": paper_id,
                "evidence_key": args.evidence_key,
                "evidence_sha256": evidence_sha,
            }
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            return 0

        if args.command in {"ingest-upnp-xml", "ingest-upnp"}:
            xml_text, source_url = resolve_upnp_input(args.xml_file, args.xml_url, args.source_url)
        if args.command in {"ingest-upnp-xml", "ingest-upnp"}:
            if not args.xml_file and not args.xml_url:
                raise ValueError("provide --xml-file or --xml-url")
            if args.xml_file and args.xml_url:
                raise ValueError("provide only one of --xml-file or --xml-url")
            if args.xml_file:
                xml_path = Path(args.xml_file).expanduser().resolve()
                if not xml_path.exists() or not xml_path.is_file():
                    raise FileNotFoundError(f"XML file not found: {xml_path}")
                xml_text = xml_path.read_text(encoding="utf-8", errors="replace")
                source_url = args.source_url or str(xml_path)
            else:
                xml_text = fetch_text_from_url(args.xml_url)
                source_url = args.source_url or args.xml_url
            row_id, details = ingest_gateway_metadata(
                conn=conn,
                source_url=source_url,
                xml_text=xml_text,
                device_mac=args.device_mac,
                asserted_by=args.asserted_by,
            )
            conn.commit()
            print(
                f"Gateway metadata captured id={row_id} "
                f"manufacturer={details.get('manufacturer')!r} model={details.get('model_name')!r}"
            )
            return 0

        if args.command == "export-network-json":
            output = Path(args.output).expanduser().resolve()
            cmd_export_network_json(conn, output, args.network_id)
            return 0

        if args.command == "export-summary":
            cmd_export_summary(conn)
            return 0

        if args.command == "list-devices":
            cmd_list_devices(conn)
            return 0

        if args.command == "list-evidence":
            cmd_list_evidence(conn, args.limit)
            return 0

        if args.command in {"list-gateway-metadata", "list-gateway"}:
            cmd_list_gateway_metadata(conn, args.limit)
            return 0

        raise ValueError(f"unknown command: {args.command}")
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
