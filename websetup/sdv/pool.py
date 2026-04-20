"""Validate SDV network plan consistency for 10.11.8.0/24."""

from __future__ import annotations

import ipaddress
from typing import Mapping


def _parse_ip(value: str) -> ipaddress.IPv4Address:
    return ipaddress.ip_address(value.split("/")[0])


def _parse_last_octet(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("empty IP/range value")
        if "." in text:
            return int(_parse_ip(text).packed[-1])
        return int(text)
    raise ValueError(f"unsupported range value type: {type(value)!r}")


def validate_network(manifest: Mapping[str, object]) -> tuple[bool, str]:
    network = manifest.get("network")
    if not isinstance(network, Mapping):
        return False, "manifest.network missing"

    subnet = network.get("subnet_cidr")
    reserved = network.get("reserved_br_int")
    assigned = network.get("script_assigned")
    alloc = network.get("allocatable_range")
    alloc = network.get("allocatable_range") or network.get("allocatable_pool")
    alloc = network.get("allocatable_pool")
    if not isinstance(subnet, str) or not isinstance(reserved, str):
        return False, "subnet_cidr/reserved_br_int invalid"
    if not isinstance(assigned, Mapping):
        return False, "script_assigned missing/invalid"
    if not isinstance(alloc, Mapping):
        return False, "allocatable_range missing/invalid"
        return False, "allocatable_pool missing/invalid"

    cidr = ipaddress.ip_network(subnet, strict=True)
    reserved_ip = _parse_ip(reserved)
    if reserved_ip not in cidr or reserved_ip != ipaddress.ip_address("10.11.8.1"):
        return False, f"reserved_br_int must be 10.11.8.1 in {cidr}"

    expected = {
        "veth0": ipaddress.ip_address("10.11.8.50"),
        "peer0": ipaddress.ip_address("10.11.8.51"),
        "veth1": ipaddress.ip_address("10.11.8.52"),
        "peer1": ipaddress.ip_address("10.11.8.53"),
    }
    for iface, exp in expected.items():
        value = assigned.get(iface)
        if not isinstance(value, str):
            return False, f"script_assigned.{iface} missing"
        actual = _parse_ip(value)
        if actual != exp or actual not in cidr:
            return False, f"script_assigned.{iface} expected {exp}, got {actual}"

    start_raw = alloc.get("start")
    end_raw = alloc.get("end")
    try:
        start = _parse_last_octet(start_raw)
        end = _parse_last_octet(end_raw)
    except ValueError as exc:
        return False, f"allocatable_range.start/end invalid: {exc}"
    if (start, end) != (54, 254):
        return False, f"allocatable_range expected 54..254, got {start}..{end}"
    start = alloc.get("start")
    end = alloc.get("end")
    if not isinstance(start, int) or not isinstance(end, int):
        return False, "allocatable_pool.start/end must be integers"
    if (start, end) != (54, 254):
        return False, f"allocatable_pool expected 54..254, got {start}..{end}"

    return True, "manifest network block OK"
