#!/usr/bin/env python3
"""Collect NETNS, veth-peer, and interface data; emit JSON and XML for the HUM site."""

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from xml.dom import minidom

HERE = Path(__file__).resolve().parent


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def collect_interfaces() -> list[dict]:
    raw = _run(["ip", "-j", "addr"])
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def collect_routes() -> list[dict]:
    raw = _run(["ip", "-j", "route"])
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def collect_namespaces() -> list[str]:
    raw = _run(["ip", "netns", "list"])
    return [line.split()[0] for line in raw.splitlines() if line.strip()] if raw else []


def collect_docker_networks() -> list[dict]:
    raw = _run(["docker", "network", "ls", "--format", "{{json .}}"])
    nets = []
    for line in raw.splitlines():
        try:
            nets.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return nets


def collect_veth_peers() -> list[dict]:
    raw = _run(["ip", "-j", "link"])
    if not raw:
        return []
    try:
        links = json.loads(raw)
    except json.JSONDecodeError:
        return []
    peers = []
    for link in links:
        if "veth" in link.get("ifname", "") or link.get("link_type") == "ether":
            entry = {
                "ifname": link.get("ifname", ""),
                "ifindex": link.get("ifindex", 0),
                "operstate": link.get("operstate", "UNKNOWN"),
                "link_type": link.get("link_type", ""),
            }
            if "link_index" in link:
                entry["peer_ifindex"] = link["link_index"]
            peers.append(entry)
    return peers


def build_topology() -> dict:
    ifaces = collect_interfaces()
    routes = collect_routes()
    namespaces = collect_namespaces()
    docker_nets = collect_docker_networks()
    veth_peers = collect_veth_peers()

    iface_summaries = []
    for iface in ifaces:
        addrs = []
        for ai in iface.get("addr_info", []):
            addrs.append(f"{ai.get('local', '?')}/{ai.get('prefixlen', '?')}")
        iface_summaries.append({
            "name": iface.get("ifname", "?"),
            "state": iface.get("operstate", "UNKNOWN"),
            "mac": iface.get("address", ""),
            "addresses": addrs,
        })

    route_summaries = []
    for r in routes:
        route_summaries.append({
            "dst": r.get("dst", "default"),
            "gateway": r.get("gateway", ""),
            "dev": r.get("dev", ""),
        })

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hostname": _run(["hostname"]) or "hum-lab",
        "interfaces": iface_summaries,
        "routes": route_summaries,
        "namespaces": namespaces,
        "veth_peers": veth_peers,
        "docker_networks": docker_nets,
    }


def topology_to_xml(topo: dict) -> str:
    root = ET.Element("hum-topology", timestamp=topo["timestamp"], hostname=topo["hostname"])

    ifaces_el = ET.SubElement(root, "interfaces")
    for iface in topo["interfaces"]:
        ie = ET.SubElement(ifaces_el, "interface", name=iface["name"],
                           state=iface["state"], mac=iface["mac"])
        for addr in iface["addresses"]:
            ET.SubElement(ie, "address").text = addr

    routes_el = ET.SubElement(root, "routes")
    for r in topo["routes"]:
        ET.SubElement(routes_el, "route", dst=r["dst"],
                      gateway=r.get("gateway", ""), dev=r.get("dev", ""))

    ns_el = ET.SubElement(root, "namespaces")
    for ns in topo["namespaces"]:
        ET.SubElement(ns_el, "namespace").text = ns

    veths_el = ET.SubElement(root, "veth-peers")
    for v in topo["veth_peers"]:
        attrs = {"ifname": v["ifname"], "ifindex": str(v["ifindex"]),
                 "operstate": v["operstate"]}
        if "peer_ifindex" in v:
            attrs["peer_ifindex"] = str(v["peer_ifindex"])
        ET.SubElement(veths_el, "veth", **attrs)

    docker_el = ET.SubElement(root, "docker-networks")
    for dn in topo["docker_networks"]:
        ET.SubElement(docker_el, "network",
                      name=dn.get("Name", ""),
                      driver=dn.get("Driver", ""),
                      scope=dn.get("Scope", ""))

    rough = ET.tostring(root, encoding="unicode", xml_declaration=True)
    return minidom.parseString(rough).toprettyxml(indent="  ")


def main():
    topo = build_topology()

    json_path = HERE / "topology.json"
    json_path.write_text(json.dumps(topo, indent=2))

    xml_path = HERE / "topology.xml"
    xml_path.write_text(topology_to_xml(topo))

    print(f"Wrote {json_path} and {xml_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
