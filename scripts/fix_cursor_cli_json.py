#!/usr/bin/env python3
"""Repair Cursor Agent CLI project config that fails schema validation.

Running `agent` from $HOME (the default Penguin/Crostini prompt) treats
`~/.cursor/cli.json` as *project* config. That schema only allows
`version`, `editor`, and `permissions`. Global-only keys such as
`display` belong in `~/.cursor/cli-config.json`.

A typical Chromebook failure looks like:

    Invalid project config at /home/<user>/.cursor/cli.json:
    schema validation failed. unrecognized_keys: display

This tool migrates unrecognized top-level keys into the global config
and rewrites the project file to the allowed shape.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ALLOWED_KEYS = frozenset({"version", "editor", "permissions"})
EDITOR_ALLOWED_KEYS = frozenset({"vimMode"})
PERMISSIONS_ALLOWED_KEYS = frozenset({"allow", "deny"})


@dataclass
class RepairResult:
    project_path: Path
    global_path: Path
    needs_repair: bool
    unrecognized_keys: list[str] = field(default_factory=list)
    migrated_keys: list[str] = field(default_factory=list)
    backups: list[str] = field(default_factory=list)
    project_written: bool = False
    global_written: bool = False
    message: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_path": str(self.project_path),
            "global_path": str(self.global_path),
            "needs_repair": self.needs_repair,
            "unrecognized_keys": list(self.unrecognized_keys),
            "migrated_keys": list(self.migrated_keys),
            "backups": list(self.backups),
            "project_written": self.project_written,
            "global_written": self.global_written,
            "message": self.message,
            "error": self.error,
        }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Move global-only Cursor CLI keys (such as display) out of "
            "~/.cursor/cli.json and into ~/.cursor/cli-config.json."
        ),
    )
    parser.add_argument(
        "--home",
        default=os.path.expanduser("~"),
        help="Home directory that contains .cursor/ (default: $HOME).",
    )
    parser.add_argument(
        "--project-config",
        help="Explicit project cli.json path (overrides --home).",
    )
    parser.add_argument(
        "--global-config",
        help="Explicit global cli-config.json path (overrides --home).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the repair without writing files.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Report whether repair is needed without writing files.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print machine-readable JSON instead of text.",
    )
    return parser.parse_args(argv)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def cursor_paths(
    home: Path,
    project_config: Path | None = None,
    global_config: Path | None = None,
) -> tuple[Path, Path]:
    cursor_dir = home / ".cursor"
    project = project_config if project_config is not None else cursor_dir / "cli.json"
    glob = global_config if global_config is not None else cursor_dir / "cli-config.json"
    return project, glob


def load_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"expected a JSON object in {path}, got {type(raw).__name__}")
    return raw


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def unrecognized_project_keys(payload: dict[str, Any]) -> list[str]:
    keys = [key for key in payload if key not in PROJECT_ALLOWED_KEYS]
    keys.sort()
    return keys


def normalize_project_payload(source: dict[str, Any]) -> dict[str, Any]:
    version = source.get("version", 1)
    if not isinstance(version, int):
        version = 1

    vim_mode = False
    editor = source.get("editor")
    if isinstance(editor, dict) and isinstance(editor.get("vimMode"), bool):
        vim_mode = editor["vimMode"]

    allow: list[Any] = []
    deny: list[Any] = []
    permissions = source.get("permissions")
    if isinstance(permissions, dict):
        if isinstance(permissions.get("allow"), list):
            allow = list(permissions["allow"])
        if isinstance(permissions.get("deny"), list):
            deny = list(permissions["deny"])

    return {
        "version": version,
        "editor": {"vimMode": vim_mode},
        "permissions": {"allow": allow, "deny": deny},
    }


def extract_global_overlay(source: dict[str, Any]) -> dict[str, Any]:
    overlay: dict[str, Any] = {}
    for key, value in source.items():
        if key not in PROJECT_ALLOWED_KEYS:
            overlay[key] = value
    editor = source.get("editor")
    if isinstance(editor, dict):
        extra_editor = {
            key: value for key, value in editor.items() if key not in EDITOR_ALLOWED_KEYS
        }
        if extra_editor:
            overlay["editor"] = extra_editor
    permissions = source.get("permissions")
    if isinstance(permissions, dict):
        extra_permissions = {
            key: value
            for key, value in permissions.items()
            if key not in PERMISSIONS_ALLOWED_KEYS
        }
        if extra_permissions:
            overlay["permissions"] = extra_permissions
    return overlay


def ensure_global_required(payload: dict[str, Any]) -> dict[str, Any]:
    """Stamp required global fields without clobbering existing values."""
    out = dict(payload)
    if not isinstance(out.get("version"), int):
        out["version"] = 1
    editor = out.get("editor")
    if not isinstance(editor, dict):
        editor = {}
    if not isinstance(editor.get("vimMode"), bool):
        editor = dict(editor)
        editor["vimMode"] = False
    out["editor"] = editor
    permissions = out.get("permissions")
    if not isinstance(permissions, dict):
        permissions = {}
    else:
        permissions = dict(permissions)
    if not isinstance(permissions.get("allow"), list):
        permissions["allow"] = []
    if not isinstance(permissions.get("deny"), list):
        permissions["deny"] = []
    out["permissions"] = permissions
    return out


def backup_file(path: Path) -> Path:
    backup = path.with_name(f"{path.name}.bak.{utc_stamp()}")
    shutil.copy2(path, backup)
    return backup


def write_json_atomic(path: Path, payload: dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=False) + "\n"
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp_path.write_text(text, encoding="utf-8")
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def existing_file_mode(path: Path, default: int = 0o600) -> int:
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return default


def inspect_project(payload: dict[str, Any] | None) -> tuple[bool, list[str]]:
    if payload is None:
        return False, []
    keys = unrecognized_project_keys(payload)
    return bool(keys), keys


def repair_cursor_cli_config(
    home: Path,
    *,
    project_config: Path | None = None,
    global_config: Path | None = None,
    dry_run: bool = False,
) -> RepairResult:
    project_path, global_path = cursor_paths(home, project_config, global_config)
    result = RepairResult(
        project_path=project_path,
        global_path=global_path,
        needs_repair=False,
        message="No project cli.json found; nothing to repair.",
    )

    try:
        project_payload = load_json_object(project_path)
    except ValueError as exc:
        result.error = str(exc)
        result.message = (
            f"Cannot parse project config. Move it aside and retry:\n"
            f"  mv {project_path} {project_path}.bad"
        )
        return result

    needs_repair, keys = inspect_project(project_payload)
    result.needs_repair = needs_repair
    result.unrecognized_keys = keys
    if project_payload is None:
        return result
    if not needs_repair:
        result.message = f"Project config is already valid: {project_path}"
        return result

    overlay = extract_global_overlay(project_payload)
    result.migrated_keys = sorted(overlay.keys())
    stripped = normalize_project_payload(project_payload)

    if dry_run:
        result.message = (
            "Dry run: would migrate "
            + ", ".join(result.migrated_keys)
            + f" from {project_path} to {global_path}"
        )
        return result

    if project_path.exists():
        result.backups.append(str(backup_file(project_path)))
    if global_path.exists():
        result.backups.append(str(backup_file(global_path)))

    try:
        global_payload = load_json_object(global_path)
    except ValueError as exc:
        result.error = str(exc)
        result.message = (
            f"Cannot parse global config. Move it aside and retry:\n"
            f"  mv {global_path} {global_path}.bad"
        )
        return result

    if global_payload is None:
        global_payload = {}
    merged_global = ensure_global_required(deep_merge(global_payload, overlay))

    write_json_atomic(
        global_path,
        merged_global,
        mode=existing_file_mode(global_path),
    )
    result.global_written = True
    write_json_atomic(
        project_path,
        stripped,
        mode=existing_file_mode(project_path),
    )
    result.project_written = True
    result.message = (
        "Repaired project config by moving "
        + ", ".join(result.migrated_keys)
        + f" into {global_path}"
    )
    return result


def format_text(result: RepairResult) -> str:
    lines = [
        f"Project config: {result.project_path}",
        f"Global config:  {result.global_path}",
        f"Needs repair:   {str(result.needs_repair).lower()}",
    ]
    if result.unrecognized_keys:
        lines.append("Unrecognized:   " + ", ".join(result.unrecognized_keys))
    if result.migrated_keys:
        lines.append("Migrated:       " + ", ".join(result.migrated_keys))
    if result.backups:
        lines.append("Backups:")
        for backup in result.backups:
            lines.append(f"  {backup}")
    if result.error:
        lines.append(f"Error: {result.error}")
    lines.append(result.message)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    home = Path(args.home).expanduser()
    project_config = (
        Path(args.project_config).expanduser() if args.project_config else None
    )
    global_config = (
        Path(args.global_config).expanduser() if args.global_config else None
    )
    dry_run = bool(args.dry_run or args.status)
    result = repair_cursor_cli_config(
        home,
        project_config=project_config,
        global_config=global_config,
        dry_run=dry_run,
    )
    if args.as_json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_text(result))
    if result.error:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
