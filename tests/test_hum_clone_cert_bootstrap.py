"""Tests for scripts/hum_clone_cert_bootstrap.py."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import hum_clone_cert_bootstrap as boot  # noqa: E402


class TestCloneCertBegin(unittest.TestCase):
    def test_begin_without_cert_vars_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            clone_root = home / "src"
            env = {
                "HUM_CLONE_ROOT": str(clone_root),
                "HUM_TLS_CERT": "",
                "HUM_TLS_KEY": "",
                "HUM_TLS_CA": "",
                "SSL_CERT_FILE": "",
                "GIT_SSL_CAINFO": "",
                "NODE_EXTRA_CA_CERTS": "",
                "REQUESTS_CA_BUNDLE": "",
                "CURL_CA_BUNDLE": "",
            }
            output = home / "report.json"
            with mock.patch.dict(os.environ, env, clear=False):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = boot.main(
                        [
                            "begin",
                            "--repo-root",
                            str(home),
                            "--output",
                            str(output),
                        ]
                    )
            self.assertEqual(code, 2)
            self.assertTrue(clone_root.is_dir())
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(payload["cert_variables_underway"])
            self.assertTrue(payload["clone_root_ready"])

    def test_begin_with_declared_ca_is_underway(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            clone_root = home / "src"
            ca = home / "lab-ca.pem"
            ca.write_text("-----BEGIN CERTIFICATE-----\nlab\n", encoding="utf-8")
            env = {
                "HUM_CLONE_ROOT": str(clone_root),
                "SSL_CERT_FILE": str(ca),
                "GIT_SSL_CAINFO": str(ca),
                "HUM_TLS_CERT": "",
                "HUM_TLS_KEY": "",
                "HUM_TLS_CA": "",
                "NODE_EXTRA_CA_CERTS": "",
                "REQUESTS_CA_BUNDLE": "",
                "CURL_CA_BUNDLE": "",
            }
            output = home / "report.json"
            with mock.patch.dict(os.environ, env, clear=False):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = boot.main(
                        [
                            "begin",
                            "--repo-root",
                            str(home),
                            "--output",
                            str(output),
                        ]
                    )
            self.assertEqual(code, 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(payload["cert_variables_underway"])
            self.assertTrue(payload["cert_files_ready"])
            self.assertIn("python3 scripts/hum_bind_bridge.py plan --no-probe", payload["next_steps"])

    def test_declared_missing_file_is_underway_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            checks = [
                boot.check_named_path(
                    "SSL_CERT_FILE",
                    str(home / "missing-ca.pem"),
                    "cert-path",
                ),
                boot.check_named_path("HUM_TLS_CERT", "", "cert-path"),
                boot.check_named_path("HUM_TLS_KEY", "", "cert-path"),
                boot.check_named_path("HUM_TLS_CA", "", "cert-path"),
                boot.check_named_path("GIT_SSL_CAINFO", "", "cert-path"),
                boot.check_named_path("NODE_EXTRA_CA_CERTS", "", "cert-path"),
                boot.check_named_path("REQUESTS_CA_BUNDLE", "", "cert-path"),
                boot.check_named_path("CURL_CA_BUNDLE", "", "cert-path"),
            ]
            self.assertTrue(boot.certs_underway(checks))
            self.assertFalse(boot.cert_files_ready(checks))


if __name__ == "__main__":
    unittest.main()
