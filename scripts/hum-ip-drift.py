#!/usr/bin/env python3
"""Report and optionally correct static IPv4 drift inside the housing container.

Default commands are status/plan only. `correct` delegates to
scripts/hum-host-static-ip.sh apply and does not build a VPN attack path.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from ipaddress import IPv4Address, ip_address
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATIC_SCRIPT = ROOT / "scripts" / "hum-host-static-ip.sh"
DEFAULT_EXPECTED = os.environ.get("HUM_HOST_STATIC_CIDR", "192.168.68.100/22")


def expected_ip(cidr: str) -> IPv4Address:
    return ip_address(cidr.split("/", 1)[0])  # type: ignore[return-value]


def current_ipv4_addresses() -> list[str]:
    result = subprocess.run(
        ["ip", "-4", "-o", "addr", "show"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    found: list[str] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if "inet" in parts:
            idx = parts.index("inet")
            if idx + 1 < len(parts):
                found.append(parts[idx + 1].split("/", 1)[0])
    return found


def drift_report(expected_cidr: str, current: list[str] | None = None) -> dict[str, Any]:
    want = expected_ip(expected_cidr)
    have = current if current is not None else current_ipv4_addresses()
    matched = str(want) in have
    octet_delta = None
    if have:
        last = ip_address(have[0])
        if isinstance(last, IPv4Address):
            octet_delta = int(last) - int(want)
    return {
        "housing": "container-local",
        "expected": str(want),
        "expected_cidr": expected_cidr,
        "current": have,
        "matched": matched,
        "octet_delta": octet_delta,
        "vpn_note": "Tunnel housing stays in hum-proxy-ns. Drift correction re-applies the static host address only.",
        "vnc_note": "VNC stays on 127.0.0.1. Drift correction does not move VNC onto nbd0.",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Static IPv4 drift status for the housing container.")
    parser.add_argument("--expected", default=DEFAULT_EXPECTED)
    parser.add_argument("--current", action="append", default=None, help="Override observed IPv4 (repeatable, for tests).")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Compare expected static IP to current addresses.")
    sub.add_parser("plan", help="Print the correct command without running it.")
    sub.add_parser("correct", help="Delegate to hum-host-static-ip.sh apply (root).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = drift_report(args.expected, args.current)
    if args.command == "status":
        print(json.dumps(report, indent=2))
        return 0 if report["matched"] else 1
    if args.command == "plan":
        report["correct_command"] = f"sudo bash {STATIC_SCRIPT} apply"
        print(json.dumps(report, indent=2))
        return 0
    if args.command == "correct":
        if not STATIC_SCRIPT.is_file():
            print("missing hum-host-static-ip.sh", flush=True)
            return 2
        completed = subprocess.run(["bash", str(STATIC_SCRIPT), "apply"], check=False)
        return completed.returncode
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
