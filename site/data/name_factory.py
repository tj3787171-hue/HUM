#!/usr/bin/env python3
"""
name_factory.py — House of Corps data naming, hierarchy, and aggregation engine.

Combines all HUM data sources (topology, recup manifest/summary, mock logs,
comments, drop-camp bands) into a unified 'House of Corps' collective data
product. Applies the 'wanted comb' hierarchy for reachability, velocity,
and mission scoring. Outputs:

  - corps.json          → the House of Corps collective dataset
  - sources.list        → flat manifest of all input data sources
  - FINAL-PRODUCT/      → gram & comb Palace of Web output files
"""

import json
import os
import sys
import hashlib
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE.parent
RECUP_HOME = Path(os.environ.get("RECUP_HOME", "/home/troy"))

# ---------------------------------------------------------------------------
# Data source loaders
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict | list | None:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return None


def load_topology() -> dict:
    return load_json(HERE / "topology.json") or {}


def load_recup_manifest() -> list:
    return load_json(RECUP_HOME / "recup_manifest.json") or []


def load_recup_summary() -> dict:
    return load_json(RECUP_HOME / "recup_summary.json") or {}


def scan_recup_tree(base: Path) -> list[dict]:
    items = []
    if not base.is_dir():
        return items
    for sub in sorted(base.iterdir()):
        if sub.is_dir():
            files = sorted(f.name for f in sub.iterdir() if f.is_file())
            items.append({"category": sub.name, "files": files, "count": len(files)})
    return items

# ---------------------------------------------------------------------------
# Mock / synthetic data generators (test logs, comments, drop-camp bands)
# ---------------------------------------------------------------------------

def generate_mock_logs() -> list[dict]:
    """Synthetic test and mock log entries representing banded data."""
    ts = datetime.now(timezone.utc).isoformat()
    return [
        {"id": "log-001", "type": "test",    "message": "Container origin verified: hum.org",      "timestamp": ts, "band": "alpha"},
        {"id": "log-002", "type": "mock",    "message": "NETNS veth peer scan completed",          "timestamp": ts, "band": "alpha"},
        {"id": "log-003", "type": "comment", "message": "Recup import pipeline initialized",       "timestamp": ts, "band": "beta"},
        {"id": "log-004", "type": "test",    "message": "Topology JSON/XML sync validated",        "timestamp": ts, "band": "beta"},
        {"id": "log-005", "type": "drop",    "message": "Dropped packet analysis: 0% loss on lo",  "timestamp": ts, "band": "gamma"},
        {"id": "log-006", "type": "camp",    "message": "Camp baseline: eth0 UP 172.30.0.2/24",    "timestamp": ts, "band": "gamma"},
        {"id": "log-007", "type": "comment", "message": "Palace of Web assembly started",          "timestamp": ts, "band": "delta"},
        {"id": "log-008", "type": "test",    "message": "Name factory hierarchy pass complete",     "timestamp": ts, "band": "delta"},
    ]

# ---------------------------------------------------------------------------
# Wanted Comb — hierarchy scoring for reachability, velocity, mission
# ---------------------------------------------------------------------------

BAND_WEIGHTS = {"alpha": 4, "beta": 3, "gamma": 2, "delta": 1}

def score_reachability(item: dict) -> float:
    """How reachable is this data? Based on source proximity and type."""
    base = BAND_WEIGHTS.get(item.get("band", ""), 1) * 10
    if item.get("type") in ("test", "mock"):
        return min(base + 20, 100)
    return min(base + 10, 100)


def score_velocity(item: dict) -> float:
    """How fast can this data be processed/served?"""
    type_v = {"test": 90, "mock": 85, "comment": 70, "drop": 60, "camp": 65}
    return type_v.get(item.get("type", ""), 50)


def score_mission(item: dict) -> float:
    """How critical is this data to the HUM mission?"""
    band_m = {"alpha": 95, "beta": 80, "gamma": 65, "delta": 50}
    return band_m.get(item.get("band", ""), 40)


def apply_wanted_comb(logs: list[dict]) -> list[dict]:
    """Apply the wanted-comb hierarchy scoring to all log entries."""
    scored = []
    for item in logs:
        entry = dict(item)
        entry["reachability"] = score_reachability(item)
        entry["velocity"] = score_velocity(item)
        entry["mission"] = score_mission(item)
        entry["comb_score"] = round(
            (entry["reachability"] * 0.35 +
             entry["velocity"] * 0.30 +
             entry["mission"] * 0.35), 2
        )
        scored.append(entry)
    scored.sort(key=lambda x: x["comb_score"], reverse=True)
    return scored


