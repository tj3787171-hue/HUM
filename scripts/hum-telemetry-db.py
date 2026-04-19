#!/usr/bin/env python3
"""Collect HUM network topology telemetry into a local SQLite database.

Parses structured JSON snapshots produced by ``hum-dev-netns.sh collect``
and stores them as typed events in three tables that map directly to the
$OBJECT / $FLOAT / $SHAPE model:

  hops        – per-interface identity records ($OBJECT)
  counters    – per-interface RX/TX packet counts ($FLOAT)
  snapshots   – whole-topology state captures ($SHAPE)

Every record belongs to a ``snapshot_id`` so you can reconstruct exact
point-in-time network state.

Usage (standalone):
    echo '<json>' | python3 scripts/hum-telemetry-db.py ingest --database data/telemetry.db
    python3 scripts/hum-telemetry-db.py ingest --database data/telemetry.db --file snapshot.json
    python3 scripts/hum-telemetry-db.py query  --database data/telemetry.db [--last N]
    python3 scripts/hum-telemetry-db.py export --database data/telemetry.db [--last N] [--format json|csv]

Usage (integrated with hum-dev-netns.sh):
    sudo bash scripts/hum-dev-netns.sh collect | \\
        python3 scripts/hum-telemetry-db.py ingest --database data/telemetry.db

Zero external dependencies — stdlib only.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at     TEXT    NOT NULL,
    peer_chain      INTEGER NOT NULL DEFAULT 0,
    peer_ready      INTEGER NOT NULL DEFAULT 0,
    chain_ready     INTEGER NOT NULL DEFAULT 0,
    topology_json   TEXT,
    raw_json        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS hops (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id     INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    role            TEXT    NOT NULL,
    namespace       TEXT,
    interface       TEXT    NOT NULL,
    mac             TEXT,
    smac64          TEXT,
    ipv4_cidr       TEXT,
    ipv6_cidr       TEXT,
    link_up         INTEGER,
    UNIQUE(snapshot_id, role)
);

CREATE TABLE IF NOT EXISTS counters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id     INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    role            TEXT    NOT NULL,
    rx_packets      INTEGER,
    tx_packets      INTEGER,
    rx_bytes        INTEGER,
    tx_bytes        INTEGER,
    UNIQUE(snapshot_id, role)
);

CREATE TABLE IF NOT EXISTS routes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id     INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    namespace       TEXT    NOT NULL,
    family          TEXT    NOT NULL DEFAULT 'inet',
    destination     TEXT    NOT NULL,
    gateway         TEXT,
    device          TEXT,
    UNIQUE(snapshot_id, namespace, family, destination)
);

CREATE INDEX IF NOT EXISTS idx_hops_snapshot   ON hops(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_counters_snap   ON counters(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_routes_snap     ON routes(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_time  ON snapshots(captured_at);
"""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def ingest_snapshot(conn: sqlite3.Connection, data: dict[str, Any]) -> int:
    """Insert one topology snapshot and return its snapshot_id."""

    captured_at = data.get("captured_at", utc_now())
    peer_chain = 1 if data.get("peer_chain_enabled", False) else 0
    peer_ready = 1 if data.get("peer_recv_ready", False) else 0
    chain_ready = 1 if data.get("peer_chain_recv_ready", False) else 0

    topo = data.get("topology")
    topo_json = json.dumps(topo, ensure_ascii=False) if topo else None
    raw_json = json.dumps(data, ensure_ascii=False)

    conn.execute(
        """INSERT INTO snapshots
           (captured_at, peer_chain, peer_ready, chain_ready, topology_json, raw_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (captured_at, peer_chain, peer_ready, chain_ready, topo_json, raw_json),
    )
    snap_id: int = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    for hop in data.get("hops", []):
        conn.execute(
            """INSERT OR REPLACE INTO hops
               (snapshot_id, role, namespace, interface, mac, smac64,
                ipv4_cidr, ipv6_cidr, link_up)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snap_id,
                hop["role"],
                hop.get("namespace"),
                hop["interface"],
                hop.get("mac"),
                hop.get("smac64"),
                hop.get("ipv4_cidr"),
                hop.get("ipv6_cidr"),
                1 if hop.get("link_up") else 0,
            ),
        )

    for ctr in data.get("counters", []):
        conn.execute(
            """INSERT OR REPLACE INTO counters
               (snapshot_id, role, rx_packets, tx_packets, rx_bytes, tx_bytes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                snap_id,
                ctr["role"],
                ctr.get("rx_packets"),
                ctr.get("tx_packets"),
                ctr.get("rx_bytes"),
                ctr.get("tx_bytes"),
            ),
        )

    for rt in data.get("routes", []):
        conn.execute(
            """INSERT OR REPLACE INTO routes
               (snapshot_id, namespace, family, destination, gateway, device)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                snap_id,
                rt["namespace"],
                rt.get("family", "inet"),
                rt["destination"],
                rt.get("gateway"),
                rt.get("device"),
            ),
        )

    return snap_id


def cmd_ingest(args: argparse.Namespace) -> int:
    db_path = Path(args.database).expanduser().resolve()
    ensure_parent_dir(db_path)

    if args.file:
        payload = Path(args.file).read_text(encoding="utf-8")
    else:
        payload = sys.stdin.read()

    if not payload.strip():
        print("Error: empty input", file=sys.stderr)
        return 1

    data = json.loads(payload)

    conn = sqlite3.connect(db_path)
    try:
        create_schema(conn)
        snap_id = ingest_snapshot(conn, data)
        conn.commit()
        print(f"Ingested snapshot {snap_id} into {db_path}")
    finally:
        conn.close()

    return 0


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

