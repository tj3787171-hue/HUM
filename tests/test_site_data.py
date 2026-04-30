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


if __name__ == "__main__":
    unittest.main()
