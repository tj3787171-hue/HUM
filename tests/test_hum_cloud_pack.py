"""Tests for scripts/hum_cloud_pack.py."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import hum_cloud_pack as cloud  # noqa: E402


def _write_source_tree(source: Path) -> None:
    (source / "docs").mkdir(parents=True, exist_ok=True)
    (source / "hello.txt").write_text("hello cloud storage\n", encoding="utf-8")
    (source / "docs" / "blob.bin").write_bytes(b"\x00\x01\x02\x03" * 800)


class TestHumCloudPack(unittest.TestCase):
    def test_pack_and_restore_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            cloud_dir = root / "cloud"
            restored = root / "restored"
            source.mkdir()
            _write_source_tree(source)

            result = cloud.pack_directory(source, cloud_dir, "s3cret-pass")

            self.assertEqual(result.manifest["chunk_size"], cloud.DEFAULT_CHUNK_SIZE)
            self.assertEqual(result.manifest["minimum_chunk_size"], cloud.MIN_CHUNK_SIZE)
            self.assertTrue((cloud_dir / "index.json").is_file())
            self.assertTrue((cloud_dir / "online-index.html").is_file())
            self.assertTrue((cloud_dir / "chunks").is_dir())
            self.assertGreater(result.manifest["summary"]["chunk_count"], 0)

            cloud.restore_directory(cloud_dir, restored, "s3cret-pass")

            for src_file in source.rglob("*"):
                if not src_file.is_file():
                    continue
                rel = src_file.relative_to(source)
                restored_file = restored / rel
                self.assertTrue(restored_file.is_file())
                self.assertEqual(src_file.read_bytes(), restored_file.read_bytes())

    def test_chunk_size_minimum_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            cloud_dir = root / "cloud"
            source.mkdir()
            (source / "one.txt").write_text("x" * 2048, encoding="utf-8")

            with self.assertRaises(ValueError):
                cloud.pack_directory(source, cloud_dir, "pw", chunk_size=1023)

    def test_expected_aggregate_checksum_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            cloud_dir = root / "cloud"
            source.mkdir()
            _write_source_tree(source)

            first = cloud.pack_directory(source, cloud_dir, "pw")
            expected = first.manifest["summary"]["aggregate_sha256"]

            second = cloud.pack_directory(
                source,
                cloud_dir,
                "pw",
                expected_aggregate_sha256=expected,
                force=True,
            )
            self.assertEqual(
                second.manifest["summary"]["aggregate_sha256"],
                expected,
            )

            with self.assertRaises(ValueError):
                cloud.pack_directory(
                    source,
                    cloud_dir,
                    "pw",
                    expected_aggregate_sha256=(
                        "c058fd133d909759028353fea46d228c2fd8bcf945cf27680bb751fe1066fc3e"
                    ),
                    force=True,
                )


if __name__ == "__main__":
    unittest.main()
