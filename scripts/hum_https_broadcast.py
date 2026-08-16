#!/usr/bin/env python3
"""Self-hosted HTTPS cert-broadcast server on an LVM-shaped cache.

Builds searchable hypertext from the inside (login, circuits, virtio map)
and serves it over TLS. The public certificate is broadcast; the private
key is never published. Default bind is 127.0.0.1. This is not a pentest
tool and does not attach VNC to nbd0.
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import shutil
import ssl
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "site" / "broadcast" / "pages"
DEFAULT_CACHE = ROOT / "site" / "broadcast" / "cache"
DEFAULT_TLS = ROOT / "site" / "broadcast" / "var" / "tls"
DEFAULT_BIND = "127.0.0.1"
DEFAULT_PORT = 8443


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_cache_root(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("HUM_LVM_CACHE")
    if env:
        return Path(env).expanduser().resolve()
    virtual = Path("/mnt/virtual-drive")
    if virtual.is_dir() and os.path.ismount(str(virtual)):
        return (virtual / "hum-cache").resolve()
    return DEFAULT_CACHE.resolve()


def cert_fingerprint(cert_path: Path) -> str:
    digest = hashlib.sha256(cert_path.read_bytes()).hexdigest()
    return ":".join(digest[i : i + 2] for i in range(0, 64, 2))


def generate_cert(tls_dir: Path, common_name: str = "hum.local") -> dict[str, str]:
    tls_dir.mkdir(parents=True, exist_ok=True)
    cert = tls_dir / "cert.pem"
    key = tls_dir / "key.pem"
    if shutil.which("openssl") is None:
        raise RuntimeError("openssl is required to mint a local broadcast certificate")
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "365",
            "-nodes",
            "-subj",
            f"/CN={common_name}",
            "-addext",
            f"subjectAltName=DNS:{common_name},DNS:localhost,IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    os.chmod(key, 0o600)
    return {"cert": str(cert), "key": str(key), "fingerprint": cert_fingerprint(cert)}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def inside_out_entries() -> list[dict[str, Any]]:
    catalog = load_json(ROOT / "site" / "circuits" / "data" / "iso-catalog.json")
    entries = [
        {
            "id": "show-and-tell",
            "title": "Desktop agent show and tell",
            "path": "/show-and-tell.html",
            "kind": "handoff",
            "tags": ["collab", "virtio", "login", "broadcast"],
            "warmth": 3,
        },
        {
            "id": "search",
            "title": "Frontend search of the housing cache",
            "path": "/search.html",
            "kind": "search",
            "tags": ["frontend", "index"],
            "warmth": 2,
        },
        {
            "id": "login",
            "title": "SQL login desk",
            "path": "/from-inside/login-map.txt",
            "kind": "signin",
            "tags": ["php", "sqlite", "collision"],
            "warmth": 3,
        },
    ]
    for item in catalog.get("isos", []):
        phase = str(item.get("phase", "optional"))
        warmth = {"present": 3, "optional": 2, "optional-onsite": 1}.get(phase, 1)
        entries.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "path": f"/from-inside/iso/{item.get('id')}.txt",
                "kind": "iso",
                "tags": [phase, item.get("family", ""), "virtio"],
                "warmth": warmth,
            }
        )
    return entries


def trend_rows(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(entries, key=lambda item: (-int(item.get("warmth", 0)), str(item.get("title"))))
    return [
        {
            "id": item["id"],
            "title": item["title"],
            "connotation": "warming" if int(item.get("warmth", 0)) >= 3 else "held",
            "warmth": item.get("warmth"),
        }
        for item in ranked
    ]


def write_inside_out(cache: Path) -> dict[str, Any]:
    cache.mkdir(parents=True, exist_ok=True)
    inside = cache / "from-inside"
    inside.mkdir(parents=True, exist_ok=True)
    (inside / "iso").mkdir(exist_ok=True)

    (inside / "login-map.txt").write_text(
        "SQL login desk at site/login/\n"
        "One session covers URL, future APK/PKG on the same origin, and loopback VNC.\n"
        "nbd0 attach stays denied.\n",
        encoding="utf-8",
    )
    for name in ("iso-catalog.json", "zones.json", "posts.xml", "signin-options.xml"):
        source = ROOT / "site" / "circuits" / "data" / name
        if source.is_file():
            shutil.copy2(source, inside / name)

    catalog = load_json(ROOT / "site" / "circuits" / "data" / "iso-catalog.json")
    for item in catalog.get("isos", []):
        (inside / "iso" / f"{item['id']}.txt").write_text(
            f"{item.get('title')}\nphase={item.get('phase')}\nfamily={item.get('family')}\nbundle={item.get('bundle')}\n",
            encoding="utf-8",
        )

    if PAGES.is_dir():
        for path in PAGES.rglob("*"):
            if path.is_file():
                target = cache / path.relative_to(PAGES)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)

    entries = inside_out_entries()
    index = {
        "generated_at": utc_now(),
        "housing": "lvm-cache-or-local-fallback",
        "cache": str(cache),
        "bind_default": f"{DEFAULT_BIND}:{DEFAULT_PORT}",
        "vnc_nbd": "denied",
        "entries": entries,
        "trends": trend_rows(entries),
        "concert": [
            "hum-housing.target",
            "hum-broadcast-cache.service",
            "hum-https-broadcast.service",
            "hum-login.service",
        ],
    }
    (cache / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    (cache / "trends.json").write_text(json.dumps(index["trends"], indent=2) + "\n", encoding="utf-8")
    return index


def search_index(index: dict[str, Any], query: str) -> list[dict[str, Any]]:
    needle = query.strip().lower()
    if not needle:
        return list(index.get("entries", []))
    hits = []
    for entry in index.get("entries", []):
        hay = " ".join(
            [
                str(entry.get("id", "")),
                str(entry.get("title", "")),
                str(entry.get("kind", "")),
                " ".join(str(tag) for tag in entry.get("tags", [])),
            ]
        ).lower()
        if needle in hay:
            hits.append(entry)
    return hits


class BroadcastHandler(http.server.SimpleHTTPRequestHandler):
    cache_root: Path = DEFAULT_CACHE
    public_cert: Path | None = None
    index_payload: dict[str, Any] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(self.cache_root), **kwargs)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _send_bytes(self, payload: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/cert.pem", "/.well-known/hum-cert.pem"):
            if self.public_cert is None or not self.public_cert.is_file():
                self.send_error(404)
                return
            self._send_bytes(self.public_cert.read_bytes(), "application/x-pem-file")
            return
        if parsed.path == "/search.json":
            query = parse_qs(parsed.query).get("q", [""])[0]
            hits = search_index(self.index_payload, query)
            self._send_bytes(json.dumps({"q": query, "hits": hits}).encode("utf-8"), "application/json")
            return
        if parsed.path in ("/key.pem", "/from-inside/key.pem"):
            self.send_error(403, "private key is not broadcast")
            return
        super().do_GET()


def serve(host: str, port: int, cache: Path, cert: Path, key: Path) -> None:
    index_path = cache / "index.json"
    payload = load_json(index_path) if index_path.is_file() else write_inside_out(cache)
    handler = BroadcastHandler
    handler.directory = str(cache)
    handler.cache_root = cache
    handler.public_cert = cert
    handler.index_payload = payload
    httpd = http.server.ThreadingHTTPServer((host, port), handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=str(cert), keyfile=str(key))
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    print(f"https://{host}:{port}/ cache={cache} cert={cert}")
    httpd.serve_forever()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HUM HTTPS cert-broadcast on an LVM-shaped cache.")
    parser.add_argument("--cache", default=None, help="Cache root (LVM mount, HUM_LVM_CACHE, or local fallback).")
    parser.add_argument("--tls-dir", default=str(DEFAULT_TLS))
    parser.add_argument("--host", default=DEFAULT_BIND)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("cache-root", help="Print the resolved cache directory.")
    sub.add_parser("build", help="Write inside-out hypertext and the search index.")
    sub.add_parser("cert", help="Mint a local self-signed certificate. Does not print the key.")
    sub.add_parser("serve", help="Serve the cache over HTTPS and broadcast the public cert.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cache = resolve_cache_root(args.cache)
    tls_dir = Path(args.tls_dir)
    if args.command == "cache-root":
        print(cache)
        return 0
    if args.command == "build":
        index = write_inside_out(cache)
        print(f"entries={len(index['entries'])} cache={cache}")
        return 0
    if args.command == "cert":
        info = generate_cert(tls_dir)
        print(f"cert={info['cert']}")
        print(f"fingerprint={info['fingerprint']}")
        return 0
    if args.command == "serve":
        cert = tls_dir / "cert.pem"
        key = tls_dir / "key.pem"
        if not cert.is_file() or not key.is_file():
            generate_cert(tls_dir)
        if not (cache / "index.json").is_file():
            write_inside_out(cache)
        serve(args.host, args.port, cache, cert, key)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
