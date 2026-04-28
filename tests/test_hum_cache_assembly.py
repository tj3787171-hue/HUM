from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.hum_cache_assembly import (
    build_interval_plot,
    classify_piece,
    interval_points,
    scan_cache,
    write_json,
    write_markdown,
    write_svg,
)


class TestCacheAssembly(unittest.TestCase):
    def test_classifies_cache_piece_series(self) -> None:
        cases = {
            "src/Sources.gz": "source-index",
            "pkg/demo.deb": "package-deb",
            "cache/pkgcache.bin": "cache-piece",
            "img/rootfs.img": "image-layer",
            "lib/libclang-cpp.so": "libclang-family",
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(classify_piece(Path(path)), expected)

    def test_interval_points_apply_exponent_formula(self) -> None:
        pieces = [
            {"path": "a", "category": "cache-piece", "size_bytes": 3},
            {"path": "b", "category": "cache-piece", "size_bytes": 2},
            {"path": "c", "category": "cache-piece", "size_bytes": 1},
            {"path": "d", "category": "cache-piece", "size_bytes": 0},
        ]
        points = interval_points(pieces, 2.0, "test")
        self.assertEqual(points[0]["n"], 1)
        self.assertEqual(points[0]["y"], 1.0)
        self.assertEqual(points[0]["id"], "test-0001")
        self.assertEqual(points[-1]["n"], 4)
        self.assertEqual(points[-1]["y"], 16.0)

    def test_write_cache_assembly_outputs_reports(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "src").mkdir()
            (root / "pkg").mkdir()
            (root / "cache").mkdir()
            (root / "src" / "Sources.gz").write_bytes(b"source")
            (root / "pkg" / "demo.deb").write_bytes(b"deb")
            (root / "cache" / "pkgcache.bin").write_bytes(b"cache")

            json_path = root / "assembly.json"
            md_path = root / "assembly.md"
            svg_path = root / "assembly.svg"
            report = scan_cache([root], max_files=10, hash_bytes=64)
            build_interval_plot(report, 1.5, "hum-test")
            write_json(json_path, report)
            write_markdown(md_path, report)
            write_svg(svg_path, report)

            self.assertEqual(report["piece_count"], 3)
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            self.assertTrue(svg_path.exists())
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["interval_plot"]["formula"], "y = n^1.5")
            self.assertEqual(loaded["interval_plot"]["prefix"], "hum-test")
            self.assertIn("<svg", svg_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
