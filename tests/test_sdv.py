from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from websetup.sdv import macsec_apply, pool
from websetup.sdv.runner import load_manifest


class TestSdvPool(unittest.TestCase):
    def test_validate_manifest_defaults_ok(self) -> None:
        manifest = load_manifest()
        ok, message = pool.validate_network(manifest)
        self.assertTrue(ok, msg=message)

    def test_validate_rejects_wrong_allocatable_range(self) -> None:
        manifest = load_manifest()
        network = dict(manifest["network"])
        alloc = dict(network["allocatable_range"])
        alloc["start"] = "10.11.8.60"
        network["allocatable_range"] = alloc
        broken = dict(manifest)
        broken["network"] = network
        ok, message = pool.validate_network(broken)
        self.assertFalse(ok)
        self.assertIn("allocatable_range expected", message)


class TestMacsecApply(unittest.TestCase):
    def test_apply_rx_returns_zero_when_disabled(self) -> None:
        payload = {
            "links": [
                {
                    "macsec_dev": "macsec0",
                    "rx": {"enabled": False},
                }
            ]
        }
        self.assertEqual(macsec_apply.apply_rx(payload), 0)

    def test_read_key_hex_accepts_64_hex_chars(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            key_path = Path(td) / "macsec.key"
            key_path.write_text("a" * 64, encoding="utf-8")
            key_hex = macsec_apply._read_key_hex(str(key_path))
            self.assertEqual(len(key_hex), 64)


class TestManifestShape(unittest.TestCase):
    def test_manifest_json_has_allocatable_range(self) -> None:
        path = Path(__file__).resolve().parent.parent / "websetup" / "sdv" / "manifest.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("network", payload)
        self.assertIn("allocatable_range", payload["network"])


if __name__ == "__main__":
    unittest.main()
