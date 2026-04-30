#!/usr/bin/env python3
"""Inventory HUM repository artifacts by layer and optionally build a copy layer."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TEXT_EXTENSIONS = {".txt", ".list", ".log"}
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
SHELL_EXTENSIONS = {".sh", ".bash", ".zsh"}
PYTHON_EXTENSIONS = {".py"}
JAVASCRIPT_EXTENSIONS = {".js", ".mjs", ".cjs"}
PHP_EXTENSIONS = {".php"}
JSON_EXTENSIONS = {".json"}
YAML_EXTENSIONS = {".yml", ".yaml"}
SVG_EXTENSIONS = {".svg"}
BITMAP_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
ARCHIVE_SUFFIXES = (".tar", ".tar.gz", ".tgz")

DEFAULT_IGNORE_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
}

COPY_LAYER_KINDS = {
    "bitmap-image",
    "markdown-document",
    "shell-code",
    "svg-vector",
    "text-document",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_prefix(path: Path, prefix_len: int = 16) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()[:prefix_len]


def classify_path(path: Path) -> str:
    lower_name = path.name.lower()
    suffix = path.suffix.lower()
    suffixes = "".join(path.suffixes).lower()
    if suffixes.endswith(ARCHIVE_SUFFIXES):
        return "tar-archive"
    if suffix == ".iso":
        return "iso-image"
    if suffix == ".deb":
        return "debian-package"
    if suffix == ".jar":
        return "java-archive"
    if lower_name.endswith(".td.zz") or suffix in {".xz", ".gz", ".zip", ".zst"}:
        return "compressed-layer"
    if suffix in JSON_EXTENSIONS:
        return "config-json"
    if suffix in YAML_EXTENSIONS:
        return "config-yaml"
    if suffix in SHELL_EXTENSIONS:
        return "shell-code"
    if suffix in PYTHON_EXTENSIONS:
        return "python-code"
    if suffix in JAVASCRIPT_EXTENSIONS:
        return "javascript-code"
    if suffix in PHP_EXTENSIONS:
        return "php-code"
    if suffix in MARKDOWN_EXTENSIONS:
        return "markdown-document"
    if suffix in TEXT_EXTENSIONS:
        return "text-document"
    if suffix in SVG_EXTENSIONS:
        return "svg-vector"
    if suffix in BITMAP_EXTENSIONS:
        return "bitmap-image"
    return "binary-or-other"


def layer_for_kind(kind: str) -> str:
    if kind in {"config-json", "config-yaml", "config-csv"}:
        return "config"
    if kind in {"markdown-document", "text-document"}:
        return "document"
    if kind in {"svg-vector", "bitmap-image"}:
        return "media"
    if kind in {"tar-archive", "compressed-layer"}:
        return "archive"
    if kind == "iso-image":
        return "iso"
    if kind == "debian-package":
        return "package"
    return "code" if kind.endswith("-code") or kind == "java-archive" else "other"


def should_skip(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    return any(part in DEFAULT_IGNORE_PARTS for part in relative.parts)


def probe_text_file(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"read_error": str(exc)}
    lines = text.splitlines()
    return {"lines": len(lines), "non_empty_lines": sum(1 for line in lines if line.strip())}


def probe_json_file(path: Path) -> dict[str, Any]:
    probe = probe_text_file(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        probe.update(
            {
                "json_type": "array" if isinstance(payload, list) else "object" if isinstance(payload, dict) else type(payload).__name__,
                "top_level_keys": sorted(payload.keys())[:12] if isinstance(payload, dict) else [],
            }
        )
    except (json.JSONDecodeError, OSError) as exc:
        probe["json_error"] = str(exc)
    return probe


def probe_tar(path: Path) -> dict[str, Any]:
    try:
        with tarfile.open(path) as archive:
            members = archive.getnames()
        return {"archive_reader": "tarfile", "readable": True, "members": len(members), "sample": members[:10]}
    except (tarfile.TarError, OSError) as exc:
        return {"archive_reader": "tarfile", "readable": False, "error": str(exc)}


def probe_artifact(path: Path, kind: str) -> dict[str, Any]:
    if kind == "config-json":
        return probe_json_file(path)
    if kind in {"config-yaml", "shell-code", "python-code", "javascript-code", "php-code", "markdown-document", "text-document", "svg-vector"}:
        return probe_text_file(path)
    if kind == "tar-archive":
        return probe_tar(path)
    if kind == "iso-image":
        return {"probe": "metadata-only"}
    return {}


def read_benchmark(path: Path, sample_bytes: int) -> dict[str, Any]:
    start = time.perf_counter()
    data = path.read_bytes()[:sample_bytes] if sample_bytes else b""
    elapsed = max(time.perf_counter() - start, 0.000001)
    mb_per_sec = (len(data) / (1024 * 1024)) / elapsed if data else 0.0
    return {
        "elapsed_ms": round(elapsed * 1000, 3),
        "mb_per_sec": round(mb_per_sec, 3),
        "read_bytes": len(data),
    }


def inventory(root: Path, benchmark_bytes: int = 256 * 1024) -> dict[str, Any]:
    root = root.resolve()
    artifacts: list[dict[str, Any]] = []
    archives: list[dict[str, Any]] = []
    layers: dict[str, dict[str, int]] = {}
    sampled_files = 0
    sampled_bytes = 0

    for path in sorted(item for item in root.rglob("*") if item.is_file() and not should_skip(item, root)):
        rel = path.relative_to(root).as_posix()
        kind = classify_path(path)
        layer = layer_for_kind(kind)
        stat = path.stat()
        probe = probe_artifact(path, kind)
        benchmark = read_benchmark(path, benchmark_bytes)
        sampled_files += 1
        sampled_bytes += benchmark["read_bytes"]
        record = {
            "path": rel,
            "kind": kind,
            "layer": layer,
            "size_bytes": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "sha256_prefix": sha256_prefix(path),
            "probe": probe,
            "benchmark": benchmark,
        }
        artifacts.append(record)
        layer_bucket = layers.setdefault(layer, {"count": 0, "size_bytes": 0})
        layer_bucket["count"] += 1
        layer_bucket["size_bytes"] += stat.st_size
        if kind in {"tar-archive", "iso-image"}:
            archives.append({"kind": kind, "path": rel, "probe": probe})

    return {
        "generated_at": utc_now(),
        "root": str(root),
        "artifact_count": len(artifacts),
        "summary": {
            "artifact_count": len(artifacts),
            "total_size_bytes": sum(item["size_bytes"] for item in artifacts),
        },
        "benchmark": {
            "enabled": bool(benchmark_bytes),
            "sampled_files": sampled_files,
            "sampled_bytes": sampled_bytes,
        },
        "layers": layers,
        "archives": archives,
        "artifacts": artifacts,
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# HUM artifact layer inventory",
        "",
        f"Generated: `{report['generated_at']}`",
        f"Root: `{report['root']}`",
        f"Artifacts: `{report['summary']['artifact_count']}`",
        "",
        "## Layers",
        "",
        "| Layer | Count | Bytes |",
        "|---|---:|---:|",
    ]
    for layer, info in sorted(report["layers"].items()):
        lines.append(f"| `{layer}` | {info['count']} | {info['size_bytes']} |")
    lines.extend(["", "## Sample artifacts", ""])
    for artifact in report["artifacts"][:50]:
        lines.append(f"- `{artifact['path']}` (`{artifact['kind']}`, {artifact['size_bytes']} bytes)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_inventory(root: Path, output_json: Path, output_markdown: Path | None = None, benchmark_bytes: int = 256 * 1024) -> dict[str, Any]:
    report = inventory(root, benchmark_bytes=benchmark_bytes)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_markdown is not None:
        write_markdown(output_markdown, report)
    return report


def build_copy_layer(root: Path, report: dict[str, Any], output_dir: Path, archive_path: Path) -> dict[str, Any]:
    root = root.resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    copied: list[dict[str, Any]] = []
    for item in report["artifacts"]:
        if item["kind"] not in COPY_LAYER_KINDS:
            continue
        source = root / item["path"]
        target = output_dir / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(
            {
                "path": item["path"],
                "kind": item["kind"],
                "layer": item["layer"],
                "size_bytes": item["size_bytes"],
                "sha256_prefix": item["sha256_prefix"],
            }
        )

    manifest = {
        "generated_at": utc_now(),
        "root": str(root),
        "copy_layer_dir": str(output_dir),
        "included_kinds": sorted(COPY_LAYER_KINDS),
        "copied_count": len(copied),
        "copied_size_bytes": sum(item["size_bytes"] for item in copied),
        "files": copied,
    }
    (output_dir / "COPY_LAYER_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(output_dir, arcname=output_dir.name)
    manifest["archive"] = {
        "archive": archive_path.as_posix(),
        "size_bytes": archive_path.stat().st_size,
        "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
    }
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inventory HUM artifacts by layer.")
    parser.add_argument("--root", default=".", help="Repository root to scan")
    parser.add_argument("--output-json", default="site/data/artifact-layers.json")
    parser.add_argument("--output-markdown", default="docs/HUM_ARTIFACT_LAYERS.generated.md")
    parser.add_argument("--benchmark-bytes", type=int, default=256 * 1024)
    parser.add_argument("--copy-layer-dir", default="")
    parser.add_argument("--copy-layer-archive", default="")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.root)
    report = write_inventory(root, Path(args.output_json), Path(args.output_markdown), benchmark_bytes=args.benchmark_bytes)
    if args.copy_layer_dir and args.copy_layer_archive:
        report["copy_layer"] = build_copy_layer(root, report, Path(args.copy_layer_dir), Path(args.copy_layer_archive))
        Path(args.output_json).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"artifact_count={report['summary']['artifact_count']}")
    print(f"output_json={args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
