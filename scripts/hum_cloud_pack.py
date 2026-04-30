#!/usr/bin/env python3
"""Create encrypted, compressed cloud directories from local files."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import shutil
import sys
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_CHUNK_SIZE = 4096
MIN_CHUNK_SIZE = 1024
DEFAULT_COMPRESSION_LEVEL = 6
DEFAULT_KDF_ITERATIONS = 200_000


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_chunk_size(chunk_size: int) -> int:
    if chunk_size < MIN_CHUNK_SIZE:
        raise ValueError(
            f"chunk size must be >= {MIN_CHUNK_SIZE}, got {chunk_size}"
        )
    return chunk_size


def _derive_key(passphrase: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8"),
        salt,
        iterations,
        dklen=32,
    )


def _stream_keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(
            key + nonce + counter.to_bytes(8, byteorder="big")
        ).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))


def _encrypt_chunk(plaintext: bytes, key: bytes) -> bytes:
    nonce = os.urandom(16)
    keystream = _stream_keystream(key, nonce, len(plaintext))
    ciphertext = _xor_bytes(plaintext, keystream)
    tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    return nonce + tag + ciphertext


def _decrypt_chunk(blob: bytes, key: bytes) -> bytes:
    if len(blob) < 48:
        raise ValueError("encrypted chunk is too small")
    nonce = blob[:16]
    tag = blob[16:48]
    ciphertext = blob[48:]
    expected = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("chunk authentication failed")
    keystream = _stream_keystream(key, nonce, len(ciphertext))
    return _xor_bytes(ciphertext, keystream)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _list_files(source: Path) -> list[Path]:
    files = [path for path in source.rglob("*") if path.is_file()]
    files.sort(key=lambda item: str(item.relative_to(source)))
    return files


def _load_passphrase(raw_passphrase: str | None, env_name: str) -> str:
    if raw_passphrase:
        return raw_passphrase
    from_env = os.environ.get(env_name)
    if from_env:
        return from_env
    raise ValueError(
        f"missing passphrase: set --passphrase or export {env_name}"
    )


def _reset_output_dir(path: Path, force: bool) -> None:
    if path.exists():
        if not force:
            raise FileExistsError(
                f"{path} already exists (use --force to overwrite)"
            )
            raise FileExistsError(f"{path} already exists (use --force to overwrite)")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _write_online_index(cloud_dir: Path, manifest: dict[str, Any]) -> None:
    summary = manifest["summary"]
    html = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        "<title>HUM Cloud Directory</title>",
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;}"
        "code{background:#f5f5f5;padding:.1rem .3rem;border-radius:4px;}"
        "table{border-collapse:collapse;margin-top:1rem;}"
        "td,th{border:1px solid #ddd;padding:.4rem .6rem;text-align:left;}"
        "</style></head><body>",
        "<h1>HUM cloud directory</h1>",
        f"<p><strong>Aggregate SHA-256:</strong> "
        f"<code>{summary['aggregate_sha256']}</code></p>",
        "<table><thead><tr><th>File</th><th>Bytes</th><th>SHA-256</th></tr>"
        "</thead><tbody>",
    ]
    for item in manifest["files"]:
        html.append(
            "<tr>"
            f"<td>{item['path']}</td>"
            f"<td>{item['size']}</td>"
            f"<td><code>{item['sha256']}</code></td>"
            "</tr>"
        )
    html.extend(
        [
            "</tbody></table>",
            '<p>Manifest: <a href="./index.json">index.json</a></p>',
            "</body></html>",
        ]
    )
    (cloud_dir / "online-index.html").write_text(
        "\n".join(html), encoding="utf-8"
    )
    html_rows = []
    for item in manifest["files"]:
        html_rows.append(
            "<tr>"
            f"<td>{html.escape(item['path'])}</td>"
            f"<td>{item['size']}</td>"
            f"<td><code>{html.escape(item['sha256'])}</code></td>"
            "</tr>"
        )

    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>HUM Cloud Directory</title>
  <style>
    body{{font-family:system-ui,sans-serif;margin:2rem;line-height:1.5;}}
    code{{background:#f5f5f5;padding:.1rem .3rem;border-radius:4px;}}
    table{{border-collapse:collapse;margin-top:1rem;}}
    td,th{{border:1px solid #ddd;padding:.4rem .6rem;text-align:left;}}
  </style>
</head>
<body>
  <h1>HUM cloud directory</h1>
  <p><strong>Aggregate SHA-256:</strong> <code>{summary['aggregate_sha256']}</code></p>
  <table>
    <thead><tr><th>File</th><th>Bytes</th><th>SHA-256</th></tr></thead>
    <tbody>
      {''.join(html_rows)}
    </tbody>
  </table>
  <p>Manifest: <a href="./index.json">index.json</a></p>
</body>
</html>
"""
    (cloud_dir / "online-index.html").write_text(page, encoding="utf-8")


