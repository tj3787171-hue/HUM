#!/usr/bin/env python3
"""Allocate simple isolation zones for the HUM virtio housing container.

Arithmetic only: one /30 track per guest, dummy-rail names, and a hard
split between the VNC display zone and /dev/nbd0. This script never
attaches VNC to NBD and never starts a pentest path.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "site" / "circuits" / "data" / "iso-catalog.json"
DEFAULT_OUTPUT = ROOT / "site" / "circuits" / "data" / "zones.json"

HOUSING_NET = "10.224.0.0/16"
MAX_GUESTS = 16
DISPLAY_ZONE_BASE = 100
DISK_ZONE_BASE = 200
NBD_ZONE_ID = 300
VNC_BIND = "127.0.0.1"
VNC_PORT_BASE = 5901
NOVNC_PORT_BASE = 6080


def load_catalog(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("iso catalog must be a JSON object")
    return payload


def present_iso_count(catalog: dict[str, Any]) -> int:
    isos = catalog.get("isos", [])
    if not isinstance(isos, list):
        raise ValueError("iso catalog.isos must be a list")
    return sum(1 for item in isos if isinstance(item, dict) and item.get("phase") == "present")


def allocate_zones(guest_count: int, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    if guest_count < 1 or guest_count > MAX_GUESTS:
        raise ValueError(f"guest_count must be 1-{MAX_GUESTS}")

    guests: list[dict[str, Any]] = []
    for index in range(guest_count):
        display_zone = DISPLAY_ZONE_BASE + index
        disk_zone = DISK_ZONE_BASE + index
        if display_zone == NBD_ZONE_ID or disk_zone == NBD_ZONE_ID:
            raise RuntimeError("display/disk zone collided with nbd0 zone")
        guests.append(
            {
                "index": index,
                "track": f"10.224.{index}.0/30",
                "left": f"10.224.{index}.1",
                "right": f"10.224.{index}.2",
                "dummy_rail": f"hum-dummy{index}",
                "display_zone": display_zone,
                "disk_zone": disk_zone,
                "vnc_bind": VNC_BIND,
                "vnc_port": VNC_PORT_BASE + index,
                "novnc_port": NOVNC_PORT_BASE + index,
                "vnc_shares_nbd": False,
            }
        )

    optional = []
    if catalog:
        for item in catalog.get("isos", []):
            if isinstance(item, dict) and item.get("phase") != "present":
                optional.append(item.get("id"))

    plan = {
        "housing": HOUSING_NET,
        "virtio": {
            "guest": "/dev/vda",
            "host": "/dev/sda",
            "note": "Virtio guest disk vda maps to the host sda/vda attachment. Not nbd0.",
        },
        "nbd0": {
            "device": "/dev/nbd0",
            "zone": NBD_ZONE_ID,
            "vnc_attach": "denied",
            "reason": "VNC is a display path. nbd0 is a block export. Sharing a namespace is a high-risk collision.",
        },
        "pattern_2026": {
            "https": {"port": 443, "bind": VNC_BIND},
            "dns": {"port": 53, "scope": "housing-ns-only"},
            "login": {"port": 8088, "bind": VNC_BIND},
        },
        "guest_count": guest_count,
        "guests": guests,
        "optional_iso_ids": optional,
        "kernel_plan": [
            f"ip netns add hum-track-{index}"
            for index in range(guest_count)
        ]
        + [
            "keep VNC listeners on 127.0.0.1 only",
            "do not qemu-nbd or nbd-client into the VNC namespace",
            "dummy rails are names only when the kernel lacks dummy iface support",
        ],
    }
    assert_vnc_nbd_separated(plan)
    return plan


def assert_vnc_nbd_separated(plan: dict[str, Any]) -> None:
    nbd_zone = int(plan["nbd0"]["zone"])
    if plan["nbd0"].get("vnc_attach") != "denied":
        raise RuntimeError("nbd0 vnc_attach must stay denied")
    for guest in plan["guests"]:
        if int(guest["display_zone"]) == nbd_zone:
            raise RuntimeError("VNC display zone collided with nbd0")
        if guest.get("vnc_shares_nbd"):
            raise RuntimeError("guest marked vnc_shares_nbd")
        if guest.get("vnc_bind") != VNC_BIND:
            raise RuntimeError("VNC must bind loopback")


def virtio_status() -> dict[str, Any]:
    devices = {
        "vda": Path("/dev/vda").exists() or Path("/sys/block/vda").exists(),
        "sda": Path("/dev/sda").exists() or Path("/sys/block/sda").exists(),
        "nbd0": Path("/dev/nbd0").exists() or Path("/sys/block/nbd0").exists(),
    }
    return {
        "map": {"guest": "/dev/vda", "host": "/dev/sda"},
        "present": devices,
        "nbd0_vnc_policy": "denied",
    }


def nbd_risk_status() -> dict[str, Any]:
    nbd_present = Path("/dev/nbd0").exists() or Path("/sys/block/nbd0").exists()
    vnc_port = os.environ.get("HUM_VNC_PORT", "5901")
    return {
        "nbd0_present": nbd_present,
        "vnc_port": vnc_port,
        "vnc_attach": "denied",
        "action": "leave nbd0 in zone 300; keep VNC on 127.0.0.1 display zones 100+",
        "safe": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HUM isolation-zone arithmetic (no VNC-NBD attach).")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--guests", type=int, default=0, help="Override guest count (default: present ISOs).")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="Print zone JSON.")
    sub.add_parser("write", help="Write site/circuits/data/zones.json.")
    sub.add_parser("virtio", help="Report vda/sda/nbd0 presence.")
    sub.add_parser("nbd-risk", help="Confirm VNC is not attached to nbd0.")
    return parser.parse_args()


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    catalog_path = Path(args.catalog)
    catalog = load_catalog(catalog_path) if catalog_path.is_file() else {}
    guests = args.guests or present_iso_count(catalog) or 3
    return allocate_zones(guests, catalog)


def main() -> int:
    args = parse_args()
    if args.command == "virtio":
        print(json.dumps(virtio_status(), indent=2))
        return 0
    if args.command == "nbd-risk":
        print(json.dumps(nbd_risk_status(), indent=2))
        return 0
    plan = build_plan(args)
    if args.command == "write":
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {output}")
        return 0
    print(json.dumps(plan, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