def cmd_query(args: argparse.Namespace) -> int:
    db_path = Path(args.database).expanduser().resolve()
    if not db_path.exists():
        print(f"Error: database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        limit = args.last or 5

        print(f"=== Last {limit} snapshots ===\n")
        rows = conn.execute(
            "SELECT * FROM snapshots ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

        for row in reversed(rows):
            sid = row["id"]
            print(f"[snapshot {sid}]  {row['captured_at']}  "
                  f"chain={'on' if row['peer_chain'] else 'off'}  "
                  f"ready={row['peer_ready']}/{row['chain_ready']}")

            hops = conn.execute(
                "SELECT role, interface, smac64, link_up FROM hops "
                "WHERE snapshot_id = ? ORDER BY id", (sid,)
            ).fetchall()
            for h in hops:
                up_str = "UP" if h["link_up"] else "DOWN"
                print(f"  hop  {h['role']:16s}  {h['interface']:20s}  "
                      f"smac64={h['smac64'] or '?':16s}  {up_str}")

            ctrs = conn.execute(
                "SELECT role, rx_packets, tx_packets FROM counters "
                "WHERE snapshot_id = ? ORDER BY id", (sid,)
            ).fetchall()
            for c in ctrs:
                print(f"  ctr  {c['role']:16s}  "
                      f"rx={c['rx_packets'] or 0}  tx={c['tx_packets'] or 0}")

            routes = conn.execute(
                "SELECT namespace, family, destination, gateway, device FROM routes "
                "WHERE snapshot_id = ? ORDER BY id", (sid,)
            ).fetchall()
            for r in routes:
                gw = f"via {r['gateway']}" if r["gateway"] else "direct"
                print(f"  rte  {r['namespace']:16s}  {r['family']:5s}  "
                      f"{r['destination']:20s}  {gw}  dev {r['device'] or '?'}")
            print()
    finally:
        conn.close()

    return 0


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def cmd_export(args: argparse.Namespace) -> int:
    db_path = Path(args.database).expanduser().resolve()
    if not db_path.exists():
        print(f"Error: database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        limit = args.last or 100
        rows = conn.execute(
            "SELECT * FROM snapshots ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        rows = list(reversed(rows))

        if args.format == "json":
            out: list[dict[str, Any]] = []
            for row in rows:
                sid = row["id"]
                snap: dict[str, Any] = dict(row)
                snap["hops"] = [dict(h) for h in conn.execute(
                    "SELECT * FROM hops WHERE snapshot_id = ?", (sid,)
                ).fetchall()]
                snap["counters"] = [dict(c) for c in conn.execute(
                    "SELECT * FROM counters WHERE snapshot_id = ?", (sid,)
                ).fetchall()]
                snap["routes"] = [dict(r) for r in conn.execute(
                    "SELECT * FROM routes WHERE snapshot_id = ?", (sid,)
                ).fetchall()]
                out.append(snap)
            print(json.dumps(out, indent=2, ensure_ascii=False))

        elif args.format == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow([
                "snapshot_id", "captured_at", "role", "interface", "smac64",
                "link_up", "rx_packets", "tx_packets",
            ])
            for row in rows:
                sid = row["id"]
                ts = row["captured_at"]
                hops = conn.execute(
                    "SELECT role, interface, smac64, link_up FROM hops "
                    "WHERE snapshot_id = ?", (sid,)
                ).fetchall()
                ctrs = {c["role"]: dict(c) for c in conn.execute(
                    "SELECT role, rx_packets, tx_packets FROM counters "
                    "WHERE snapshot_id = ?", (sid,)
                ).fetchall()}
                for h in hops:
                    c = ctrs.get(h["role"], {})
                    writer.writerow([
                        sid, ts, h["role"], h["interface"], h["smac64"],
                        h["link_up"],
                        c.get("rx_packets", ""),
                        c.get("tx_packets", ""),
                    ])
            print(buf.getvalue(), end="")
        else:
            print(f"Unknown format: {args.format}", file=sys.stderr)
            return 1
    finally:
        conn.close()

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HUM network telemetry database.",
    )
    sub = p.add_subparsers(dest="command")

    ing = sub.add_parser("ingest", help="Ingest a JSON topology snapshot.")
    ing.add_argument("--database", default="data/telemetry.db")
    ing.add_argument("--file", default=None, help="Read JSON from file instead of stdin.")

    qry = sub.add_parser("query", help="Show recent snapshots.")
    qry.add_argument("--database", default="data/telemetry.db")
    qry.add_argument("--last", type=int, default=5)

    exp = sub.add_parser("export", help="Export snapshots as JSON or CSV.")
    exp.add_argument("--database", default="data/telemetry.db")
    exp.add_argument("--last", type=int, default=100)
    exp.add_argument("--format", choices=["json", "csv"], default="json")

    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "ingest":
        return cmd_ingest(args)
    if args.command == "query":
        return cmd_query(args)
    if args.command == "export":
        return cmd_export(args)
    parse_args().parse_args(["--help"])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
