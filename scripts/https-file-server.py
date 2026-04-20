#!/usr/bin/env python3
"""Serve files over HTTPS with optional HSTS response headers."""

from __future__ import annotations

import argparse
import functools
import http.server
import ssl
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simple HTTPS file server with optional HSTS support."
    )
    parser.add_argument("port", type=int, nargs="?", default=8443, help="Listen port")
    parser.add_argument(
        "--bind",
        default="0.0.0.0",
        help="Bind address (default: 0.0.0.0)",
    )
    parser.add_argument(
        "-d",
        "--directory",
        default=".",
        help="Directory to serve (default: current directory)",
    )
    parser.add_argument("--cert", required=True, help="Path to TLS certificate PEM")
    parser.add_argument("--key", required=True, help="Path to TLS private key PEM")
    parser.add_argument(
        "--hsts-max-age",
        type=int,
        default=0,
        help="Enable HSTS and set max-age seconds (0 disables HSTS)",
    )
    parser.add_argument(
        "--hsts-include-subdomains",
        action="store_true",
        help="Add includeSubDomains to HSTS header",
    )
    parser.add_argument(
        "--hsts-preload",
        action="store_true",
        help="Add preload to HSTS header",
    )
    return parser.parse_args()


def build_hsts_header(
    max_age: int, include_subdomains: bool, preload: bool
) -> str | None:
    if max_age <= 0:
        return None
    parts = [f"max-age={max_age}"]
    if include_subdomains:
        parts.append("includeSubDomains")
    if preload:
        parts.append("preload")
    return "; ".join(parts)


def main() -> int:
    args = parse_args()

    cert = Path(args.cert).expanduser().resolve()
    key = Path(args.key).expanduser().resolve()
    serve_dir = Path(args.directory).expanduser().resolve()

    if not cert.is_file():
        raise FileNotFoundError(f"certificate file not found: {cert}")
    if not key.is_file():
        raise FileNotFoundError(f"key file not found: {key}")
    if not serve_dir.is_dir():
        raise NotADirectoryError(f"directory not found: {serve_dir}")

    hsts_value = build_hsts_header(
        max_age=args.hsts_max_age,
        include_subdomains=args.hsts_include_subdomains,
        preload=args.hsts_preload,
    )

    class Handler(http.server.SimpleHTTPRequestHandler):
        def end_headers(self) -> None:  # type: ignore[override]
            if hsts_value:
                self.send_header("Strict-Transport-Security", hsts_value)
            super().end_headers()

    handler = functools.partial(Handler, directory=str(serve_dir))
    httpd = http.server.ThreadingHTTPServer((args.bind, args.port), handler)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=str(cert), keyfile=str(key))
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

    print(f"Serving HTTPS: {serve_dir}")
    print(f"URL: https://{args.bind}:{args.port}/")
    if hsts_value:
        print(f"HSTS: {hsts_value}")

    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
