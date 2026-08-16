"""Tests for the LVM-cache HTTPS cert-broadcast desk."""

from __future__ import annotations

import json
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import hum_https_broadcast as broadcast  # noqa: E402


class TestBroadcastCache(unittest.TestCase):
    def test_resolve_cache_falls_back_locally(self) -> None:
        root = broadcast.resolve_cache_root(None)
        self.assertTrue(str(root).endswith("site/broadcast/cache"))

    def test_build_writes_searchable_inside_out_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            index = broadcast.write_inside_out(cache)
            self.assertTrue((cache / "show-and-tell.html").is_file())
            self.assertTrue((cache / "index.json").is_file())
            self.assertTrue((cache / "from-inside" / "login-map.txt").is_file())
            ids = {entry["id"] for entry in index["entries"]}
            self.assertIn("show-and-tell", ids)
            self.assertIn("ubuntu-server", ids)
            self.assertIn("hum-https-broadcast.service", index["concert"])
            hits = broadcast.search_index(index, "zorin")
            self.assertTrue(any(hit["id"] == "zorin" for hit in hits))
            warming = [row["id"] for row in index["trends"] if row["connotation"] == "warming"]
            self.assertIn("ubuntu-server", warming)

    def test_cert_and_https_search_and_key_forbidden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            tls = Path(tmp) / "tls"
            broadcast.write_inside_out(cache)
            info = broadcast.generate_cert(tls)
            self.assertTrue(Path(info["cert"]).is_file())
            self.assertNotIn("BEGIN PRIVATE KEY", Path(info["cert"]).read_text(encoding="utf-8"))
            self.assertIn(":", info["fingerprint"])

            thread = threading.Thread(
                target=broadcast.serve,
                args=("127.0.0.1", 8444, cache, Path(info["cert"]), Path(info["key"])),
                daemon=True,
            )
            thread.start()
            self._wait("https://127.0.0.1:8444/index.json")
            ctx = ssl._create_unverified_context()
            index = json.loads(urllib.request.urlopen("https://127.0.0.1:8444/index.json", context=ctx).read())
            self.assertGreaterEqual(len(index["entries"]), 3)
            cert_body = urllib.request.urlopen("https://127.0.0.1:8444/cert.pem", context=ctx).read()
            self.assertIn(b"BEGIN CERTIFICATE", cert_body)
            search = json.loads(
                urllib.request.urlopen("https://127.0.0.1:8444/search.json?q=login", context=ctx).read()
            )
            self.assertTrue(search["hits"])
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen("https://127.0.0.1:8444/key.pem", context=ctx)
            self.assertEqual(raised.exception.code, 403)

    def test_cli_cache_root_and_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "hum_https_broadcast.py"), "--cache", str(cache), "build"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("entries=", result.stdout)

    def test_systemd_concert_has_no_nbd_attach(self) -> None:
        for name in (
            "hum-housing.target",
            "hum-broadcast-cache.service",
            "hum-https-broadcast.service",
            "hum-login.service",
        ):
            text = (ROOT / "site" / "broadcast" / "systemd" / name).read_text(encoding="utf-8")
            self.assertNotIn("nbd0", text)
            self.assertNotIn("qemu-nbd", text)

    def _wait(self, url: str, timeout: float = 8.0) -> None:
        ctx = ssl._create_unverified_context()
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                urllib.request.urlopen(url, context=ctx, timeout=0.5)
                return
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(0.1)
        raise AssertionError(f"broadcast server did not start: {last}")


if __name__ == "__main__":
    unittest.main()