@dataclass
class PackResult:
    manifest: dict[str, Any]
    manifest_path: Path


def pack_directory(
    source: Path,
    cloud_dir: Path,
    passphrase: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    compression_level: int = DEFAULT_COMPRESSION_LEVEL,
    expected_aggregate_sha256: str | None = None,
    force: bool = False,
    write_online_index: bool = True,
) -> PackResult:
    chunk_size = _validate_chunk_size(chunk_size)
    if not source.is_dir():
        raise NotADirectoryError(f"source directory not found: {source}")
    if compression_level < 0 or compression_level > 9:
        raise ValueError("compression level must be in range 0..9")

    _reset_output_dir(cloud_dir, force=force)
    chunk_dir = cloud_dir / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)

    files = _list_files(source)
    salt = os.urandom(16)
    key = _derive_key(passphrase, salt, DEFAULT_KDF_ITERATIONS)
    aggregate_hasher = hashlib.sha256()
    file_entries: list[dict[str, Any]] = []
    chunk_count = 0
    plain_bytes = 0
    compressed_bytes = 0

    for file_idx, path in enumerate(files):
        rel = path.relative_to(source).as_posix()
        stat = path.stat()
        per_file_hasher = hashlib.sha256()
        file_chunks: list[dict[str, Any]] = []
        offset = 0
        chunk_idx = 0

        with path.open("rb") as handle:
            while True:
                block = handle.read(chunk_size)
                if not block:
                    break
                per_file_hasher.update(block)
                compressed = zlib.compress(block, level=compression_level)
                encrypted = _encrypt_chunk(compressed, key)
                chunk_name = f"f{file_idx:05d}-c{chunk_idx:05d}.bin"
                chunk_path = chunk_dir / chunk_name
                chunk_path.write_bytes(encrypted)

                file_chunks.append(
                    {
                        "name": chunk_name,
                        "offset": offset,
                        "plain_size": len(block),
                        "compressed_size": len(compressed),
                        "encrypted_size": len(encrypted),
                        "sha256_plain": _sha256_hex(block),
                        "sha256_compressed": _sha256_hex(compressed),
                        "sha256_encrypted": _sha256_hex(encrypted),
                    }
                )
                offset += len(block)
                chunk_idx += 1
                chunk_count += 1
                plain_bytes += len(block)
                compressed_bytes += len(compressed)

        file_sha = per_file_hasher.hexdigest()
        aggregate_hasher.update(rel.encode("utf-8"))
        aggregate_hasher.update(b"\0")
        aggregate_hasher.update(file_sha.encode("ascii"))
        aggregate_hasher.update(b"\n")
        file_entries.append(
            {
                "path": rel,
                "size": stat.st_size,
                "mtime_epoch": int(stat.st_mtime),
                "sha256": file_sha,
                "chunks": file_chunks,
            }
        )

    aggregate_sha = aggregate_hasher.hexdigest()
    if expected_aggregate_sha256 and expected_aggregate_sha256 != aggregate_sha:
        raise ValueError(
            "aggregate SHA-256 mismatch: "
            f"expected {expected_aggregate_sha256}, got {aggregate_sha}"
        )

    compression_ratio = 0.0
    if plain_bytes:
        compression_ratio = compressed_bytes / plain_bytes

    manifest = {
        "format": "hum-cloud-pack-v1",
        "created_at_utc": _utc_now_iso(),
        "source_directory": str(source.resolve()),
        "chunk_size": chunk_size,
        "minimum_chunk_size": MIN_CHUNK_SIZE,
        "compression": {"method": "zlib", "level": compression_level},
        "encryption": {
            "cipher": "sha256-stream-xor+hmac-sha256",
            "kdf": "pbkdf2_hmac_sha256",
            "kdf_iterations": DEFAULT_KDF_ITERATIONS,
            "kdf_salt_base64": base64.b64encode(salt).decode("ascii"),
        },
        "files": file_entries,
        "summary": {
            "file_count": len(file_entries),
            "chunk_count": chunk_count,
            "plain_bytes": plain_bytes,
            "compressed_bytes": compressed_bytes,
            "compression_ratio": round(compression_ratio, 6),
            "aggregate_sha256": aggregate_sha,
        },
    }
    manifest_path = cloud_dir / "index.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if write_online_index:
        _write_online_index(cloud_dir, manifest)

    return PackResult(manifest=manifest, manifest_path=manifest_path)


