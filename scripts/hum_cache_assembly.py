#!/usr/bin/env python3
"""Build cache/package/image assembly evidence with interval plot data."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_piece(path: Path) -> str:
    name = path.name.lower()
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if name in {"sources.gz", "packages.gz", "release", "inrelease"}:
        return "source-index"
    if ".deb" in suffixes:
        return "package-deb"
    if name.endswith("pkgcache.bin") or "cache" in path.parts:
        return "cache-piece"
    if suffixes and suffixes[-1] in {".img", ".iso", ".qcow2", ".squashfs"}:
        return "image-layer"
    if "libclang" in name or "clang" in name:
        return "libclang-family"
    return "other"


def sha256_prefix(path: Path, hash_bytes: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        remaining = hash_bytes
        while remaining > 0:
            chunk = handle.read(min(65536, remaining))
            if not chunk:
                break
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()[:16]


def scan_cache(roots: list[Path], max_files: int = 5000, hash_bytes: int = 1024 * 1024) -> dict[str, Any]:
    pieces: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists():
            continue
        files = sorted(path for path in root.rglob("*") if path.is_file())
        for path in files:
            if len(pieces) >= max_files:
                break
            stat = path.stat()
            category = classify_piece(path)
            pieces.append(
                {
                    "path": str(path),
                    "name": path.name,
                    "category": category,
                    "size_bytes": stat.st_size,
                    "sha256_prefix": sha256_prefix(path, hash_bytes),
                }
            )
    categories: dict[str, dict[str, int]] = {}
    for piece in pieces:
        cat = piece["category"]
        bucket = categories.setdefault(cat, {"count": 0, "size_bytes": 0})
        bucket["count"] += 1
        bucket["size_bytes"] += int(piece["size_bytes"])
    return {
        "generated_at": utc_now(),
        "roots": [str(root) for root in roots],
        "piece_count": len(pieces),
        "categories": categories,
        "pieces": pieces,
    }


def interval_points(pieces: list[dict[str, Any]], exponent: float, prefix: str) -> list[dict[str, Any]]:
    points = []
    for index, piece in enumerate(pieces, start=1):
        points.append(
            {
                "id": f"{prefix}-{index:04d}",
                "n": index,
                "y": round(index**exponent, 6),
                "path": piece["path"],
                "size_bytes": piece["size_bytes"],
                "category": piece["category"],
            }
        )
    return points


def build_interval_plot(report: dict[str, Any], exponent: float, prefix: str) -> dict[str, Any]:
    pieces = sorted(report["pieces"], key=lambda item: (-int(item["size_bytes"]), item["path"]))
    points = interval_points(pieces, exponent, prefix)
    report["interval_plot"] = {
        "formula": f"y = n^{exponent:g}",
        "prefix": prefix,
        "points": points,
    }
    return report


def write_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# HUM cache assembly",
        "",
        f"Generated: `{report['generated_at']}`",
        f"Pieces: `{report['piece_count']}`",
        "",
        "## Categories",
        "",
        "| Category | Count | Bytes |",
        "|---|---:|---:|",
    ]
    for name, bucket in sorted(report["categories"].items()):
        lines.append(f"| `{name}` | {bucket['count']} | {bucket['size_bytes']} |")
    if "interval_plot" in report:
        lines.extend(["", "## Interval plot", "", f"Formula: `{report['interval_plot']['formula']}`"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_svg(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    points = report.get("interval_plot", {}).get("points", [])
    width = 900
    height = 360
    pad = 40
    max_n = max([point["n"] for point in points], default=1)
    max_y = max([point["y"] for point in points], default=1)
    circles = []
    for point in points[:200]:
        x = pad + (point["n"] / max_n) * (width - pad * 2)
        y = height - pad - (point["y"] / max_y) * (height - pad * 2)
        circles.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="#58a6ff">'
            f"<title>{html.escape(point['id'])} {html.escape(point['path'])}</title></circle>"
        )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#0d1117"/>
  <text x="{pad}" y="25" fill="#c9d1d9" font-family="monospace" font-size="16">HUM cache interval plot: {html.escape(report.get('interval_plot', {}).get('formula', 'n/a'))}</text>
  <line x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{height-pad}" stroke="#30363d"/>
  <line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height-pad}" stroke="#30363d"/>
  {''.join(circles)}
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build HUM cache assembly evidence.")
    parser.add_argument("--root", action="append", default=["."], help="Root path to scan (repeatable)")
    parser.add_argument("--output-json", default="site/data/cache-assembly.json")
    parser.add_argument("--output-markdown", default="docs/HUM_CACHE_ASSEMBLY.generated.md")
    parser.add_argument("--output-svg", default="site/data/cache-interval-plot.svg")
    parser.add_argument("--max-files", type=int, default=5000)
    parser.add_argument("--hash-bytes", type=int, default=1024 * 1024)
    parser.add_argument("--exponent", type=float, default=1.5)
    parser.add_argument("--prefix", default="hum-cache")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = scan_cache([Path(root) for root in args.root], max_files=args.max_files, hash_bytes=args.hash_bytes)
    build_interval_plot(report, args.exponent, args.prefix)
    write_json(Path(args.output_json), report)
    write_markdown(Path(args.output_markdown), report)
    write_svg(Path(args.output_svg), report)
    print(f"cache pieces={report['piece_count']}")
    print(f"json={args.output_json}")
    print(f"markdown={args.output_markdown}")
    print(f"svg={args.output_svg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
