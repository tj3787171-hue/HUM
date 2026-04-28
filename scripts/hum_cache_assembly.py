#!/usr/bin/env python3
"""Assemble apt/pkg/cache/image/libclang evidence and interval plots."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape


DEFAULT_OUTPUT_JSON = Path("site/data/cache-assembly.json")
DEFAULT_OUTPUT_MARKDOWN = Path("docs/HUM_CACHE_ASSEMBLY.generated.md")
DEFAULT_OUTPUT_SVG = Path("site/data/cache-interval-plot.svg")
DEFAULT_PREFIX = "hum-cache"
DEFAULT_ROOTS = (
    Path("."),
    Path("/var/cache/apt"),
    Path("/var/lib/apt"),
    Path("/var/lib/dpkg/info"),
    Path("/usr/lib"),
    Path("/usr/lib/x86_64-linux-gnu"),
)
READ_CHUNK_SIZE = 1024 * 1024
DEFAULT_MAX_FILES = 2500
DEFAULT_HASH_BYTES = 1024 * 1024

CANDIDATE_SUFFIXES = {
    ".a",
    ".bin",
    ".bmp",
    ".cache",
    ".deb",
    ".dsc",
    ".gif",
    ".gz",
    ".img",
    ".jpeg",
    ".jpg",
    ".list",
    ".lz4",
    ".png",
    ".so",
    ".svg",
    ".webp",
    ".xz",
}

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "hum-copy-layer",
    "node_modules",
}


@dataclass(frozen=True)
class CachePiece:
    path: str
    root: str
    category: str
    size_bytes: int
    mtime: str
    sha256_prefix: str


def utc_iso(timestamp: float | None = None) -> str:
    if timestamp is None:
        timestamp = time.time()
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat()


def classify_piece(path: Path) -> str:
    name = path.name.lower()
    text = path.as_posix().lower()
    suffix = path.suffix.lower()
    if "libclang" in name or "libclang" in text or "clang++" in text or "llvm" in text:
        return "libclang-family"
    if suffix == ".deb":
        return "package-deb"
    if suffix in {".dsc"} or "source" in name or "sources" in name:
        return "source-index"
    if suffix in {".img", ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".svg"}:
        return "image-layer"
    if "cache" in text or suffix in {".cache", ".bin"}:
        return "cache-piece"
    if suffix in {".list", ".gz", ".xz", ".lz4"}:
        return "apt-index"
    if suffix in {".so", ".a"}:
        return "library-piece"
    return "metadata"


def should_include(path: Path) -> bool:
    suffix = path.suffix.lower()
    text = path.as_posix().lower()
    if suffix in CANDIDATE_SUFFIXES:
        return True
    return any(token in text for token in ("apt", "pkg", "cache", "clang", "llvm", "libclang"))


def iter_files(roots: Iterable[Path], max_files: int) -> Iterable[tuple[Path, Path]]:
    emitted = 0
    for root in roots:
        if emitted >= max_files:
            return
        if not root.exists():
            continue
        root = root.resolve()
        if root.is_file():
            if should_include(root):
                yield root, root.parent
                emitted += 1
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
            for filename in filenames:
                if emitted >= max_files:
                    return
                path = Path(dirpath) / filename
                if should_include(path):
                    yield path, root
                    emitted += 1


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


def scan_cache(roots: Iterable[Path], max_files: int, hash_bytes: int) -> dict[str, Any]:
    pieces: list[CachePiece] = []
    for path, root in iter_files(roots, max_files=max_files):
        try:
            stat = path.stat()
            relative = path.relative_to(root).as_posix()
            digest = sha256_prefix(path, hash_bytes)
        except (OSError, ValueError):
            continue
        pieces.append(
            CachePiece(
                path=relative,
                root=str(root),
                category=classify_piece(path),
                size_bytes=stat.st_size,
                mtime=utc_iso(stat.st_mtime),
                sha256_prefix=digest,
            )
        )

    categories: dict[str, dict[str, int]] = {}
    roots_summary: dict[str, dict[str, int]] = {}
    for piece in pieces:
        cat = categories.setdefault(piece.category, {"count": 0, "size_bytes": 0})
        cat["count"] += 1
        cat["size_bytes"] += piece.size_bytes
        root = roots_summary.setdefault(piece.root, {"count": 0, "size_bytes": 0})
        root["count"] += 1
        root["size_bytes"] += piece.size_bytes

    return {
        "generated_at": utc_iso(),
        "piece_count": len(pieces),
        "categories": categories,
        "roots": roots_summary,
        "pieces": [piece.__dict__ for piece in pieces],
    }


def interval_points(pieces: list[dict[str, Any]], exponent: float, prefix: str) -> list[dict[str, Any]]:
    ordered = sorted(pieces, key=lambda item: (-int(item["size_bytes"]), item["path"]))
    points = []
    for index, piece in enumerate(ordered, start=1):
        y = index**exponent
        points.append(
            {
                "id": f"{prefix}-{index:04d}",
                "n": index,
                "y": round(y, 6),
                "predicate": f"y = n^{exponent:g}",
                "category": piece["category"],
                "path": piece["path"],
                "size_bytes": piece["size_bytes"],
            }
        )
    return points


def build_interval_plot(payload: dict[str, Any], exponent: float, prefix: str = DEFAULT_PREFIX) -> dict[str, Any]:
    points = interval_points(payload["pieces"], exponent, prefix)
    payload["interval_plot"] = {
        "prefix": prefix,
        "formula": f"y = n^{exponent:g}",
        "exponent": exponent,
        "point_count": len(points),
        "points": points,
    }
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# HUM cache assembly",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Pieces: `{payload['piece_count']}`",
        f"Prefix: `{payload['interval_plot']['prefix']}`",
        f"Formula: `{payload['interval_plot']['formula']}`",
        "",
        "## Categories",
        "",
        "| Category | Count | Size bytes |",
        "|---|---:|---:|",
    ]
    for category, data in sorted(payload["categories"].items()):
        lines.append(f"| `{category}` | {data['count']} | {data['size_bytes']} |")
    lines.extend(["", "## Largest pieces", "", "| Category | Root | Path | Bytes | SHA-256 prefix |", "|---|---|---|---:|---|"])
    for piece in sorted(payload["pieces"], key=lambda item: -int(item["size_bytes"]))[:40]:
        lines.append(
            f"| `{piece['category']}` | `{piece['root']}` | `{piece['path']}` | "
            f"{piece['size_bytes']} | `{piece['sha256_prefix']}` |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_svg(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    points = payload["interval_plot"]["points"]
    width = 960
    height = 420
    pad = 52
    plot_w = width - (pad * 2)
    plot_h = height - (pad * 2)
    max_y = max((float(point["y"]) for point in points), default=1.0)
    max_size = max((int(point["size_bytes"]) for point in points), default=1)
    prefix = payload["interval_plot"]["prefix"]
    rows = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#0d1117"/>',
        f'<text x="{pad}" y="30" fill="#58a6ff" font-size="18" font-family="monospace">HUM cache interval plot {escape(prefix)} ({escape(payload["interval_plot"]["formula"])})</text>',
        f'<line x1="{pad}" y1="{height - pad}" x2="{width - pad}" y2="{height - pad}" stroke="#30363d"/>',
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height - pad}" stroke="#30363d"/>',
    ]
    for point in points[:160]:
        x = pad + ((point["n"] - 1) / max(max(len(points) - 1, 1), 1)) * plot_w
        y = (height - pad) - (float(point["y"]) / max_y) * plot_h
        radius = 3 + min(8, (int(point["size_bytes"]) / max_size) * 8)
        color = {
            "apt-index": "#58a6ff",
            "cache-piece": "#d29922",
            "image-layer": "#a371f7",
            "libclang-family": "#3fb950",
            "package-deb": "#f85149",
            "source-index": "#79c0ff",
        }.get(point["category"], "#8b949e")
        label = escape(f"{point['id']} {point['category']} {point['path']} {point['size_bytes']} bytes")
        rows.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" fill="{color}"><title>{label}</title></circle>')
    rows.extend(
        [
            f'<text x="{pad}" y="{height - 16}" fill="#8b949e" font-size="12" font-family="monospace">n interval index</text>',
            f'<text x="{width - pad}" y="{height - 16}" fill="#8b949e" font-size="12" font-family="monospace" text-anchor="end">pieces: {len(points)}</text>',
            "</svg>",
        ]
    )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", type=Path, help="Root to scan; may be repeated")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_OUTPUT_MARKDOWN)
    parser.add_argument("--output-svg", type=Path, default=DEFAULT_OUTPUT_SVG)
    parser.add_argument("--exponent", type=float, default=1.35, help="Exponent for interval plot formula y=n^exponent")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="Prefix for interval point IDs")
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    parser.add_argument("--hash-bytes", type=int, default=DEFAULT_HASH_BYTES)
    parser.add_argument("--stdout", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    roots = args.root if args.root else list(DEFAULT_ROOTS)
    payload = scan_cache(roots, max_files=args.max_files, hash_bytes=args.hash_bytes)
    build_interval_plot(payload, args.exponent, args.prefix)
    write_json(args.output_json, payload)
    write_markdown(args.output_markdown, payload)
    write_svg(args.output_svg, payload)
    if args.stdout:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"[hum-cache-assembly] wrote {args.output_json}")
        print(f"[hum-cache-assembly] wrote {args.output_markdown}")
        print(f"[hum-cache-assembly] wrote {args.output_svg}")
        print(f"[hum-cache-assembly] pieces: {payload['piece_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