def name_factory_tag(item: dict) -> str:
    """Generate a unique factory name tag for a data item."""
    raw = f"{item.get('id', '')}-{item.get('type', '')}-{item.get('band', '')}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:8]
    return f"HUM-{item.get('band', 'x').upper()}-{h}"

# ---------------------------------------------------------------------------
# House of Corps builder
# ---------------------------------------------------------------------------

def build_house_of_corps() -> dict:
    topology = load_topology()
    recup_manifest = load_recup_manifest()
    recup_summary = load_recup_summary()
    templates_tree = scan_recup_tree(RECUP_HOME / "TEMPLATES")
    photos_tree = scan_recup_tree(RECUP_HOME / "PHOTOS")
    mock_logs = generate_mock_logs()

    scored_logs = apply_wanted_comb(mock_logs)
    for entry in scored_logs:
        entry["factory_tag"] = name_factory_tag(entry)

    recup_items = []
    for item in recup_manifest:
        recup_items.append({
            "file": item.get("file", ""),
            "source": item.get("source", ""),
            "class": item.get("class", ""),
            "factory_tag": f"HUM-RECUP-{hashlib.sha256(item.get('file', '').encode()).hexdigest()[:8]}",
        })

    iface_items = []
    for iface in topology.get("interfaces", []):
        iface_items.append({
            "name": iface["name"],
            "state": iface["state"],
            "addresses": iface.get("addresses", []),
            "factory_tag": f"HUM-NET-{hashlib.sha256(iface['name'].encode()).hexdigest()[:8]}",
        })

    ts = datetime.now(timezone.utc).isoformat()

    corps = {
        "house_of_corps": {
            "origin": recup_summary.get("origin", os.environ.get("HUM_ORIGIN", "hum.org")),
            "timestamp": ts,
            "version": "1.0.0",
            "name_factory": "HUM Name Factory v1",
            "description": "Collective data after the Name Factory — reachability, velocity, and mission scored",
        },
        "topology": {
            "hostname": topology.get("hostname", "hum-lab"),
            "interfaces": iface_items,
            "routes": topology.get("routes", []),
            "veth_peers": topology.get("veth_peers", []),
            "namespaces": topology.get("namespaces", []),
        },
        "recup": {
            "summary": recup_summary,
            "templates": templates_tree,
            "photos": photos_tree,
            "manifest": recup_items,
        },
        "wanted_comb": {
            "description": "Test/mock/log/comment/drop-camp banded data scored by reachability, velocity, mission",
            "bands": list(BAND_WEIGHTS.keys()),
            "entries": scored_logs,
        },
        "gram_comb_totals": {
            "topology_interfaces": len(iface_items),
            "topology_routes": len(topology.get("routes", [])),
            "recup_files": len(recup_items),
            "wanted_comb_entries": len(scored_logs),
            "templates_categories": len(templates_tree),
            "photos_categories": len(photos_tree),
            "total_data_points": (
                len(iface_items) + len(topology.get("routes", [])) +
                len(recup_items) + len(scored_logs) +
                sum(c["count"] for c in templates_tree) +
                sum(c["count"] for c in photos_tree)
            ),
        },
    }
    return corps

# ---------------------------------------------------------------------------
# Sources list builder
# ---------------------------------------------------------------------------

def build_sources_list(corps: dict) -> str:
    lines = [
        "# sources.list — HUM.org House of Corps data source manifest",
        f"# Generated: {corps['house_of_corps']['timestamp']}",
        f"# Origin: {corps['house_of_corps']['origin']}",
        "",
        "## Topology Sources",
        f"  topology.json          {HERE / 'topology.json'}",
        f"  topology.xml           {HERE / 'topology.xml'}",
        "",
        "## Recup Sources",
        f"  recup_manifest.json    {RECUP_HOME / 'recup_manifest.json'}",
        f"  recup_summary.json     {RECUP_HOME / 'recup_summary.json'}",
        f"  TEMPLATES/             {RECUP_HOME / 'TEMPLATES'}",
        f"  PHOTOS/                {RECUP_HOME / 'PHOTOS'}",
        "",
        "## Wanted Comb Sources",
        "  mock_logs              (generated: test, mock, comment, drop, camp)",
        "  bands                  alpha, beta, gamma, delta",
        "",
        "## FINAL-PRODUCT Output",
        f"  corps.json             {HERE / 'corps.json'}",
        f"  sources.list           {HERE / 'sources.list'}",
        f"  FINAL-PRODUCT/         {HERE / 'FINAL-PRODUCT/'}",
        "",
        f"## Totals",
    ]
    totals = corps.get("gram_comb_totals", {})
    for k, v in totals.items():
        lines.append(f"  {k:30s} {v}")
    lines.append("")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# FINAL-PRODUCT gram & comb output
