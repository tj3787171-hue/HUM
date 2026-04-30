from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from websetup.sdv import macsec_apply, pool
from scripts.validate_virtual_setup import validate_virtual_setup
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


class TestVirtualBindingsConsistency(unittest.TestCase):
    def test_bindings_schema_requires_binding_id(self) -> None:
        base = Path(__file__).resolve().parent.parent / "websetup" / "virtual" / "schemas"
        schema = json.loads((base / "bindings.schema.json").read_text(encoding="utf-8"))
        required = schema["properties"]["bindings"]["items"]["required"]
        self.assertIn("id", required)

    def test_bindings_entries_include_id_and_allocatable_range_ref(self) -> None:
        bindings_path = Path(__file__).resolve().parent.parent / "websetup" / "virtual" / "bindings.json"
        payload = json.loads(bindings_path.read_text(encoding="utf-8"))
        entries = payload.get("bindings", [])
        self.assertTrue(entries, msg="bindings list should not be empty")
        for entry in entries:
            self.assertIn("id", entry)
            self.assertTrue(str(entry["id"]).strip())

        joined = json.dumps(payload, sort_keys=True)
        self.assertIn("allocatable_range", joined)


class TestVirtualSetupValidator(unittest.TestCase):
    def test_virtual_setup_validator_ok_for_repo_defaults(self) -> None:
        repo = Path(__file__).resolve().parent.parent
        ok, errors = validate_virtual_setup(
            inventory_path=repo / "websetup" / "virtual" / "inventory.csv",
            network_matrix_path=repo / "websetup" / "virtual" / "network-matrix.json",
            manifest_path=repo / "websetup" / "sdv" / "manifest.json",
        )
        self.assertTrue(ok, msg="\n".join(errors))
        self.assertEqual(errors, [])

    def test_virtual_setup_validator_detects_out_of_range_workload_ip(self) -> None:
        repo = Path(__file__).resolve().parent.parent
        inventory_src = (repo / "websetup" / "virtual" / "inventory.csv").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as td:
            temp_inventory = Path(td) / "inventory.csv"
            temp_inventory.write_text(
                inventory_src.replace("10.11.8.200", "10.11.9.200"),
                encoding="utf-8",
            )
            ok, errors = validate_virtual_setup(
                inventory_path=temp_inventory,
                network_matrix_path=repo / "websetup" / "virtual" / "network-matrix.json",
                manifest_path=repo / "websetup" / "sdv" / "manifest.json",
            )
            self.assertFalse(ok)
            joined = "\n".join(errors)
            self.assertIn("outside SDV subnet", joined)


class TestLvmLocationCloudPlan(unittest.TestCase):
    def test_lvm_cloud_plan_writes_non_destructive_action_report(self) -> None:
        repo = Path(__file__).resolve().parent.parent
        script = repo / "scripts" / "hum-lvm-cloud-plan.py"
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "plan.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--source",
                    str(repo),
                    "--cloud-root",
                    str(repo),
                    "--output",
                    str(output),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertIn("LVM/cloud plan written", completed.stdout)
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["sources"][0]["path"], str(repo))
        self.assertTrue(payload["sources"][0]["exists"])
        self.assertTrue(payload["cloud_roots"][0]["exists"])
        self.assertIn("automatic_actions", payload)
        self.assertIn("recommended_actions", payload)
        self.assertEqual(payload["privacy_bindings"]["virtual_desktop_bind"], "127.0.0.1")

    def test_network_matrix_links_lvm_location_and_encrypted_cloud_services(self) -> None:
        repo = Path(__file__).resolve().parent.parent
        matrix = json.loads(
            (repo / "websetup" / "virtual" / "network-matrix.json").read_text(encoding="utf-8")
        )
        nodes = {node["id"]: node for node in matrix["nodes"]}
        edges = {(edge["from"], edge["to"], edge["type"]) for edge in matrix["edges"]}

        self.assertIn("location-services", nodes)
        self.assertIn("encrypted-cloud-services", nodes)
        self.assertIn("lvm-secure-cloud", nodes)
        self.assertIn(
            ("location-services", "lvm-secure-cloud", "metadata_feed"),
            edges,
        )
        self.assertIn(
            ("encrypted-cloud-services", "lvm-secure-cloud", "encrypted_storage_backend"),
            edges,
        )
        self.assertTrue(nodes["location-services"]["metadata"]["interactive_results"])
        self.assertTrue(nodes["lvm-secure-cloud"]["metadata"]["automatic_actions"])


if __name__ == "__main__":
    unittest.main()