def restore_directory(
    cloud_dir: Path,
    target_dir: Path,
    passphrase: str,
    *,
    overwrite: bool = False,
) -> Path:
    manifest_path = cloud_dir / "index.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != "hum-cloud-pack-v1":
        raise ValueError("unsupported manifest format")

    if target_dir.exists() and any(target_dir.iterdir()) and not overwrite:
        raise FileExistsError(
            f"{target_dir} is not empty (use --overwrite to allow writes)"
        )
    target_dir.mkdir(parents=True, exist_ok=True)

    salt = base64.b64decode(manifest["encryption"]["kdf_salt_base64"])
    iterations = int(manifest["encryption"]["kdf_iterations"])
    key = _derive_key(passphrase, salt, iterations)

    for file_entry in manifest["files"]:
        rel_path = Path(file_entry["path"])
        out_path = target_dir / rel_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        file_hasher = hashlib.sha256()
        with out_path.open("wb") as out:
            for chunk in file_entry["chunks"]:
                enc_path = cloud_dir / "chunks" / chunk["name"]
                encrypted = enc_path.read_bytes()
                if _sha256_hex(encrypted) != chunk["sha256_encrypted"]:
                    raise ValueError(
                        f"encrypted checksum mismatch for {chunk['name']}"
                    )
                compressed = _decrypt_chunk(encrypted, key)
                if _sha256_hex(compressed) != chunk["sha256_compressed"]:
                    raise ValueError(
                        f"compressed checksum mismatch for {chunk['name']}"
                    )
                block = zlib.decompress(compressed)
                if _sha256_hex(block) != chunk["sha256_plain"]:
                    raise ValueError(
                        f"plain checksum mismatch for {chunk['name']}"
                    )
                out.write(block)
                file_hasher.update(block)
        if file_hasher.hexdigest() != file_entry["sha256"]:
            raise ValueError(
                f"file checksum mismatch after restore: {file_entry['path']}"
            )

    return target_dir


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create and restore encrypted cloud directories with "
            "chunk-based compression."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    pack = sub.add_parser("pack", help="create cloud directory")
    pack.add_argument("--source", required=True, help="source directory")
    pack.add_argument("--cloud-dir", required=True, help="output directory")
    pack.add_argument("--passphrase", help="encryption passphrase")
    pack.add_argument(
        "--passphrase-env",
        default="HUM_CLOUD_PASSPHRASE",
        help="fallback env var for passphrase",
    )
    pack.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help=f"chunk size in bytes (default: {DEFAULT_CHUNK_SIZE})",
    )
    pack.add_argument(
        "--compression-level",
        type=int,
        default=DEFAULT_COMPRESSION_LEVEL,
        help="zlib compression level (0-9)",
    )
    pack.add_argument(
        "--expected-aggregate-sha256",
        help="optional aggregate checksum expected value",
    )
    pack.add_argument(
        "--force",
        action="store_true",
        help="remove cloud dir before writing",
    )
    pack.add_argument(
        "--no-online-index",
        action="store_true",
        help="skip online-index.html generation",
    )

    restore = sub.add_parser("restore", help="restore cloud directory")
    restore.add_argument("--cloud-dir", required=True, help="cloud directory")
    restore.add_argument("--target-dir", required=True, help="restore target")
    restore.add_argument("--passphrase", help="encryption passphrase")
    restore.add_argument(
        "--passphrase-env",
        default="HUM_CLOUD_PASSPHRASE",
        help="fallback env var for passphrase",
    )
    restore.add_argument(
        "--overwrite",
        action="store_true",
        help="allow writing into a non-empty target",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        passphrase = _load_passphrase(args.passphrase, args.passphrase_env)
        if args.command == "pack":
            result = pack_directory(
                Path(args.source),
                Path(args.cloud_dir),
                passphrase,
                chunk_size=args.chunk_size,
                compression_level=args.compression_level,
                expected_aggregate_sha256=args.expected_aggregate_sha256,
                force=args.force,
                write_online_index=not args.no_online_index,
            )
            aggregate = result.manifest["summary"]["aggregate_sha256"]
            print(f"cloud_dir={args.cloud_dir}")
            print(f"manifest={result.manifest_path}")
            print(f"aggregate_sha256={aggregate}")
            print(f"cloud_dir={args.cloud_dir}")
            print(f"manifest={result.manifest_path}")
            print(f"aggregate_sha256={result.manifest['summary']['aggregate_sha256']}")
            return 0

        restore_directory(
            Path(args.cloud_dir),
            Path(args.target_dir),
            passphrase,
            overwrite=args.overwrite,
        )
        print(f"restored_to={Path(args.target_dir).resolve()}")
        return 0

    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