# ---------------------------------------------------------------------------

def write_final_product(corps: dict):
    fp_dir = HERE / "FINAL-PRODUCT"
    fp_dir.mkdir(exist_ok=True)

    (fp_dir / "corps_full.json").write_text(json.dumps(corps, indent=2))

    gram = {
        "origin": corps["house_of_corps"]["origin"],
        "timestamp": corps["house_of_corps"]["timestamp"],
        "totals": corps["gram_comb_totals"],
        "top_scored": corps["wanted_comb"]["entries"][:5] if corps["wanted_comb"]["entries"] else [],
    }
    (fp_dir / "gram.json").write_text(json.dumps(gram, indent=2))

    comb_entries = []
    for e in corps["wanted_comb"]["entries"]:
        comb_entries.append({
            "tag": e["factory_tag"],
            "type": e["type"],
            "band": e["band"],
            "score": e["comb_score"],
            "message": e["message"],
        })
    for r in corps["recup"]["manifest"]:
        comb_entries.append({
            "tag": r["factory_tag"],
            "type": "recup",
            "band": r["class"].lower(),
            "score": 0,
            "message": f"{r['file']} from {r['source']}",
        })
    comb = {
        "origin": corps["house_of_corps"]["origin"],
        "timestamp": corps["house_of_corps"]["timestamp"],
        "comb_hierarchy": comb_entries,
    }
    (fp_dir / "comb.json").write_text(json.dumps(comb, indent=2))

    palace_data = {
        "palace_of_web": True,
        "origin": corps["house_of_corps"]["origin"],
        "timestamp": corps["house_of_corps"]["timestamp"],
        "name_factory": corps["house_of_corps"]["name_factory"],
        "total_data_points": corps["gram_comb_totals"]["total_data_points"],
        "sections": [
            {"id": "topology",    "label": "Network Topology",  "count": corps["gram_comb_totals"]["topology_interfaces"]},
            {"id": "recup",       "label": "Recup Recovery",    "count": corps["gram_comb_totals"]["recup_files"]},
            {"id": "wanted_comb", "label": "Wanted Comb",       "count": corps["gram_comb_totals"]["wanted_comb_entries"]},
            {"id": "templates",   "label": "Templates",         "count": corps["gram_comb_totals"]["templates_categories"]},
            {"id": "photos",      "label": "Photos",            "count": corps["gram_comb_totals"]["photos_categories"]},
        ],
    }
    (fp_dir / "palace.json").write_text(json.dumps(palace_data, indent=2))

    print(f"  FINAL-PRODUCT/corps_full.json")
    print(f"  FINAL-PRODUCT/gram.json")
    print(f"  FINAL-PRODUCT/comb.json")
    print(f"  FINAL-PRODUCT/palace.json")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("[name_factory] Building House of Corps...")
    corps = build_house_of_corps()

    corps_path = HERE / "corps.json"
    corps_path.write_text(json.dumps(corps, indent=2))
    print(f"  → {corps_path}")

    sources_path = HERE / "sources.list"
    sources_path.write_text(build_sources_list(corps))
    print(f"  → {sources_path}")

    print("[name_factory] Writing FINAL-PRODUCT gram & comb...")
    write_final_product(corps)

    totals = corps["gram_comb_totals"]
    print(f"\n[name_factory] House of Corps complete.")
    print(f"  Origin:           {corps['house_of_corps']['origin']}")
    print(f"  Data points:      {totals['total_data_points']}")
    print(f"  Interfaces:       {totals['topology_interfaces']}")
    print(f"  Routes:           {totals['topology_routes']}")
    print(f"  Recup files:      {totals['recup_files']}")
    print(f"  Wanted comb:      {totals['wanted_comb_entries']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
