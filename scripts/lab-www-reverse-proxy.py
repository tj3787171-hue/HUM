#!/usr/bin/env python3
"""
lab-www reverse proxy — runs on the host side of a lab-www netns veth pair.

Listens on LAB_WWW_HOST_IP (default 10.223.77.1) and forwards HTTP requests
to LAB_WWW_NS_IP (default 10.223.77.2) where a web server inside the
lab-www network namespace is expected to be running.

See lab-www.txt for the netns/veth bring-up steps and environment overrides.
"""

import http.server
import os
import signal
import socketserver
import sys
import urllib.error
import urllib.request

HOST_IP = os.environ.get("LAB_WWW_HOST_IP", "10.223.77.1")
NS_IP = os.environ.get("LAB_WWW_NS_IP", "10.223.77.2")
LISTEN_PORT = int(os.environ.get("LAB_WWW_LISTEN_PORT", "8080"))
UPSTREAM_PORT = int(os.environ.get("LAB_WWW_UPSTREAM_PORT", "80"))
UPSTREAM_TIMEOUT = int(os.environ.get("LAB_WWW_UPSTREAM_TIMEOUT", "30"))

UPSTREAM_BASE = f"http://{NS_IP}:{UPSTREAM_PORT}"

HOP_BY_HOP = frozenset(
    h.lower()
    for h in (
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    )
)


class ReverseProxyHandler(http.server.BaseHTTPRequestHandler):
    """Forward every request to the upstream inside the lab-www namespace."""

    server_version = "lab-www-reverse-proxy/1.0"

    # ---- shared plumbing ------------------------------------------------

    def _relay(self) -> None:
        upstream_url = f"{UPSTREAM_BASE}{self.path}"

        body = None
        content_length = self.headers.get("Content-Length")
        if content_length is not None:
            body = self.rfile.read(int(content_length))

        req = urllib.request.Request(upstream_url, data=body, method=self.command)

        for key, value in self.headers.items():
            if key.lower() in HOP_BY_HOP or key.lower() == "host":
                continue
            req.add_header(key, value)

        req.add_header("X-Forwarded-For", self.client_address[0])
        req.add_header("X-Forwarded-Host", self.headers.get("Host", HOST_IP))
        req.add_header("X-Forwarded-Proto", "http")

        try:
            with urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT) as resp:
                self.send_response(resp.status)
                for key, value in resp.headers.items():
                    if key.lower() not in HOP_BY_HOP:
                        self.send_header(key, value)
                self.end_headers()
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except urllib.error.HTTPError as exc:
            self.send_response(exc.code)
            for key, value in exc.headers.items():
                if key.lower() not in HOP_BY_HOP:
                    self.send_header(key, value)
            self.end_headers()
            body_bytes = exc.read()
            if body_bytes:
                self.wfile.write(body_bytes)
        except (urllib.error.URLError, OSError) as exc:
            self.send_error(502, f"Upstream unreachable: {exc}")

    # ---- method handlers ------------------------------------------------

    def do_GET(self) -> None:
        self._relay()

    def do_POST(self) -> None:
        self._relay()

    def do_PUT(self) -> None:
        self._relay()

    def do_DELETE(self) -> None:
        self._relay()

    def do_PATCH(self) -> None:
        self._relay()

    def do_HEAD(self) -> None:
        self._relay()

    def do_OPTIONS(self) -> None:
        self._relay()

    # ---- logging --------------------------------------------------------

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write(
            f"[lab-www-proxy] {self.client_address[0]} "
            f"-> {NS_IP}:{UPSTREAM_PORT} "
            f"{fmt % args}\n"
        )


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True
    allow_reuse_port = True


def main() -> None:
    bind = os.environ.get("LAB_WWW_BIND", HOST_IP)
    server = ReusableTCPServer((bind, LISTEN_PORT), ReverseProxyHandler)

    def _shutdown(signum: int, _frame: object) -> None:
        sys.stderr.write(f"\n[lab-www-proxy] caught signal {signum}, shutting down\n")
        server.shutdown()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    sys.stderr.write(
        f"[lab-www-proxy] listening on {bind}:{LISTEN_PORT} "
        f"-> upstream {NS_IP}:{UPSTREAM_PORT}\n"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
