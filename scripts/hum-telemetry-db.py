#!/usr/bin/env python3
"""Collect HUM network topology telemetry into a local SQLite database.

Consumes structured JSON snapshots produced by ``hum-dev-netns.sh collect`` and
stores point-in-time topology, hop, counter, route, and alert records. The tool
uses only Python standard library modules.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import signal
import sqlite3
import subprocess
import sys
import time
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    rx_packets INTEGER,
    tx_packets INTEGER,
    rx_bytes INTEGER,
    tx_bytes INTEGER,
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    namespace TEXT NOT NULL,
    family TEXT NOT NULL DEFAULT 'inet',
    destination TEXT NOT NULL,
    gateway TEXT,
    device TEXT,
    UNIQUE(snapshot_id, namespace, family, destination)
);

CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id     INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    prev_snapshot_id INTEGER,
    fired_at        TEXT    NOT NULL,
    severity        TEXT    NOT NULL DEFAULT 'info',
    alert_type      TEXT    NOT NULL,
    role            TEXT,
    summary         TEXT    NOT NULL,
    detail_json     TEXT
);

CREATE INDEX IF NOT EXISTS idx_hops_snapshot   ON hops(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_counters_snap   ON counters(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_routes_snap     ON routes(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_time  ON snapshots(captured_at);
CREATE INDEX IF NOT EXISTS idx_alerts_snap     ON alerts(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_alerts_type     ON alerts(alert_type);
"""

    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    prev_snapshot_id INTEGER,
    fired_at TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    alert_type TEXT NOT NULL,
    role TEXT,
    summary TEXT NOT NULL,
    detail_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_hops_snapshot ON hops(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_counters_snap ON counters(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_routes_snap ON routes(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_time ON snapshots(captured_at);
CREATE INDEX IF NOT EXISTS idx_alerts_snap ON alerts(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(alert_type);
"""

COUNTER_JUMP_THRESHOLD = 1000
_STOP_WATCH = False


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
def ingest_snapshot(conn: sqlite3.Connection, data: dict[str, Any]) -> int:
    captured_at = str(data.get("captured_at") or utc_now())
    topology = data.get("topology")

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
        (
            captured_at,
            1 if data.get("peer_chain_enabled") else 0,
            1 if data.get("peer_recv_ready") else 0,
            1 if data.get("peer_chain_recv_ready") else 0,
            json.dumps(topology, ensure_ascii=False) if topology else None,
            json.dumps(data, ensure_ascii=False),
        ),
    )
    snapshot_id: int = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    for hop in data.get("hops", []):
        if not isinstance(hop, dict):
            continue
        conn.execute(
            """INSERT OR REPLACE INTO hops
               (snapshot_id, role, namespace, interface, mac, smac64, ipv4_cidr, ipv6_cidr, link_up)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot_id,
                str(hop.get("role", "unknown")),
                hop.get("namespace"),
                str(hop.get("interface", "unknown")),
                hop.get("mac"),
                hop.get("smac64"),
                hop.get("ipv4_cidr"),
                hop.get("ipv6_cidr"),
                1 if hop.get("link_up") else 0,
            ),
        )

    for counter in data.get("counters", []):
        if not isinstance(counter, dict):
            continue
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
                snapshot_id,
                str(counter.get("role", "unknown")),
                counter.get("rx_packets"),
                counter.get("tx_packets"),
                counter.get("rx_bytes"),
                counter.get("tx_bytes"),
            ),
        )

    for route in data.get("routes", []):
        if not isinstance(route, dict):
            continue
        conn.execute(
            """INSERT OR REPLACE INTO routes
               (snapshot_id, namespace, family, destination, gateway, device)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                snapshot_id,
                str(route.get("namespace", "unknown")),
                str(route.get("family", "inet")),
                str(route.get("destination", "unknown")),
                route.get("gateway"),
                route.get("device"),
            ),
        )

    return snapshot_id


def _row_dicts(conn: sqlite3.Connection, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def _insert_alerts(
    conn: sqlite3.Connection,
    alerts: list[dict[str, Any]],
    snapshot_id: int,
    prev_snapshot_id: int | None,
    fired_at: str,
) -> list[dict[str, Any]]:
    for alert in alerts:
        conn.execute(
            """INSERT INTO alerts
               (snapshot_id, prev_snapshot_id, fired_at, severity, alert_type, role, summary, detail_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot_id,
                prev_snapshot_id,
                fired_at,
                alert["severity"],
                alert["alert_type"],
                alert.get("role"),
                alert["summary"],
                json.dumps(alert.get("detail", {}), ensure_ascii=False),
            ),
        )
    return alerts


