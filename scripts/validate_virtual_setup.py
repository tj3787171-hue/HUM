#!/usr/bin/env python3
"""Cross-check websetup virtual artifacts against SDV manifest constraints."""

from __future__ import annotations

import argparse
import csv
import ipaddress
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _parse_ip(text: str) -> ipaddress.IPv4Address:
    return ipaddress.ip_address(text.split("/", 1)[0])


def _sdv_range_octets(manifest: dict[str, Any]) -> tuple[int, int]:
    network = manifest.get("network", {})
    alloc = network.get("allocatable_range")
    if not isinstance(alloc, dict):
        raise ValueError("manifest.network.allocatable_range missing/invalid")
    start_raw = alloc.get("start")
    end_raw = alloc.get("end")
    if not isinstance(start_raw, str) or not isinstance(end_raw, str):
        raise ValueError("allocatable_range start/end must be IPv4 strings")
    start = int(str(_parse_ip(start_raw)).split(".")[-1])
    end = int(str(_parse_ip(end_raw)).split(".")[-1])
    return start, end


def _iter_inventory(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for idx, row in enumerate(rows, start=2):
        if "id" not in row:
            raise ValueError(f"{path}:{idx} missing 'id' column")
    return rows


def validate_virtual_setup(
    *,
    inventory_path: Path,
    network_matrix_path: Path,
    manifest_path: Path,
) -> tuple[bool, list[str]]:
    errors: list[str] = []

    manifest = _load_json(manifest_path)
    matrix = _load_json(network_matrix_path)
    inventory_rows = _iter_inventory(inventory_path)

    network = manifest.get("network")
    if not isinstance(network, dict):
        return False, ["manifest.network missing/invalid"]

    subnet = network.get("subnet_cidr")
    if not isinstance(subnet, str):
        return False, ["manifest.network.subnet_cidr missing/invalid"]
    cidr = ipaddress.ip_network(subnet, strict=True)

    script_assigned = network.get("script_assigned", {})
    reserved_ips: set[ipaddress.IPv4Address] = set()
    if isinstance(script_assigned, dict):
        for iface, value in script_assigned.items():
            if isinstance(value, str):
                try:
                    reserved_ips.add(_parse_ip(value))
                except ValueError:
                    errors.append(f"manifest script_assigned.{iface} invalid IP: {value!r}")

    reserved_br_int = network.get("reserved_br_int")
    if isinstance(reserved_br_int, str):
        try:
            reserved_ips.add(_parse_ip(reserved_br_int))
        except ValueError:
            errors.append(f"manifest reserved_br_int invalid IP: {reserved_br_int!r}")

    try:
        start_octet, end_octet = _sdv_range_octets(manifest)
    except ValueError as exc:
        errors.append(str(exc))
        start_octet, end_octet = (0, -1)

    workload_ids: set[str] = set()
    for row in inventory_rows:
        row_id = (row.get("id") or "").strip()
        if not row_id:
            errors.append("inventory row has empty id")
            continue

        ip_text = (row.get("ip_address") or "").strip()
        segment = (row.get("segment") or "").strip()

        if ip_text in {"", "TBD", "-", "192.168.68.x"}:
            continue

        try:
            ip = _parse_ip(ip_text)
        except ValueError:
            errors.append(f"inventory {row_id}: invalid ip_address {ip_text!r}")
            continue

        if segment in {"workload", "ephemeral", "core"}:
            if ip not in cidr:
                errors.append(f"inventory {row_id}: IP {ip} is outside SDV subnet {cidr}")

        if segment in {"workload", "ephemeral"}:
            workload_ids.add(row_id)
            octet = int(str(ip).split(".")[-1])
            if not (start_octet <= octet <= end_octet):
                errors.append(
                    f"inventory {row_id}: {ip} outside allocatable_range "
                    f"{start_octet}..{end_octet}"
                )
            if ip in reserved_ips:
                errors.append(f"inventory {row_id}: {ip} conflicts with reserved/script-assigned IPs")

    nodes = matrix.get("nodes", [])
    if not isinstance(nodes, list):
        errors.append("network-matrix nodes must be an array")
        nodes = []
    node_ids = {
        str(node.get("id"))
        for node in nodes
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    for workload_id in workload_ids:
        if workload_id not in node_ids:
            errors.append(
                f"network-matrix missing node for inventory workload/ephemeral id {workload_id!r}"
            )

    edges = matrix.get("edges", [])
    if not isinstance(edges, list):
        errors.append("network-matrix edges must be an array")
        edges = []
    has_sdv_segment_edge = False
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        to_value = edge.get("to")
        if isinstance(to_value, str) and to_value == str(cidr):
            has_sdv_segment_edge = True
            break
    if not has_sdv_segment_edge:
        errors.append(f"network-matrix has no edge targeting SDV subnet {cidr}")

    return (len(errors) == 0), errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate websetup virtual setup consistency.")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root path (default: current directory)",
    )
    parser.add_argument(
        "--inventory",
        default="websetup/virtual/inventory.csv",
        help="Relative path to virtual inventory CSV",
    )
    parser.add_argument(
        "--network-matrix",
        default="websetup/virtual/network-matrix.json",
        help="Relative path to network matrix JSON",
    )
    parser.add_argument(
        "--manifest",
        default="websetup/sdv/manifest.json",
        help="Relative path to SDV manifest JSON",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    ok, errors = validate_virtual_setup(
        inventory_path=(repo_root / args.inventory).resolve(),
        network_matrix_path=(repo_root / args.network_matrix).resolve(),
        manifest_path=(repo_root / args.manifest).resolve(),
    )
    if ok:
        print("[virtual-setup] OK: inventory, network-matrix, and SDV manifest are consistent")
        return 0
    for issue in errors:
        print(f"[virtual-setup] ERROR: {issue}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
