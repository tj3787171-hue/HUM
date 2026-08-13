#!/usr/bin/env python3
"""Plan the laptop-to-desktop bind-bridge from present ISO/DMG artifacts.

Penguin/Chromebook and the desktop server area (HUM at 192.168.68.53) share a
logical bind-bridge. Tokens are derived from amd64 installer ISOs, Darwin
kernel.dmg, and any other present .iso files. The bridge path is intended to
run under snapper-timeline.service / snapperd.service and fwupd.service so
phpsessionclean.service and apt-listchanges.service stay off this path.

This planner is non-destructive by default: it inventories images, mints
tokens, probes TCP/UDP, and can emit systemd unit snippets into a staging
directory. It does not install units into /etc or create host bridges unless
those files are copied by the operator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import stat
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LAPTOP_NODE = "local-laptop-dev"
PENGUIN_NODE = "penguin"
DESKTOP_NODE = "desktop-server"
DESKTOP_ALIAS_OF = "HUM"
DEFAULT_DESKTOP_HOST = "192.168.68.53"
DEFAULT_GATEWAY = "192.168.68.51"

ALLOWED_UNITS = (
    "snapper-timeline.service",
    "snapperd.service",
    "fwupd.service",
    "fwupd-refresh.service",
)
DENIED_UNITS = (
    "phpsessionclean.service",
    "apt-listchanges.service",
)
# apt-listchanges is Perl and historically After=plymouth-quit-wait.service.
PERL_BOOT_UNIT = "apt-listchanges.service"
PLYMOUTH_WAIT_UNIT = "plymouth-quit-wait.service"
PLYMOUTH_QUIT_UNIT = "plymouth-quit.service"
PLYMOUTH_START_UNIT = "plymouth-start.service"
PLYMOUTH_MODES = ("join", "mask")
DEFAULT_PLYMOUTH_MODE = "join"
PLYMOUTH_WAIT_TIMEOUT_SEC = 20

FWUPD_TCP_PORTS = (443, 80)
FWUPD_UDP_PORTS = (5353,)
DESKTOP_TCP_PROBE_PORTS = (22, 443)

DEFAULT_SEARCH_PATHS = (
    "dist",
    "data/iso-output",
    "iso-build",
    "/iso-staging",
    "/iso-output",
    "/host-downloads",
    "/mnt/virtual-drive",
    "~/Downloads",
    "/mnt/chromeos/MyFiles/Downloads",
)

ISO_SUFFIXES = {".iso"}
DMG_SUFFIXES = {".dmg"}
IMAGE_SUFFIXES = ISO_SUFFIXES | DMG_SUFFIXES | {".img"}
HASH_WINDOW = 1024 * 1024


@dataclass
class ImageArtifact:
    path: str
    name: str
    suffix: str
    size_bytes: int
    role: str
    fingerprint: str
    exists: bool = True


@dataclass
class BindBridgePlan:
    timestamp_utc: str
    laptop_nodes: list[str]
    desktop_node: str
    desktop_host: str
    gateway: str
    token: str
    artifacts: list[dict[str, Any]]
    units_allow: list[str]
    units_deny: list[str]
    fwupd_tcp_ports: list[int]
    fwupd_udp_ports: list[int]
    plymouth_mode: str = DEFAULT_PLYMOUTH_MODE
    plymouth_wait_timeout_sec: int = PLYMOUTH_WAIT_TIMEOUT_SEC
    plymouth_gate: str = PLYMOUTH_WAIT_UNIT
    probes: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory ISO/DMG artifacts and mint laptop-desktop bind-bridge "
            "tokens for the snapper/fwupd path."
        ),
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="plan",
        choices=("plan", "status", "emit-units"),
        help="plan (default), status, or emit-units",
    )
    parser.add_argument(
        "--search",
        action="append",
        default=[],
        help="Directory to search for .iso/.dmg files. Repeatable.",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root used to resolve relative search paths.",
    )
    parser.add_argument(
        "--desktop-host",
        default=DEFAULT_DESKTOP_HOST,
        help=f"Desktop server IPv4 (default: {DEFAULT_DESKTOP_HOST}).",
    )
    parser.add_argument(
        "--output",
        default="diagnostics/bind-bridge-plan.json",
        help="JSON plan output path (default: diagnostics/bind-bridge-plan.json).",
    )
    parser.add_argument(
        "--units-dir",
        default="diagnostics/bind-bridge-units",
        help="Directory for emitted systemd snippets (emit-units).",
    )
    parser.add_argument(
        "--plymouth",
        choices=PLYMOUTH_MODES,
        default=DEFAULT_PLYMOUTH_MODE,
        help=(
            "join (default): timeout plymouth-quit-wait and order it into the "
            "unit field. mask: document masking it on headless/Penguin hosts."
        ),
    )
    parser.add_argument(
        "--no-probe",
        action="store_true",
        help="Skip TCP/UDP connectivity probes.",
    )
    parser.add_argument(
        "--probe-timeout",
        type=float,
        default=1.0,
        help="Per-port probe timeout in seconds (default: 1.0).",
    )
    return parser.parse_args(argv)


def classify_image(path: Path) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if suffix in ISO_SUFFIXES:
        if "amd64" in name or "x86_64" in name:
            return "linux-amd64-iso"
        return "iso-image"
    if suffix in DMG_SUFFIXES:
        if "kernel" in name or "darwin" in name:
            return "darwin-kernel-dmg"
        return "darwin-disk-image"
    if suffix == ".img":
        return "disk-image"
    return "unknown-image"


def fingerprint_file(path: Path, window: int = HASH_WINDOW) -> str:
    digest = hashlib.sha256()
    size = path.stat().st_size
    digest.update(f"{size}\n".encode("utf-8"))
    with path.open("rb") as handle:
        head = handle.read(window)
        digest.update(head)
        if size > window:
            handle.seek(max(0, size - window))
            digest.update(handle.read(window))
    return digest.hexdigest()


def iter_image_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    found: list[Path] = []
    try:
        entries = list(directory.iterdir())
    except OSError:
        return []
    for entry in entries:
        if not entry.is_file():
            continue
        if entry.suffix.lower() in IMAGE_SUFFIXES:
            found.append(entry)
    found.sort(key=lambda item: item.name.lower())
    return found


def discover_artifacts(search_paths: list[Path]) -> list[ImageArtifact]:
    artifacts: list[ImageArtifact] = []
    seen: set[str] = set()
    for directory in search_paths:
        for path in iter_image_files(directory):
            resolved = str(path.resolve()) if path.exists() else str(path)
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                size = path.stat().st_size
                digest = fingerprint_file(path)
            except OSError:
                continue
            artifacts.append(
                ImageArtifact(
                    path=resolved,
                    name=path.name,
                    suffix=path.suffix.lower(),
                    size_bytes=size,
                    role=classify_image(path),
                    fingerprint=digest,
                )
            )
    return artifacts


def mint_token(
    *,
    laptop_nodes: list[str],
    desktop_node: str,
    desktop_host: str,
    artifacts: list[ImageArtifact],
    units_allow: tuple[str, ...] = ALLOWED_UNITS,
    units_deny: tuple[str, ...] = DENIED_UNITS,
) -> str:
    payload = {
        "laptop_nodes": laptop_nodes,
        "desktop_node": desktop_node,
        "desktop_host": desktop_host,
        "artifacts": [
            {"name": item.name, "role": item.role, "fingerprint": item.fingerprint}
            for item in artifacts
        ],
        "units_allow": list(units_allow),
        "units_deny": list(units_deny),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"HUM-BIND-{digest[:20]}"


def probe_tcp(host: str, port: int, timeout: float) -> dict[str, Any]:
    result: dict[str, Any] = {
        "protocol": "tcp",
        "host": host,
        "port": port,
        "ok": False,
        "error": None,
    }
    try:
        with socket.create_connection((host, port), timeout=timeout):
            result["ok"] = True
    except OSError as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def probe_udp(host: str, port: int, timeout: float) -> dict[str, Any]:
    result: dict[str, Any] = {
        "protocol": "udp",
        "host": host,
        "port": port,
        "ok": False,
        "error": None,
        "note": "UDP send is best-effort; a quiet drop is common on Crostini.",
    }
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(timeout)
        sock.sendto(b"", (host, port))
        result["ok"] = True
    except OSError as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        sock.close()
    return result


def collect_probes(desktop_host: str, timeout: float) -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []
    for port in DESKTOP_TCP_PROBE_PORTS:
        probes.append(probe_tcp(desktop_host, port, timeout))
    for port in FWUPD_TCP_PORTS:
        probes.append(probe_tcp(desktop_host, port, timeout))
    for port in FWUPD_UDP_PORTS:
        probes.append(probe_udp(desktop_host, port, timeout))
    return probes


def resolve_search_paths(repo_root: Path, extra: list[str]) -> list[Path]:
    raw = list(extra) if extra else list(DEFAULT_SEARCH_PATHS)
    resolved: list[Path] = []
    seen: set[str] = set()
    for item in raw:
        path = Path(item).expanduser()
        if not path.is_absolute():
            path = repo_root / path
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        resolved.append(path)
    return resolved


def build_warnings(artifacts: list[ImageArtifact], probes: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    roles = {item.role for item in artifacts}
    if "linux-amd64-iso" not in roles:
        warnings.append("No amd64 ISO found in search paths.")
    if "darwin-kernel-dmg" not in roles:
        warnings.append("No Darwin kernel.dmg found in search paths.")
    if not artifacts:
        warnings.append("No .iso/.dmg artifacts present; token is topology-only.")
    tcp_fail = [
        probe
        for probe in probes
        if probe.get("protocol") == "tcp" and not probe.get("ok")
    ]
    udp_fail = [
        probe
        for probe in probes
        if probe.get("protocol") == "udp" and not probe.get("ok")
    ]
    if tcp_fail:
        warnings.append(
            "TCP probes to the desktop server area failed; fwupd LVFS (443/80) "
            "and SSH (22) need a working TCP path."
        )
    if udp_fail:
        warnings.append(
            "UDP probes failed; fwupd local device discovery (UDP 5353) may be "
            "blocked. Prefer TCP 443 for LVFS and keep php/apt units off this bridge."
        )
    return warnings


def recommended_actions(
    artifacts: list[ImageArtifact],
    plymouth_mode: str = DEFAULT_PLYMOUTH_MODE,
) -> list[str]:
    actions = [
        "Keep snapper-timeline.service and snapperd.service on the bind-bridge path.",
        "Involve fwupd.service for firmware TCP/UDP; do not route it through apt-listchanges.",
        "Mask or avoid phpsessionclean.service on this bridge so PHP session GC stays local.",
        (
            "Do not After=plymouth-quit-wait.service on the bind-bridge; its "
            "default TimeoutStartSec=infinity is the boot hold-up."
        ),
        (
            "apt-listchanges.service is Perl and was designed to run after "
            "plymouth-quit-wait; keep it Conflicts= on this field."
        ),
        "Emit units with: python3 scripts/hum_bind_bridge.py emit-units",
    ]
    if plymouth_mode == "mask":
        actions.append(
            "Headless/Penguin: systemctl mask plymouth-quit-wait.service "
            "plymouth-start.service"
        )
    else:
        actions.append(
            f"Join mode: drop-in TimeoutStartSec={PLYMOUTH_WAIT_TIMEOUT_SEC}s on "
            "plymouth-quit-wait.service and After=plymouth-quit.service on the bridge."
        )
    if any(item.role == "linux-amd64-iso" for item in artifacts):
        actions.append("Use the discovered amd64 ISO as the Linux side of the bind token.")
    if any(item.role == "darwin-kernel-dmg" for item in artifacts):
        actions.append("Use Darwin kernel.dmg as the macOS-side bind token input.")
    if any(item.suffix == ".iso" and item.role == "iso-image" for item in artifacts):
        actions.append("Include other present .iso files in the same token set.")
    return actions


def build_plan(
    *,
    search_paths: list[Path],
    desktop_host: str,
    probe: bool,
    probe_timeout: float,
    plymouth_mode: str = DEFAULT_PLYMOUTH_MODE,
) -> BindBridgePlan:
    artifacts = discover_artifacts(search_paths)
    laptop_nodes = [LAPTOP_NODE, PENGUIN_NODE]
    token = mint_token(
        laptop_nodes=laptop_nodes,
        desktop_node=DESKTOP_NODE,
        desktop_host=desktop_host,
        artifacts=artifacts,
    )
    probes = collect_probes(desktop_host, probe_timeout) if probe else []
    return BindBridgePlan(
        timestamp_utc=utc_now(),
        laptop_nodes=laptop_nodes,
        desktop_node=DESKTOP_NODE,
        desktop_host=desktop_host,
        gateway=DEFAULT_GATEWAY,
        token=token,
        artifacts=[asdict(item) for item in artifacts],
        units_allow=list(ALLOWED_UNITS),
        units_deny=list(DENIED_UNITS),
        fwupd_tcp_ports=list(FWUPD_TCP_PORTS),
        fwupd_udp_ports=list(FWUPD_UDP_PORTS),
        plymouth_mode=plymouth_mode,
        plymouth_wait_timeout_sec=PLYMOUTH_WAIT_TIMEOUT_SEC,
        plymouth_gate=PLYMOUTH_WAIT_UNIT,
        probes=probes,
        warnings=build_warnings(artifacts, probes),
        recommended_actions=recommended_actions(artifacts, plymouth_mode),
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def unit_bind_bridge(plan: BindBridgePlan, repo_root: Path) -> str:
    script = (repo_root / "scripts" / "hum_bind_bridge.py").resolve()
    wants = " ".join(plan.units_allow)
    conflicts = " ".join(plan.units_deny)
    return f"""[Unit]