def detect_alerts(
    conn: sqlite3.Connection,
    snapshot_id: int,
    prev_snapshot_id: int | None,
) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    alerts: list[dict[str, Any]] = []
    fired_at = utc_now()

    current = dict(conn.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)).fetchone())
    current_hops = {
        item["role"]: item
        for item in _row_dicts(conn, "SELECT * FROM hops WHERE snapshot_id = ?", (snapshot_id,))
    }
    current_counters = {
        item["role"]: item
        for item in _row_dicts(conn, "SELECT * FROM counters WHERE snapshot_id = ?", (snapshot_id,))
    }

    if prev_snapshot_id is None:
        if not current["peer_ready"]:
            alerts.append(
                {
                    "alert_type": "initial_down",
                    "severity": "warning",
                    "summary": "Topology started in DOWN state (peer not ready)",
                    "detail": {"peer_ready": False, "chain_ready": bool(current["chain_ready"])},
                }
            )
        return _insert_alerts(conn, alerts, snapshot_id, prev_snapshot_id, fired_at)

    previous = dict(conn.execute("SELECT * FROM snapshots WHERE id = ?", (prev_snapshot_id,)).fetchone())
    previous_hops = {
        item["role"]: item
        for item in _row_dicts(conn, "SELECT * FROM hops WHERE snapshot_id = ?", (prev_snapshot_id,))
    }
    previous_counters = {
        item["role"]: item
        for item in _row_dicts(conn, "SELECT * FROM counters WHERE snapshot_id = ?", (prev_snapshot_id,))
    }

    for role in set(current_hops) | set(previous_hops):
        current_up = current_hops.get(role, {}).get("link_up", 0)
        previous_up = previous_hops.get(role, {}).get("link_up", 0)
        if previous_up and not current_up:
            alerts.append(
                {
                    "alert_type": "forced_off",
                    "severity": "critical",
                    "role": role,
                    "summary": f"{role} link went DOWN (forced-off)",
                    "detail": {"interface": current_hops.get(role, {}).get("interface", "?")},
                }
            )
        elif not previous_up and current_up:
            alerts.append(
                {
                    "alert_type": "recovery",
                    "severity": "info",
                    "role": role,
                    "summary": f"{role} link came UP (recovery)",
                    "detail": {"interface": current_hops.get(role, {}).get("interface", "?")},
                }
            )

    for role in current_hops:
        if role not in previous_hops:
            alerts.append(
                {
                    "alert_type": "hop_appeared",
                    "severity": "info",
                    "role": role,
                    "summary": f"{role} hop appeared",
                    "detail": {
                        "interface": current_hops[role].get("interface", "?"),
                        "smac64": current_hops[role].get("smac64"),
                    },
                }
            )
    for role in previous_hops:
        if role not in current_hops:
            alerts.append(
                {
                    "alert_type": "hop_disappeared",
                    "severity": "warning",
                    "role": role,
                    "summary": f"{role} hop disappeared",
                    "detail": {"interface": previous_hops[role].get("interface", "?")},
                }
            )

    for role in current_hops:
        if role in previous_hops:
            current_smac = current_hops[role].get("smac64")
            previous_smac = previous_hops[role].get("smac64")
            if current_smac and previous_smac and current_smac != previous_smac:
                alerts.append(
                    {
                        "alert_type": "identity_change",
                        "severity": "warning",
                        "role": role,
                        "summary": f"{role} SMAC64 changed: {previous_smac} -> {current_smac}",
                        "detail": {"prev_smac64": previous_smac, "new_smac64": current_smac},
                    }
                )

    if previous["peer_ready"] and not current["peer_ready"]:
        alerts.append(
            {
                "alert_type": "peer_not_ready",
                "severity": "critical",
                "summary": "Peer recv-ready dropped to NO",
                "detail": {},
            }
        )
    elif not previous["peer_ready"] and current["peer_ready"]:
        alerts.append(
            {
                "alert_type": "peer_ready_restored",
                "severity": "info",
                "summary": "Peer recv-ready restored to YES",
                "detail": {},
            }
        )

    if previous["chain_ready"] and not current["chain_ready"]:
        alerts.append(
            {
                "alert_type": "chain_not_ready",
                "severity": "critical",
                "summary": "Peer chain recv-ready dropped to NO",
                "detail": {},
            }
        )
    elif not previous["chain_ready"] and current["chain_ready"]:
        alerts.append(
            {
                "alert_type": "chain_ready_restored",
                "severity": "info",
                "summary": "Peer chain recv-ready restored to YES",
                "detail": {},
            }
        )

    for role in current_counters:
        if role not in previous_counters:
            continue
        current_rx = current_counters[role].get("rx_packets") or 0
        previous_rx = previous_counters[role].get("rx_packets") or 0
        delta = current_rx - previous_rx
        if delta < 0:
            alerts.append(
                {
                    "alert_type": "counter_reset",
                    "severity": "warning",
                    "role": role,
                    "summary": f"{role} RX counter reset ({previous_rx} -> {current_rx})",
                    "detail": {"prev_rx": previous_rx, "cur_rx": current_rx},
                }
            )
        elif delta > COUNTER_JUMP_THRESHOLD:
            alerts.append(
                {
                    "alert_type": "counter_jump",
                    "severity": "warning",
                    "role": role,
                    "summary": f"{role} RX jumped by {delta} packets",
                    "detail": {"prev_rx": previous_rx, "cur_rx": current_rx, "delta": delta},
                }
            )

    if previous["peer_chain"] and not current["peer_chain"]:
        alerts.append(
            {
                "alert_type": "chain_disabled",
                "severity": "warning",
                "summary": "Peer chain was disabled",
                "detail": {},
            }
        )
    elif not previous["peer_chain"] and current["peer_chain"]:
        alerts.append(
            {
                "alert_type": "chain_enabled",
                "severity": "info",
                "summary": "Peer chain was enabled",
                "detail": {},
            }
        )

    return _insert_alerts(conn, alerts, snapshot_id, prev_snapshot_id, fired_at)


