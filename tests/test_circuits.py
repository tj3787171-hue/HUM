"""Tests for virtio housing, isolation zones, and circuit blog data."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CIRCUITS = ROOT / "site" / "circuits"


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


zones = load_script("hum_isolation_zones", "hum-isolation-zones.py")
drift = load_script("hum_ip_drift", "hum-ip-drift.py")


class TestIsoCatalog(unittest.TestCase):
    def test_present_tracks_and_optional_onsite(self) -> None:
        catalog = json.loads((CIRCUITS / "data" / "iso-catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["guest_disk"], "/dev/vda")
        self.assertEqual(catalog["host_disk"], "/dev/sda")
        self.assertEqual(catalog["nbd_export"]["vnc_attach"], "denied")
        ids = {item["id"]: item for item in catalog["isos"]}
        for name in ("ubuntu-server", "kali-desktop", "zorin"):
            self.assertEqual(ids[name]["phase"], "present")
            self.assertFalse(ids[name]["bundle"])
        self.assertTrue(ids["windows-11"]["operator_iso"])
        self.assertTrue(ids["sequoia-macos"]["operator_iso"])
        self.assertFalse(ids["windows-11"]["bundle"])


class TestIsolationZones(unittest.TestCase):
    def test_vnc_never_shares_nbd_zone(self) -> None:
        catalog = json.loads((CIRCUITS / "data" / "iso-catalog.json").read_text(encoding="utf-8"))
        plan = zones.allocate_zones(3, catalog)
        self.assertEqual(plan["nbd0"]["vnc_attach"], "denied")
        self.assertEqual(plan["nbd0"]["zone"], 300)
        for guest in plan["guests"]:
            self.assertNotEqual(guest["display_zone"], 300)
            self.assertFalse(guest["vnc_shares_nbd"])
            self.assertEqual(guest["vnc_bind"], "127.0.0.1")
            self.assertTrue(guest["dummy_rail"].startswith("hum-dummy"))

    def test_attach_flag_is_rejected(self) -> None:
        plan = zones.allocate_zones(1)
        plan["nbd0"]["vnc_attach"] = "allowed"
        with self.assertRaises(RuntimeError):
            zones.assert_vnc_nbd_separated(plan)

    def test_cli_plan_and_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "zones.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "hum-isolation-zones.py"),
                    "--output",
                    str(output),
                    "write",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["virtio"]["guest"], "/dev/vda")
            self.assertEqual(payload["nbd0"]["vnc_attach"], "denied")


class TestIpDrift(unittest.TestCase):
    def test_matched_and_drifted(self) -> None:
        ok = drift.drift_report("192.168.68.100/22", ["192.168.68.100"])
        self.assertTrue(ok["matched"])
        self.assertEqual(ok["octet_delta"], 0)
        moved = drift.drift_report("192.168.68.100/22", ["192.168.68.110"])
        self.assertFalse(moved["matched"])
        self.assertEqual(moved["octet_delta"], 10)

    def test_plan_cli_does_not_apply(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "hum-ip-drift.py"),
                "--expected",
                "192.168.68.100/22",
                "--current",
                "10.0.0.8",
                "plan",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("hum-host-static-ip.sh apply", payload["correct_command"])
        self.assertFalse(payload["matched"])


class TestCircuitBlog(unittest.TestCase):
    def test_posts_and_signin_xml_parse(self) -> None:
        for name in ("posts.xml", "signin-options.xml"):
            with (CIRCUITS / "data" / name).open("rb") as handle:
                ET.parse(handle)

    def test_php_pages_exist(self) -> None:
        for name in ("index.php", "iso.php", "zones.php", "risk.php", "includes/blog.php"):
            self.assertTrue((CIRCUITS / name).is_file())


if __name__ == "__main__":
    unittest.main()