Description=HUM laptop-desktop bind-bridge ({plan.token})
Documentation=file://{repo_root}/README.md
After=network-online.target snapperd.service {PLYMOUTH_QUIT_UNIT}
Wants={wants}
Conflicts={conflicts}
# Do not After={PLYMOUTH_WAIT_UNIT}: default TimeoutStartSec=infinity holds the field.
# {PERL_BOOT_UNIT} is Perl and was designed on that wait job; keep it off this path.

[Service]
Type=oneshot
RemainAfterExit=yes
Environment=HUM_BIND_TOKEN={plan.token}
Environment=HUM_BIND_DESKTOP={plan.desktop_host}
ExecStart=/usr/bin/python3 {script} status --no-probe --repo-root {repo_root}

[Install]
WantedBy=multi-user.target
"""


def unit_fwupd_dropin(plan: BindBridgePlan) -> str:
    tcp = ",".join(str(port) for port in plan.fwupd_tcp_ports)
    udp = ",".join(str(port) for port in plan.fwupd_udp_ports)
    return f"""[Unit]
Description=HUM bind-bridge fwupd TCP/UDP involvement
After=hum-bind-bridge.service snapperd.service
Wants=hum-bind-bridge.service
Conflicts=phpsessionclean.service apt-listchanges.service