def open_database(database: str) -> sqlite3.Connection:
    db_path = Path(database).expanduser().resolve()
    ensure_parent_dir(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    return conn


def cmd_ingest(args: argparse.Namespace) -> int:
    payload = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    if not payload.strip():
        print("Error: empty input", file=sys.stderr)
        return 1

    data = json.loads(payload)

    conn = sqlite3.connect(db_path)
    try:
        create_schema(conn)

        prev_row = conn.execute(
            "SELECT id FROM snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        prev_snap_id = prev_row[0] if prev_row else None

        snap_id = ingest_snapshot(conn, data)
        fired = detect_alerts(conn, snap_id, prev_snap_id)
        conn.commit()

        print(f"Ingested snapshot {snap_id} into {db_path}")
        if fired:
            for a in fired:
                print(f"  ALERT [{a['severity'].upper()}] {a['summary']}")
    finally:
        conn.close()

    return 0


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

    db_path = Path(args.database).expanduser().resolve()
    conn = open_database(args.database)
    try:
        previous = conn.execute("SELECT id FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
        prev_snapshot_id = previous[0] if previous else None
        snapshot_id = ingest_snapshot(conn, data)
        alerts = detect_alerts(conn, snapshot_id, prev_snapshot_id)
        conn.commit()
        print(f"Ingested snapshot {snapshot_id} into {db_path}")
        for alert in alerts:
            print(f"  ALERT [{alert['severity'].upper()}] {alert['summary']}")
    finally:
        conn.close()
    return 0


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

        rows = conn.execute("SELECT * FROM snapshots ORDER BY id DESC LIMIT ?", (args.last,)).fetchall()
        print(f"=== Last {args.last} snapshots ===\n")
        for row in reversed(rows):
            snapshot_id = row["id"]
            print(
                f"[snapshot {snapshot_id}] {row['captured_at']} "
                f"chain={'on' if row['peer_chain'] else 'off'} "
                f"ready={row['peer_ready']}/{row['chain_ready']}"
            )
            for hop in conn.execute(
                "SELECT role, interface, smac64, link_up FROM hops WHERE snapshot_id = ? ORDER BY id",
                (snapshot_id,),
            ):
                state = "UP" if hop["link_up"] else "DOWN"
                print(
                    f"  hop  {hop['role']:16s} {hop['interface']:20s} "
                    f"smac64={hop['smac64'] or '?':16s} {state}"
                )
            for counter in conn.execute(
                "SELECT role, rx_packets, tx_packets FROM counters WHERE snapshot_id = ? ORDER BY id",
                (snapshot_id,),
            ):
                print(
                    f"  ctr  {counter['role']:16s} "
                    f"rx={counter['rx_packets'] or 0} tx={counter['tx_packets'] or 0}"
                )
            for route in conn.execute(
                "SELECT namespace, family, destination, gateway, device FROM routes "
                "WHERE snapshot_id = ? ORDER BY id",
                (snapshot_id,),
            ):
                gateway = f"via {route['gateway']}" if route["gateway"] else "direct"
                print(
                    f"  rte  {route['namespace']:16s} {route['family']:5s} "
                    f"{route['destination']:20s} {gateway} dev {route['device'] or '?'}"
                )
            print()
    finally:
        conn.close()
    return 0


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
# Alert detection engine
# ---------------------------------------------------------------------------

COUNTER_JUMP_THRESHOLD = 1000  # rx delta per interval that triggers a jump alert


def detect_alerts(
    conn: sqlite3.Connection,
    snap_id: int,
    prev_snap_id: int | None,
) -> list[dict[str, Any]]:
    """Compare snapshot ``snap_id`` against ``prev_snap_id`` and return alerts."""
    conn.row_factory = sqlite3.Row
    alerts: list[dict[str, Any]] = []
    now = utc_now()

    cur = dict(conn.execute(
        "SELECT * FROM snapshots WHERE id = ?", (snap_id,)
    ).fetchone())
    cur_hops = {h["role"]: dict(h) for h in conn.execute(
        "SELECT * FROM hops WHERE snapshot_id = ?", (snap_id,)
    ).fetchall()}
    cur_ctrs = {c["role"]: dict(c) for c in conn.execute(
        "SELECT * FROM counters WHERE snapshot_id = ?", (snap_id,)
    ).fetchall()}

    if prev_snap_id is None:
        if not cur["peer_ready"]:
            alerts.append({
                "alert_type": "initial_down",
                "severity": "warning",
                "role": None,
                "summary": "Topology started in DOWN state (peer not ready)",
                "detail": {"peer_ready": False, "chain_ready": bool(cur["chain_ready"])},
            })
        return _insert_alerts(conn, alerts, snap_id, prev_snap_id, now)

    prev = dict(conn.execute(
        "SELECT * FROM snapshots WHERE id = ?", (prev_snap_id,)
    ).fetchone())
    prev_hops = {h["role"]: dict(h) for h in conn.execute(
        "SELECT * FROM hops WHERE snapshot_id = ?", (prev_snap_id,)
    ).fetchall()}
    prev_ctrs = {c["role"]: dict(c) for c in conn.execute(
        "SELECT * FROM counters WHERE snapshot_id = ?", (prev_snap_id,)
    ).fetchall()}

    # --- Link forced-off / recovery ---
    for role in set(cur_hops) | set(prev_hops):
        cur_up = cur_hops.get(role, {}).get("link_up", 0)
        prev_up = prev_hops.get(role, {}).get("link_up", 0)
        if prev_up and not cur_up:
            alerts.append({
                "alert_type": "forced_off",
                "severity": "critical",
                "role": role,
                "summary": f"{role} link went DOWN (forced-off)",
                "detail": {"interface": cur_hops.get(role, {}).get("interface", "?")},
            })
        elif not prev_up and cur_up:
            alerts.append({
                "alert_type": "recovery",
                "severity": "info",
                "role": role,
                "summary": f"{role} link came UP (recovery)",
                "detail": {"interface": cur_hops.get(role, {}).get("interface", "?")},
            })

    # --- Hop appeared / disappeared ---
    for role in cur_hops:
        if role not in prev_hops:
            alerts.append({
                "alert_type": "hop_appeared",
                "severity": "info",
                "role": role,
                "summary": f"{role} hop appeared",
                "detail": {"interface": cur_hops[role].get("interface", "?"),
                           "smac64": cur_hops[role].get("smac64")},
            })
    for role in prev_hops:
        if role not in cur_hops:
            alerts.append({
                "alert_type": "hop_disappeared",
                "severity": "warning",
                "role": role,
                "summary": f"{role} hop disappeared",
                "detail": {"interface": prev_hops[role].get("interface", "?")},
            })

    # --- Identity change (SMAC64 changed on same role) ---
    for role in cur_hops:
        if role in prev_hops:
            c_s = cur_hops[role].get("smac64")
            p_s = prev_hops[role].get("smac64")
            if c_s and p_s and c_s != p_s:
                alerts.append({
                    "alert_type": "identity_change",
                    "severity": "warning",
                    "role": role,
                    "summary": f"{role} SMAC64 changed: {p_s} -> {c_s}",
                    "detail": {"prev_smac64": p_s, "new_smac64": c_s},
                })

    # --- Peer readiness transitions ---
    if prev["peer_ready"] and not cur["peer_ready"]:
        alerts.append({
            "alert_type": "peer_not_ready",
            "severity": "critical",
            "role": None,
            "summary": "Peer recv-ready dropped to NO",
            "detail": {},
        })
    elif not prev["peer_ready"] and cur["peer_ready"]:
        alerts.append({
            "alert_type": "peer_ready_restored",
            "severity": "info",
            "role": None,
            "summary": "Peer recv-ready restored to YES",
            "detail": {},
        })

    if prev["chain_ready"] and not cur["chain_ready"]:
        alerts.append({
            "alert_type": "chain_not_ready",
            "severity": "critical",
            "role": None,
            "summary": "Peer chain recv-ready dropped to NO",
            "detail": {},
        })
    elif not prev["chain_ready"] and cur["chain_ready"]:
        alerts.append({
            "alert_type": "chain_ready_restored",
            "severity": "info",
            "role": None,
            "summary": "Peer chain recv-ready restored to YES",
            "detail": {},
        })

    # --- Counter jumps ---
    for role in cur_ctrs:
        if role in prev_ctrs:
            c_rx = cur_ctrs[role].get("rx_packets") or 0
            p_rx = prev_ctrs[role].get("rx_packets") or 0
            delta = c_rx - p_rx
            if delta < 0:
                alerts.append({
                    "alert_type": "counter_reset",
                    "severity": "warning",
                    "role": role,
                    "summary": f"{role} RX counter reset ({p_rx} -> {c_rx})",
                    "detail": {"prev_rx": p_rx, "cur_rx": c_rx},
                })
            elif delta > COUNTER_JUMP_THRESHOLD:
                alerts.append({
                    "alert_type": "counter_jump",
                    "severity": "warning",
                    "role": role,
                    "summary": f"{role} RX jumped by {delta} packets",
                    "detail": {"prev_rx": p_rx, "cur_rx": c_rx, "delta": delta},
                })

    # --- Peer chain toggled ---
    if prev["peer_chain"] and not cur["peer_chain"]:
        alerts.append({
            "alert_type": "chain_disabled",
            "severity": "warning",
            "role": None,
            "summary": "Peer chain was disabled",
            "detail": {},
        })
    elif not prev["peer_chain"] and cur["peer_chain"]:
        alerts.append({
            "alert_type": "chain_enabled",
            "severity": "info",
            "role": None,
            "summary": "Peer chain was enabled",
            "detail": {},
        })

    return _insert_alerts(conn, alerts, snap_id, prev_snap_id, now)


def _insert_alerts(
    conn: sqlite3.Connection,
    alerts: list[dict[str, Any]],
    snap_id: int,
    prev_snap_id: int | None,
    fired_at: str,
) -> list[dict[str, Any]]:
    for a in alerts:
        conn.execute(
            """INSERT INTO alerts
               (snapshot_id, prev_snapshot_id, fired_at, severity,
                alert_type, role, summary, detail_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snap_id,
                prev_snap_id,
                fired_at,
                a["severity"],
                a["alert_type"],
                a.get("role"),
                a["summary"],
                json.dumps(a.get("detail", {}), ensure_ascii=False),
            ),
        )
    return alerts


# ---------------------------------------------------------------------------
# Watch loop
# ---------------------------------------------------------------------------

_stop_watch = False


def _sighandler(_sig: int, _frame: Any) -> None:
    global _stop_watch  # noqa: PLW0603
    _stop_watch = True


def cmd_watch(args: argparse.Namespace) -> int:
    db_path = Path(args.database).expanduser().resolve()
    ensure_parent_dir(db_path)

    collect_cmd = args.collect_cmd
    interval = args.interval

    global _stop_watch  # noqa: PLW0603
    _stop_watch = False
    signal.signal(signal.SIGINT, _sighandler)
    signal.signal(signal.SIGTERM, _sighandler)

    conn = sqlite3.connect(db_path)
    create_schema(conn)

    prev_snap_id: int | None = None
    row = conn.execute("SELECT id FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        prev_snap_id = row[0]

    print(f"[watch] database={db_path}  interval={interval}s  cmd={collect_cmd}")
    print(f"[watch] starting (Ctrl-C to stop)...")
    cycle = 0

    while not _stop_watch:
        cycle += 1
        try:
            result = subprocess.run(
                collect_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=max(interval - 1, 5),
            )
            if result.returncode != 0 or not result.stdout.strip():
                ts = utc_now()
                print(f"[watch {ts}] collect failed (rc={result.returncode}), skipping")
                time.sleep(interval)
                continue

            data = json.loads(result.stdout)
            snap_id = ingest_snapshot(conn, data)
            fired = detect_alerts(conn, snap_id, prev_snap_id)
            conn.commit()

            ts = data.get("captured_at", "?")
            if fired:
                for a in fired:
                    sev = a["severity"].upper()
                    print(f"[watch {ts}] ALERT [{sev}] {a['summary']}")
            else:
                if cycle == 1 or cycle % 12 == 0:
                    print(f"[watch {ts}] snapshot {snap_id} ok (no alerts)")

            prev_snap_id = snap_id

        except json.JSONDecodeError as exc:
            print(f"[watch] JSON parse error: {exc}", file=sys.stderr)
        except subprocess.TimeoutExpired:
            print(f"[watch] collect command timed out", file=sys.stderr)
        except Exception as exc:
            print(f"[watch] error: {exc}", file=sys.stderr)

        if not _stop_watch:
            time.sleep(interval)

    print(f"\n[watch] stopped after {cycle} cycles")
    conn.close()
    return 0


# ---------------------------------------------------------------------------
# Alerts query
# ---------------------------------------------------------------------------

        rows = list(
            reversed(conn.execute("SELECT * FROM snapshots ORDER BY id DESC LIMIT ?", (args.last,)).fetchall())
        )
        if args.format == "json":
            output: list[dict[str, Any]] = []
            for row in rows:
                snapshot_id = row["id"]
                snapshot = dict(row)
                snapshot["hops"] = _row_dicts(conn, "SELECT * FROM hops WHERE snapshot_id = ?", (snapshot_id,))
                snapshot["counters"] = _row_dicts(
                    conn, "SELECT * FROM counters WHERE snapshot_id = ?", (snapshot_id,)
                )
                snapshot["routes"] = _row_dicts(conn, "SELECT * FROM routes WHERE snapshot_id = ?", (snapshot_id,))
                output.append(snapshot)
            print(json.dumps(output, indent=2, ensure_ascii=False))
            return 0

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            ["snapshot_id", "captured_at", "role", "interface", "smac64", "link_up", "rx_packets", "tx_packets"]
        )
        for row in rows:
            snapshot_id = row["id"]
            counters = {
                counter["role"]: dict(counter)
                for counter in conn.execute(
                    "SELECT role, rx_packets, tx_packets FROM counters WHERE snapshot_id = ?",
                    (snapshot_id,),
                ).fetchall()
            }
            for hop in conn.execute(
                "SELECT role, interface, smac64, link_up FROM hops WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchall():
                counter = counters.get(hop["role"], {})
                writer.writerow(
                    [
                        snapshot_id,
                        row["captured_at"],
                        hop["role"],
                        hop["interface"],
                        hop["smac64"],
                        hop["link_up"],
                        counter.get("rx_packets", ""),
                        counter.get("tx_packets", ""),
                    ]
                )
        print(buffer.getvalue(), end="")
    finally:
        conn.close()
    return 0


def cmd_alerts(args: argparse.Namespace) -> int:
    db_path = Path(args.database).expanduser().resolve()
    if not db_path.exists():
        print(f"Error: database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        limit = args.last or 20
        severity_filter = args.severity

        query = "SELECT * FROM alerts"
        params: list[Any] = []
        if severity_filter:
            query += " WHERE severity = ?"
            params.append(severity_filter)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        rows = list(reversed(rows))

        if not rows:
            print("(no alerts)")
            return 0

        print(f"=== Last {limit} alerts"
              f"{f' (severity={severity_filter})' if severity_filter else ''} ===\n")
        for r in rows:
            sev = r["severity"].upper()
            role_str = f" [{r['role']}]" if r["role"] else ""
            print(f"  #{r['id']:4d}  {r['fired_at']}  {sev:8s}  "
                  f"{r['alert_type']:24s}{role_str}  {r['summary']}")
        print()
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

    wat = sub.add_parser("watch", help="Collect snapshots on interval, detect state transitions.")
    wat.add_argument("--database", default="data/telemetry.db")
    wat.add_argument("--interval", type=int, default=5, help="Seconds between collections (default 5).")
    wat.add_argument("--collect-cmd", default="bash scripts/hum-dev-netns.sh collect",
                     help="Shell command to collect a JSON snapshot.")

    alt = sub.add_parser("alerts", help="Show recent alerts.")
    alt.add_argument("--database", default="data/telemetry.db")
    alt.add_argument("--last", type=int, default=20)
    alt.add_argument("--severity", choices=["info", "warning", "critical"], default=None)

    return p.parse_args()


def main() -> int:
    args = parse_args()
        query = "SELECT * FROM alerts"
        params: list[Any] = []
        if args.severity:
            query += " WHERE severity = ?"
            params.append(args.severity)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(args.last)
        rows = list(reversed(conn.execute(query, params).fetchall()))
        if not rows:
            print("(no alerts)")
            return 0
        print(f"=== Last {args.last} alerts ===\n")
        for row in rows:
            role = f" [{row['role']}]" if row["role"] else ""
            print(
                f"  #{row['id']:4d} {row['fired_at']} {row['severity'].upper():8s} "
                f"{row['alert_type']:24s}{role} {row['summary']}"
            )
    finally:
        conn.close()
    return 0


def _signal_handler(_signal_number: int, _frame: Any) -> None:
    global _STOP_WATCH
    _STOP_WATCH = True


def cmd_watch(args: argparse.Namespace) -> int:
    global _STOP_WATCH
    _STOP_WATCH = False
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    conn = open_database(args.database)
    previous = conn.execute("SELECT id FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
    prev_snapshot_id = previous[0] if previous else None
    print(f"[watch] database={Path(args.database).expanduser().resolve()} interval={args.interval}s")

    cycles = 0
    try:
        while not _STOP_WATCH:
            cycles += 1
            try:
                result = subprocess.run(
                    args.collect_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=max(args.interval - 1, 5),
                )
                if result.returncode != 0 or not result.stdout.strip():
                    print(f"[watch] collect failed rc={result.returncode}", file=sys.stderr)
                    time.sleep(args.interval)
                    continue
                snapshot = json.loads(result.stdout)
                snapshot_id = ingest_snapshot(conn, snapshot)
                alerts = detect_alerts(conn, snapshot_id, prev_snapshot_id)
                conn.commit()
                if alerts:
                    for alert in alerts:
                        print(f"[watch] ALERT [{alert['severity'].upper()}] {alert['summary']}")
                elif cycles == 1 or cycles % 12 == 0:
                    print(f"[watch] snapshot {snapshot_id} ok")
                prev_snapshot_id = snapshot_id
            except json.JSONDecodeError as exc:
                print(f"[watch] JSON parse error: {exc}", file=sys.stderr)
            except subprocess.TimeoutExpired:
                print("[watch] collect command timed out", file=sys.stderr)
            if not _STOP_WATCH:
                time.sleep(args.interval)
    finally:
        conn.close()
    print(f"[watch] stopped after {cycles} cycles")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HUM network telemetry database.")
    subcommands = parser.add_subparsers(dest="command")

    ingest = subcommands.add_parser("ingest", help="Ingest a JSON topology snapshot.")
    ingest.add_argument("--database", default="data/telemetry.db")
    ingest.add_argument("--file", default=None, help="Read JSON from file instead of stdin.")

    query = subcommands.add_parser("query", help="Show recent snapshots.")
    query.add_argument("--database", default="data/telemetry.db")
    query.add_argument("--last", type=int, default=5)

    export = subcommands.add_parser("export", help="Export snapshots as JSON or CSV.")
    export.add_argument("--database", default="data/telemetry.db")
    export.add_argument("--last", type=int, default=100)
    export.add_argument("--format", choices=["json", "csv"], default="json")

    alerts = subcommands.add_parser("alerts", help="Show recent alerts.")
    alerts.add_argument("--database", default="data/telemetry.db")
    alerts.add_argument("--last", type=int, default=20)
    alerts.add_argument("--severity", choices=["info", "warning", "critical"], default=None)

    watch = subcommands.add_parser("watch", help="Collect snapshots on interval.")
    watch.add_argument("--database", default="data/telemetry.db")
    watch.add_argument("--interval", type=int, default=5)
    watch.add_argument("--collect-cmd", default="bash scripts/hum-dev-netns.sh collect")

    return parser


def parse_args() -> argparse.Namespace:
    return build_parser().parse_args()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "ingest":
        return cmd_ingest(args)
    if args.command == "query":
        return cmd_query(args)
    if args.command == "export":
        return cmd_export(args)
    if args.command == "watch":
        return cmd_watch(args)
    if args.command == "alerts":
        return cmd_alerts(args)
    parse_args().parse_args(["--help"])
    if args.command == "alerts":
        return cmd_alerts(args)
    if args.command == "watch":
        return cmd_watch(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
