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


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    peer_chain INTEGER NOT NULL DEFAULT 0,
    peer_ready INTEGER NOT NULL DEFAULT 0,
    chain_ready INTEGER NOT NULL DEFAULT 0,
    topology_json TEXT,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    namespace TEXT,
    interface TEXT NOT NULL,
    mac TEXT,
    smac64 TEXT,
    ipv4_cidr TEXT,
    ipv6_cidr TEXT,
    link_up INTEGER,
    UNIQUE(snapshot_id, role)
);

CREATE TABLE IF NOT EXISTS counters (
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


def ingest_snapshot(conn: sqlite3.Connection, data: dict[str, Any]) -> int:
    captured_at = str(data.get("captured_at") or utc_now())
    topology = data.get("topology")

    conn.execute(
        """INSERT INTO snapshots
           (captured_at, peer_chain, peer_ready, chain_ready, topology_json, raw_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
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
    if args.command == "alerts":
        return cmd_alerts(args)
    if args.command == "watch":
        return cmd_watch(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