[Service]
# LVFS uses HTTPS TCP {tcp}. Local device discovery may use UDP {udp}.
# Prior UDP/TCP failures on this LAN should not fall back to apt-listchanges.
Environment=HUM_BIND_TOKEN={plan.token}
"""


def unit_snapper_dropin(plan: BindBridgePlan, title: str) -> str:
    return f"""[Unit]
Description=HUM bind-bridge {title}
Wants=hum-bind-bridge.service
Before=phpsessionclean.service {PERL_BOOT_UNIT}
Conflicts=phpsessionclean.service {PERL_BOOT_UNIT}

[Service]
Environment=HUM_BIND_TOKEN={plan.token}
"""


def unit_plymouth_wait_dropin(plan: BindBridgePlan) -> str:
    return f"""[Unit]
Description=HUM: bound Plymouth wait so it cannot hold the bind-bridge field
Before=hum-bind-bridge.service snapperd.service fwupd.service
Conflicts=phpsessionclean.service {PERL_BOOT_UNIT}

[Service]
# Vendor default is TimeoutStartSec=infinity ("Hold until boot process finishes up").
TimeoutStartSec={plan.plymouth_wait_timeout_sec}s
"""


def unit_plymouth_quit_dropin(plan: BindBridgePlan) -> str:
    return f"""[Unit]
