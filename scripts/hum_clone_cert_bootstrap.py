#!/usr/bin/env python3
"""Begin HUM clone-path and authenticated-cert variable bootstrap.

Required clone directories and TLS path variables must be declared before
ISO/DMG bind-bridge work or HTTPS serving. Certificate *contents* stay on
disk outside git; this tool only checks paths and environment names.

Typical start (Penguin/zsh or a desktop clone):

  cp .devcontainer/dev.env.example .devcontainer/dev.env
  chmod 600 .devcontainer/dev.env
  # edit clone root + HUM_TLS_* / SSL_CERT_FILE / GIT_SSL_CAINFO paths
  bash .devcontainer/import-environment.sh
  python3 scripts/hum_clone_cert_bootstrap.py begin
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_CLONE_ROOT = "~/src"
CERT_PATH_VARS = (
    "HUM_TLS_CERT",
    "HUM_TLS_KEY",
    "HUM_TLS_CA",
    "SSL_CERT_FILE",
    "GIT_SSL_CAINFO",
    "NODE_EXTRA_CA_CERTS",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
)
CLONE_PATH_VARS = (
    "HUM_CLONE_ROOT",
    "HUM_ISO_DIR",
    "HUM_DMG_DIR",
)
UNDERWAY_CERT_VARS = (
    "HUM_TLS_CERT",
    "HUM_TLS_CA",
    "SSL_CERT_FILE",
    "GIT_SSL_CAINFO",
    "NODE_EXTRA_CA_CERTS",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
)


@dataclass
class PathCheck:
    name: str
    value: str
    declared: bool
    exists: bool
    kind: str


@dataclass
class BeginReport:
    timestamp_utc: str
    clone_root: str
    clone_root_ready: bool
    cert_variables_underway: bool
    cert_files_ready: bool
    git_available: bool
    ca_certificates_hint: str
    paths: list[dict[str, Any]] = field(default_factory=list)
    certs: list[dict[str, Any]] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check clone directories and authenticated cert path variables "
            "before cloning dependencies or starting the bind-bridge."
        ),
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="begin",
        choices=("begin", "status"),
        help="begin (default) creates the clone root and reports cert readiness.",
    )
    parser.add_argument(
        "--output",
        default="diagnostics/clone-cert-begin.json",
        help="JSON report path (default: diagnostics/clone-cert-begin.json).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero unless clone root exists and cert files are present.",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root for relative output paths.",
    )
    return parser.parse_args(argv)


def env_path(name: str, default: str = "") -> str:
    raw = os.environ.get(name, default).strip()
    if not raw:
        return ""
    return str(Path(raw).expanduser())


def check_named_path(name: str, value: str, kind: str) -> PathCheck:
    declared = bool(value)
    exists = Path(value).exists() if declared else False
    return PathCheck(
        name=name,
        value=value,
        declared=declared,
        exists=exists,
        kind=kind,
    )


def ensure_clone_root(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return path.is_dir() and os.access(path, os.W_OK)


def collect_checks() -> tuple[list[PathCheck], list[PathCheck], Path]:
    clone_root_value = env_path("HUM_CLONE_ROOT", DEFAULT_CLONE_ROOT)
    clone_root = Path(clone_root_value)
    path_checks = [
        check_named_path("HUM_CLONE_ROOT", clone_root_value, "clone-root"),
    ]
    for name in CLONE_PATH_VARS:
        if name == "HUM_CLONE_ROOT":
            continue
        path_checks.append(check_named_path(name, env_path(name), "clone-path"))
    cert_checks = [
        check_named_path(name, env_path(name), "cert-path") for name in CERT_PATH_VARS
    ]
    return path_checks, cert_checks, clone_root


def certs_underway(cert_checks: list[PathCheck]) -> bool:
    wanted = set(UNDERWAY_CERT_VARS)
    return any(item.declared and item.name in wanted for item in cert_checks)


def cert_files_ready(cert_checks: list[PathCheck]) -> bool:
    by_name = {item.name: item for item in cert_checks}
    pair = by_name["HUM_TLS_CERT"].exists and by_name["HUM_TLS_KEY"].exists
    ca_ready = any(
        by_name[name].exists
        for name in (
            "HUM_TLS_CA",
            "SSL_CERT_FILE",
            "GIT_SSL_CAINFO",
            "REQUESTS_CA_BUNDLE",
            "CURL_CA_BUNDLE",
            "NODE_EXTRA_CA_CERTS",
        )
    )
    return pair or ca_ready


def next_steps(
    *,
    clone_ready: bool,
    underway: bool,
    files_ready: bool,
) -> list[str]:
    steps = [
        "Copy .devcontainer/dev.env.example to .devcontainer/dev.env and chmod 600.",
        "Set HUM_CLONE_ROOT and authenticated cert *paths* (not PEM bodies).",
        "bash .devcontainer/import-environment.sh  # also hooks ~/.zshrc on Penguin",
        "sudo apt-get install -y ca-certificates git",
    ]
    if not clone_ready:
        steps.append("Fix HUM_CLONE_ROOT so `begin` can create a writable clone directory.")
    if not underway:
        steps.append(
            "Declare at least HUM_TLS_CA or SSL_CERT_FILE / GIT_SSL_CAINFO "
            "(and HUM_TLS_CERT/HUM_TLS_KEY for HTTPS serving)."
        )
    if underway and not files_ready:
        steps.append("Place cert/key/CA files at the declared paths, then re-run begin.")
    if files_ready:
        steps.append("python3 scripts/hum_bind_bridge.py plan --no-probe")
        steps.append(
            "python3 scripts/https-file-server.py 8443 --cert \"$HUM_TLS_CERT\" "
            "--key \"$HUM_TLS_KEY\" --directory data/iso-output"
        )
    return steps


def build_report(create_root: bool) -> BeginReport:
    path_checks, cert_checks, clone_root = collect_checks()
    clone_ready = clone_root.is_dir() and os.access(clone_root, os.W_OK)
    if create_root and not clone_ready:
        clone_ready = ensure_clone_root(clone_root)
        path_checks[0] = check_named_path(
            "HUM_CLONE_ROOT",
            str(clone_root),
            "clone-root",
        )
    underway = certs_underway(cert_checks)
    files_ready = cert_files_ready(cert_checks)
    warnings: list[str] = []
    if not underway:
        warnings.append(
            "Authenticated cert variables are not underway; declare path env vars first."
        )
    elif not files_ready:
        warnings.append(
            "Cert variables are declared but files are not on disk yet (underway, not ready)."
        )
    if not clone_ready:
        warnings.append(f"Clone root is not writable: {clone_root}")
    return BeginReport(
        timestamp_utc=utc_now(),
        clone_root=str(clone_root),
        clone_root_ready=clone_ready,
        cert_variables_underway=underway,
        cert_files_ready=files_ready,
        git_available=shutil.which("git") is not None,
        ca_certificates_hint="sudo apt-get install -y ca-certificates git",
        paths=[asdict(item) for item in path_checks],
        certs=[asdict(item) for item in cert_checks],
        next_steps=next_steps(
            clone_ready=clone_ready,
            underway=underway,
            files_ready=files_ready,
        ),
        warnings=warnings,
    )


def format_text(report: BeginReport) -> str:
    lines = [
        f"Clone root:     {report.clone_root} ready={str(report.clone_root_ready).lower()}",
        f"Cert underway:  {str(report.cert_variables_underway).lower()}",
        f"Cert files:     {str(report.cert_files_ready).lower()}",
        f"git on PATH:    {str(report.git_available).lower()}",
        f"OS trust:       {report.ca_certificates_hint}",
    ]
    declared = [item for item in report.certs if item["declared"]]
    if declared:
        lines.append("Declared cert vars:")
        for item in declared:
            state = "present" if item["exists"] else "missing-file"
            lines.append(f"  - {item['name']}={item['value']} ({state})")
    else:
        lines.append("Declared cert vars: none")
    if report.warnings:
        lines.append("Warnings:")
        for warning in report.warnings:
            lines.append(f"  - {warning}")
    lines.append("Begin with:")
    for step in report.next_steps[:4]:
        lines.append(f"  - {step}")
    return "\n".join(lines)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).expanduser().resolve()
    report = build_report(create_root=args.command == "begin")
    output = Path(args.output)
    if not output.is_absolute():
        output = repo_root / output
    write_json(output, report.to_dict())
    print(format_text(report))
    print(f"Report written: {output}")
    if args.strict and (not report.clone_root_ready or not report.cert_files_ready):
        return 1
    if not report.cert_variables_underway:
        return 2
    if not report.clone_root_ready:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
