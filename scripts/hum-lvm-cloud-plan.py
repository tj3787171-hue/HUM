#!/usr/bin/env python3
"""Create a non-destructive LVM/cloud-location readiness plan.

The script inventories storage, encrypted-volume tooling, cloud-backed paths,
and HUM listener defaults. It intentionally does not create, format, mount, or
modify LVM devices.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CLOUD_ROOTS = (
    "~/Cloud",
    "~/Google Drive",
    "/mnt/chromeos/GoogleDrive",
    "/mnt/chromeos/MyFiles",
    "/host-downloads",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inventory LVM, encrypted storage, and cloud locations without changing disks.",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Filesystem path to include as a planned LVM/cloud source location.",
    )
    parser.add_argument(
        "--cloud-root",
        action="append",
        default=[],
        help="Cloud or backup root path to check. May be supplied multiple times.",
    )
    parser.add_argument(
        "--output",
        default="diagnostics/lvm-cloud-plan.json",
        help="JSON output path (default: diagnostics/lvm-cloud-plan.json).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when no usable source/cloud paths are visible.",
    )
    return parser.parse_args()


def run_json_command(command: list[str]) -> Any | None:
    try:
        completed = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None


def path_record(raw_path: str) -> dict[str, Any]:
    expanded = Path(raw_path).expanduser()
    exists = expanded.exists()
    record: dict[str, Any] = {
        "path": str(expanded),
        "exists": exists,
        "is_dir": expanded.is_dir() if exists else False,
        "is_mount": os.path.ismount(expanded) if exists else False,
    }
    if exists:
        try:
            usage = shutil.disk_usage(expanded)
            record["disk_usage"] = {
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
            }
        except OSError as exc:
            record["disk_usage_error"] = str(exc)
    return record


def flatten_block_devices(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for device in devices:
        item = {key: value for key, value in device.items() if key != "children"}
        flattened.append(item)
        children = device.get("children")
        if isinstance(children, list):
            flattened.extend(flatten_block_devices(children))
    return flattened


def visible_block_devices() -> list[dict[str, Any]]:
    data = run_json_command(
        ["lsblk", "-J", "-b", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,RM,TRAN,MODEL"]
    )
    if not isinstance(data, dict):
        return []
    devices = data.get("blockdevices")
    if not isinstance(devices, list):
        return []
    return flatten_block_devices(devices)


def command_presence() -> dict[str, bool]:
    commands = ("lsblk", "pvs", "vgs", "lvs", "cryptsetup", "rclone", "git")
    return {command: shutil.which(command) is not None for command in commands}


def lvm_summary() -> dict[str, Any]:
    result: dict[str, Any] = {"commands": command_presence()}
    for label, command in {
        "physical_volumes": ["pvs", "--reportformat", "json"],
        "volume_groups": ["vgs", "--reportformat", "json"],
        "logical_volumes": ["lvs", "--reportformat", "json"],
    }.items():
        data = run_json_command(command)
        result[label] = data if data is not None else {"available": False}
    return result


def privacy_bindings() -> dict[str, str]:
    return {
        "virtual_desktop_bind": os.environ.get("HUM_VDESK_BIND", "127.0.0.1"),
        "virtual_desktop_port": os.environ.get("HUM_VDESK_PORT", "6080"),
        "vnc_port": os.environ.get("HUM_VNC_PORT", "5901"),
        "chrome_remote_debug_bind": os.environ.get("HUM_CHROME_REMOTE_DEBUG_ADDR", "127.0.0.1"),
        "chrome_remote_debug_port": os.environ.get("HUM_CHROME_REMOTE_DEBUG_PORT", "9222"),
    }


def recommended_actions(
    sources: list[dict[str, Any]],
    clouds: list[dict[str, Any]],
    commands: dict[str, bool],
) -> list[str]:
    actions = [
        "Keep LVM mutation manual: create/extend volume groups only after confirming source devices.",
        "Keep encrypted cloud sync mounted under a known path before importing data into SQLite.",
    ]
    if not commands.get("cryptsetup", False):
        actions.append("Install cryptsetup before opening LUKS/encrypted backup volumes.")
    if not commands.get("pvs", False) or not commands.get("lvs", False):
        actions.append("Install lvm2 before managing LVM physical or logical volumes.")
    if not any(item["exists"] for item in sources):
        actions.append("Provide --source /path/to/mounted/backup once the SSD or encrypted volume is mounted.")
    if not any(item["exists"] for item in clouds):
        actions.append("Provide --cloud-root /path/to/cloud/root for the encrypted cloud service location.")
    return actions


def main() -> int:
    args = parse_args()
    cloud_roots = args.cloud_root or list(DEFAULT_CLOUD_ROOTS)
    sources = [path_record(source) for source in args.source]
    clouds = [path_record(path) for path in cloud_roots]
    devices = visible_block_devices()
    lvm = lvm_summary()

    encrypted_candidates = [
        device
        for device in devices
        if str(device.get("fstype", "")).lower() in {"crypto_luks", "bitlocker"}
    ]
    mounted_large_devices = [
        device
        for device in devices
        if int(device.get("size") or 0) >= 1_500_000_000_000 and device.get("mountpoints")
    ]

    output = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
        "cwd": str(Path.cwd()),
        "sources": sources,
        "cloud_roots": clouds,
        "block_devices": devices,
        "encrypted_candidates": encrypted_candidates,
        "mounted_large_devices": mounted_large_devices,
        "lvm": lvm,
        "privacy_bindings": privacy_bindings(),
        "automatic_actions": [
            "created diagnostics output directory",
            "inventoried visible source/cloud paths",
            "inventoried block devices and LVM command availability",
            "generated recommended manual storage actions",
        ],
    }
    output["recommended_actions"] = recommended_actions(
        sources,
        clouds,
        lvm["commands"],
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    visible_sources = sum(1 for item in sources if item["exists"])
    visible_clouds = sum(1 for item in clouds if item["exists"])
    print(f"LVM/cloud plan written: {output_path}")
    print(f"Visible source paths: {visible_sources}/{len(sources)}")
    print(f"Visible cloud roots: {visible_clouds}/{len(clouds)}")
    print(f"Encrypted block candidates: {len(encrypted_candidates)}")
    print(f"Mounted large devices: {len(mounted_large_devices)}")

    if args.strict and visible_sources == 0 and visible_clouds == 0:
        print("Strict mode failed: no source or cloud paths are visible.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
