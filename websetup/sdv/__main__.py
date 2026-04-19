"""CLI entry point for Software-Defined Validation."""

from __future__ import annotations

import argparse
from pathlib import Path

from websetup.sdv import pool
from websetup.sdv.runner import apply, load_manifest


def cmd_validate(args: argparse.Namespace) -> int:
    manifest = load_manifest(Path(args.manifest).resolve() if args.manifest else None)
    ok, message = pool.validate_network(manifest)
    if not ok:
        raise ValueError(message)
    print(f"[sdv] {message}")
    manifest = load_manifest(Path(args.manifest) if args.manifest else None)
    pool.validate_network(manifest["network"])
    print("[sdv] manifest network block OK")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).resolve() if args.manifest else None
    manifest = load_manifest(manifest_path)
    apply(manifest, root=Path.cwd())
    apply(Path(args.manifest) if args.manifest else None)
    print("[sdv] apply complete")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="websetup SDV toolkit")
    sub = parser.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="validate SDV manifest network block")
    v.add_argument(
        "-m",
        "--manifest",
        help="path to manifest JSON (defaults to websetup/sdv/manifest.json)",
    )
    v.set_defaults(func=cmd_validate)

    a = sub.add_parser("apply", help="apply SDV workflow")
    a.add_argument(
        "-m",
        "--manifest",
        help="path to manifest JSON (defaults to websetup/sdv/manifest.json)",
    )
    a.set_defaults(func=cmd_apply)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
