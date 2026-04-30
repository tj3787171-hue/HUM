from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestSiteData(unittest.TestCase):
    def test_final_product_json_is_valid(self) -> None:
        final_product = ROOT / "site" / "data" / "FINAL-PRODUCT"
        for name in ("corps_full.json", "gram.json", "comb.json", "palace.json"):
            with self.subTest(name=name):
                payload = json.loads((final_product / name).read_text(encoding="utf-8"))
                self.assertIsInstance(payload, dict)

    def test_recup_nav_has_single_palace_link(self) -> None:
        recup = (ROOT / "site" / "recup.php").read_text(encoding="utf-8")
        self.assertEqual(recup.count('href="palace.php"'), 1)

    def test_layers_page_has_required_generated_data(self) -> None:
        site = ROOT / "site"
        self.assertIn("artifact-layers.json", (site / "layers.html").read_text(encoding="utf-8"))
        for name in ("artifact-layers.json", "cache-assembly.json"):
            with self.subTest(name=name):
                payload = json.loads((site / "data" / name).read_text(encoding="utf-8"))
                self.assertIsInstance(payload, dict)
        self.assertTrue((site / "data" / "cache-interval-plot.svg").is_file())


if __name__ == "__main__":
    unittest.main()
