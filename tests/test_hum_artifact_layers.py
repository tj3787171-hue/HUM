from __future__ import annotations

import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts.hum_artifact_layers import (
    classify_path,
    inventory,
    write_inventory,
)


class TestArtifactLayerClassification(unittest.TestCase):
    def test_classifies_known_layer_extensions(self) -> None:
        cases = {
            "virtual-setup.yml": "config-yaml",
            "manifest.json": "config-json",
            "tool.jar": "java-archive",
            "bundle.tar": "tar-archive",
            "bundle.tar.gz": "tar-archive",
            "package.deb": "debian-package",
            "system.iso": "iso-image",
            "trace.td.zz": "compressed-layer",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(classify_path(Path(name)), expected)


class TestArtifactLayerInventory(unittest.TestCase):
    def test_inventory_records_artifacts_and_archive_members(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "virtual-setup.yml").write_text("name: hum\n", encoding="utf-8")
            (root / "manifest.json").write_text('{"ok": true}\n', encoding="utf-8")
            payload = root / "payload.txt"
            payload.write_text("hello\n", encoding="utf-8")
            with tarfile.open(root / "bundle.tar", "w") as tf:
                tf.add(payload, arcname="payload.txt")

            report = inventory(root, benchmark_bytes=64)
            kinds = {item["kind"] for item in report["artifacts"]}
            self.assertIn("config-yaml", kinds)
            self.assertIn("config-json", kinds)
            self.assertIn("tar-archive", kinds)
            self.assertTrue(report["archives"])
            self.assertGreaterEqual(report["summary"]["total_size_bytes"], 1)
            self.assertGreaterEqual(report["benchmark"]["sampled_files"], 1)

    def test_write_inventory_creates_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "manifest.json").write_text('{"ok": true}\n', encoding="utf-8")
            json_path = root / "layers.json"
            md_path = root / "layers.md"

            report = write_inventory(root, json_path, md_path, benchmark_bytes=0)

            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["summary"]["artifact_count"], report["summary"]["artifact_count"])
            self.assertIn("# HUM artifact layer inventory", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
