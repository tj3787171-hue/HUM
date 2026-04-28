#!/usr/bin/env python3
"""Inventory HUM artifact layers from config files through ISO outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_OUTPUT_JSON = Path("site/data/artifact-layers.json")
DEFAULT_OUTPUT_MARKDOWN = Path("docs/HUM_ARTIFACT_LAYERS.generated.md")
DEFAULT_COPY_LAYER_DIR = Path("dist/hum-copy-layer")
DEFAULT_COPY_LAYER_ARCHIVE = Path("dist/hum-copy-layer-accompaniment.tar.gz")
DEFAULT_MAX_BYTES = 16 * 1024 * 1024
READ_CHUNK_SIZE = 1024 * 1024

LAYER_EXTENSIONS = {
    "config": {".yml", ".yaml", ".json", ".csv"},
    "code": {".py", ".js", ".php", ".sh"},
    "document": {".md", ".txt"},
    "media": {".svg", ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"},
    "java": {".jar"},
    "archive": {
        ".tar",
        ".tar.gz",
        ".tgz",
        ".tar.xz",
        ".tar.zst",
        ".gz",
        ".xz",
        ".zst",
        ".zip",
        ".snap",
        ".td.zz",
    },
    "package": {".deb"},
    "iso": {".iso"},
}

KIND_BY_SUFFIX = {
    ".yml": "config-yaml",
    ".yaml": "config-yaml",
    ".json": "config-json",
    ".csv": "config-csv",
    ".py": "python-code",
    ".js": "javascript-code",
    ".php": "php-code",
    ".sh": "shell-code",
    ".md": "markdown-document",
    ".txt": "text-document",
    ".svg": "svg-vector",
    ".png": "bitmap-image",
    ".jpg": "bitmap-image",
    ".jpeg": "bitmap-image",
    ".bmp": "bitmap-image",
    ".gif": "bitmap-image",
    ".webp": "bitmap-image",
    ".jar": "java-archive",
    ".tar": "tar-archive",
    ".tar.gz": "tar-archive",
    ".tgz": "tar-archive",
    ".tar.xz": "tar-archive",
    ".tar.zst": "tar-archive",
    ".gz": "compressed-layer",
    ".xz": "compressed-layer",
    ".zst": "compressed-layer",
    ".zip": "zip-archive",
    ".snap": "snap-package",
    ".td.zz": "compressed-layer",
    ".deb": "debian-package",
    ".iso": "iso-image",
}

COPY_LAYER_KINDS = {
    "markdown-document",
    "shell-code",
    "svg-vector",
    "text-document",
    "bitmap-image",
}

SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    "hum-copy-layer",
    "node_modules",
    ".venv",
    "venv",
}


@dataclass(frozen=True)
class Artifact:
    path: str
    layer: str
    kind: str
    size_bytes: int
    mtime: str
    sha256_prefix: str | None
    probe: dict[str, Any]
    benchmark: dict[str, Any] | None


def utc_iso(timestamp: float | None = None) -> str:
    if timestamp is None:
        timestamp = time.time()
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat()


def normalized_suffix(path: Path) -> str:
    name = path.name.lower()
    for suffix in (".tar.gz", ".tar.xz", ".tar.zst", ".td.zz"):
        if name.endswith(suffix):
            return suffix
    return path.suffix.lower()


def layer_for(path: Path) -> tuple[str, str] | None:
    suffix = normalized_suffix(path)
    for layer, extensions in LAYER_EXTENSIONS.items():
        if suffix in extensions:
            return layer, KIND_BY_SUFFIX.get(suffix, suffix.lstrip("."))
    return None


def classify_path(path: Path) -> str | None:
    layer = layer_for(path)
    return layer[1] if layer else None


def iter_candidates(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            if layer_for(path):
                yield path


def sha256_prefix(path: Path, max_bytes: int) -> str:
    digest = hashlib.sha256()
    remaining = max_bytes
    with path.open("rb") as handle:
        while remaining > 0:
            chunk = handle.read(min(READ_CHUNK_SIZE, remaining))
            if not chunk:
                break
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()[:16]


def benchmark_read(path: Path, max_bytes: int) -> dict[str, Any]:
    start = time.perf_counter()
    total = 0
    with path.open("rb") as handle:
        while total < max_bytes:
            chunk = handle.read(min(READ_CHUNK_SIZE, max_bytes - total))
            if not chunk:
                break
            total += len(chunk)
    elapsed = max(time.perf_counter() - start, 0.000001)
    return {
        "read_bytes": total,
        "elapsed_ms": round(elapsed * 1000, 3),
        "mb_per_sec": round((total / (1024 * 1024)) / elapsed, 3),
    }


def count_json_keys(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        return {"json_type": "object", "top_level_keys": sorted(payload.keys())[:20]}
    if isinstance(payload, list):
        return {"json_type": "array", "items": len(payload)}
    return {"json_type": type(payload).__name__}


def probe_text(path: Path) -> dict[str, Any]:
    lines = 0
    non_empty = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for lines, line in enumerate(handle, start=1):
            if line.strip():
                non_empty += 1
    probe: dict[str, Any] = {"lines": lines, "non_empty_lines": non_empty}
    if normalized_suffix(path) == ".json":
        try:
            probe.update(count_json_keys(path))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            probe["json_error"] = str(exc)
    return probe


def probe_tar(path: Path) -> dict[str, Any]:
    if not tarfile.is_tarfile(path):
        return {"archive_reader": "tarfile", "readable": False}
    with tarfile.open(path) as tar:
        members = tar.getmembers()
        return {
            "archive_reader": "tarfile",
            "readable": True,
            "members": len(members),
            "sample": [member.name for member in members[:10]],
        }


def probe_zip(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        return {
            "archive_reader": "zipfile",
            "readable": True,
            "members": len(names),
            "sample": names[:10],
        }


def probe_artifact(path: Path, layer: str, kind: str) -> dict[str, Any]:
    try:
        if layer in {"config", "code", "document"} or kind == "svg-vector":
            return probe_text(path)
        if kind == "jar" or normalized_suffix(path) == ".zip":
            return probe_zip(path)
        if normalized_suffix(path).startswith(".tar") or kind == "tgz":
            return probe_tar(path)
        return {"probe": "metadata-only"}
    except (OSError, tarfile.TarError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
        return {"probe_error": str(exc)}


def scan(root: Path, *, benchmark: bool, max_bytes: int) -> dict[str, Any]:
    artifacts: list[Artifact] = []
    for path in sorted(iter_candidates(root)):
        stat = path.stat()
        layer, kind = layer_for(path) or ("unknown", normalized_suffix(path).lstrip("."))
        artifacts.append(
            Artifact(
                path=path.relative_to(root).as_posix(),
                layer=layer,
                kind=kind,
                size_bytes=stat.st_size,
                mtime=utc_iso(stat.st_mtime),
                sha256_prefix=sha256_prefix(path, max_bytes),
                probe=probe_artifact(path, layer, kind),
                benchmark=benchmark_read(path, max_bytes) if benchmark else None,
            )
        )

    by_layer: dict[str, dict[str, int]] = {}
    archives = []
    sampled_files = 0
    sampled_bytes = 0
    for artifact in artifacts:
        entry = by_layer.setdefault(artifact.layer, {"count": 0, "size_bytes": 0})
        entry["count"] += 1
        entry["size_bytes"] += artifact.size_bytes
        if artifact.probe.get("archive_reader") or artifact.layer in {"archive", "java", "package", "iso"}:
            archives.append({"path": artifact.path, "kind": artifact.kind, "probe": artifact.probe})
        if artifact.benchmark:
            sampled_files += 1
            sampled_bytes += int(artifact.benchmark.get("read_bytes", 0))

    return {
        "generated_at": utc_iso(),
        "root": str(root),
        "artifact_count": len(artifacts),
        "summary": {
            "artifact_count": len(artifacts),
            "total_size_bytes": sum(artifact.size_bytes for artifact in artifacts),
        },
        "benchmark": {
            "enabled": benchmark,
            "sampled_files": sampled_files,
            "sampled_bytes": sampled_bytes,
        },
        "layers": by_layer,
        "archives": archives,
        "artifacts": [artifact.__dict__ for artifact in artifacts],
    }


def inventory(root: Path, benchmark_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, Any]:
    return scan(root.resolve(), benchmark=benchmark_bytes > 0, max_bytes=max(benchmark_bytes, 0))


def write_inventory(
    root: Path,
    output_json: Path,
    output_markdown: Path,
    benchmark_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    payload = inventory(root, benchmark_bytes=benchmark_bytes)
    write_json(output_json, payload)
    write_markdown(output_markdown, payload)
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# HUM artifact layer inventory",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Root: `{payload['root']}`",
        f"Artifacts: `{payload['artifact_count']}`",
        "",
        "## Layer summary",
        "",
        "| Layer | Count | Size bytes |",
        "|---|---:|---:|",
    ]
    for layer, data in sorted(payload["layers"].items()):
        lines.append(f"| `{layer}` | {data['count']} | {data['size_bytes']} |")
    lines.extend(["", "## Artifacts", "", "| Layer | Kind | Path | Bytes | SHA-256 prefix |", "|---|---|---|---:|---|"])
    for artifact in payload["artifacts"]:
        lines.append(
            f"| `{artifact['layer']}` | `{artifact['kind']}` | `{artifact['path']}` | "
            f"{artifact['size_bytes']} | `{artifact['sha256_prefix']}` |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_layer_artifacts(root: Path, payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    copied: list[dict[str, Any]] = []
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for artifact in payload["artifacts"]:
        if artifact["kind"] not in COPY_LAYER_KINDS:
            continue
        source = root / artifact["path"]
        target = output_dir / artifact["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(
            {
                "path": artifact["path"],
                "kind": artifact["kind"],
                "layer": artifact["layer"],
                "size_bytes": artifact["size_bytes"],
                "sha256_prefix": artifact["sha256_prefix"],
            }
        )

    manifest = {
        "generated_at": utc_iso(),
        "root": str(root),
        "copy_layer_dir": str(output_dir),
        "copied_count": len(copied),
        "copied_size_bytes": sum(int(item["size_bytes"]) for item in copied),
        "included_kinds": sorted(COPY_LAYER_KINDS),
        "files": copied,
    }
    write_json(output_dir / "COPY_LAYER_MANIFEST.json", manifest)
    return manifest


def compress_copy_layer(output_dir: Path, archive_path: Path) -> dict[str, Any]:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(output_dir, arcname=output_dir.name)

    stat = archive_path.stat()
    digest = hashlib.sha256()
    with archive_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(READ_CHUNK_SIZE), b""):
            digest.update(chunk)
    return {
        "archive": str(archive_path),
        "size_bytes": stat.st_size,
        "sha256": digest.hexdigest(),
    }


def build_copy_layer(root: Path, payload: dict[str, Any], output_dir: Path, archive_path: Path) -> dict[str, Any]:
    manifest = copy_layer_artifacts(root, payload, output_dir)
    archive = compress_copy_layer(output_dir, archive_path)
    manifest["archive"] = archive
    write_json(output_dir / "COPY_LAYER_MANIFEST.json", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."), help="Directory to scan")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_OUTPUT_MARKDOWN)
    parser.add_argument("--benchmark", action="store_true", help="Measure sequential read speed")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help="Per-file hash/read byte cap")
    parser.add_argument("--copy-layer", action="store_true", help="Copy md/sh/svg/txt/bitmap files into a staged layer")
    parser.add_argument("--copy-output-dir", type=Path, default=DEFAULT_COPY_LAYER_DIR)
    parser.add_argument("--copy-archive", type=Path, default=DEFAULT_COPY_LAYER_ARCHIVE)
    parser.add_argument("--stdout", action="store_true", help="Print JSON payload to stdout")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    benchmark_bytes = args.max_bytes if args.benchmark else 0
    payload = write_inventory(root, args.output_json, args.output_markdown, benchmark_bytes=benchmark_bytes)
    copy_layer = None
    if args.copy_layer:
        copy_layer = build_copy_layer(root, payload, args.copy_output_dir, args.copy_archive)
        payload["copy_layer"] = copy_layer
        write_json(args.output_json, payload)
    if args.stdout:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"[hum-artifact-layers] wrote {args.output_json}")
        print(f"[hum-artifact-layers] wrote {args.output_markdown}")
        print(f"[hum-artifact-layers] artifacts: {payload['artifact_count']}")
        if copy_layer:
            print(f"[hum-artifact-layers] copy layer files: {copy_layer['copied_count']}")
            print(f"[hum-artifact-layers] copy archive: {copy_layer['archive']['archive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