Description=HUM: quit Plymouth so wait cannot block snapper/fwupd
Before=hum-bind-bridge.service
Wants=hum-bind-bridge.service
Conflicts={PERL_BOOT_UNIT}

[Service]
Environment=HUM_BIND_TOKEN={plan.token}
"""


def plymouth_mask_instructions(plan: BindBridgePlan) -> str:
    return (
        "# Headless / Penguin: remove the Plymouth wait job from the boot field.\n"
        "# Do not mask this on a graphical Kali desktop that still uses a splash.\n"
        f"# Token: {plan.token}\n"
        "systemctl mask "
        f"{PLYMOUTH_WAIT_UNIT} {PLYMOUTH_START_UNIT}\n"
        "systemctl daemon-reload\n"
    )


def emit_units(plan: BindBridgePlan, units_dir: Path, repo_root: Path) -> list[str]:
    units_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    files = {
        "hum-bind-bridge.service": unit_bind_bridge(plan, repo_root),
        "fwupd.service.d/hum-bind-bridge.conf": unit_fwupd_dropin(plan),
        "snapper-timeline.service.d/hum-bind-bridge.conf": unit_snapper_dropin(
            plan, "snapper timeline ownership"
        ),
        "snapperd.service.d/hum-bind-bridge.conf": unit_snapper_dropin(
            plan, "snapperd ownership"
        ),
        "plymouth-quit-wait.service.d/hum-bind-bridge.conf": unit_plymouth_wait_dropin(
            plan
        ),
        "plymouth-quit.service.d/hum-bind-bridge.conf": unit_plymouth_quit_dropin(plan),
    }
    if plan.plymouth_mode == "mask":
        files["MASK-plymouth.cmds"] = plymouth_mask_instructions(plan)
    for relative, content in files.items():
        path = units_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        os.chmod(path, stat.S_IMODE(path.stat().st_mode) | stat.S_IRUSR)
        written.append(str(path))
    return written


def format_status(plan: BindBridgePlan) -> str:
    lines = [
        f"Token:          {plan.token}",
        f"Laptop nodes:   {', '.join(plan.laptop_nodes)}",
        f"Desktop:        {plan.desktop_node} ({plan.desktop_host}) via {plan.gateway}",
        f"Allow units:    {', '.join(plan.units_allow)}",
        f"Deny units:     {', '.join(plan.units_deny)}",
        f"fwupd TCP:      {', '.join(str(port) for port in plan.fwupd_tcp_ports)}",
        f"fwupd UDP:      {', '.join(str(port) for port in plan.fwupd_udp_ports)}",
        f"Plymouth:       {plan.plymouth_mode} gate={plan.plymouth_gate} "
        f"timeout={plan.plymouth_wait_timeout_sec}s",
        f"Artifacts:      {len(plan.artifacts)}",
    ]
    for item in plan.artifacts:
        lines.append(
            f"  - {item['role']}: {item['name']} ({item['size_bytes']} bytes)"
        )
    if plan.warnings:
        lines.append("Warnings:")
        for warning in plan.warnings:
            lines.append(f"  - {warning}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).expanduser().resolve()
    search_paths = resolve_search_paths(repo_root, args.search)
    plan = build_plan(
        search_paths=search_paths,
        desktop_host=args.desktop_host,
        probe=not args.no_probe,
        probe_timeout=args.probe_timeout,
        plymouth_mode=args.plymouth,
    )
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = repo_root / output_path
    write_json(output_path, plan.to_dict())

    if args.command == "emit-units":
        units_dir = Path(args.units_dir)
        if not units_dir.is_absolute():
            units_dir = repo_root / units_dir
        written = emit_units(plan, units_dir, repo_root)
        print(format_status(plan))
        print(f"Plan written: {output_path}")
        print("Emitted units:")
        for path in written:
            print(f"  {path}")
        print("Copy into /etc/systemd/system/ only after reviewing Conflicts= lines.")
        return 0

    print(format_status(plan))
    print(f"Plan written: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
