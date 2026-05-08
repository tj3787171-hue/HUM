from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestBootstrapSecurity(unittest.TestCase):
    def test_firebase_hosting_security_headers_are_configured(self) -> None:
        payload = json.loads((ROOT / "firebase.json").read_text(encoding="utf-8"))
        hosting = payload["hosting"]
        self.assertEqual(hosting["public"], "site")
        flattened = {
            header["key"]: header["value"]
            for block in hosting["headers"]
            for header in block["headers"]
        }
        self.assertIn("Content-Security-Policy", flattened)
        self.assertIn("frame-ancestors 'none'", flattened["Content-Security-Policy"])
        self.assertEqual(flattened["X-Content-Type-Options"], "nosniff")
        self.assertIn("geolocation=()", flattened["Permissions-Policy"])

    def test_package_scripts_reference_semgrep_bootstrap(self) -> None:
        payload = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        scripts = payload["scripts"]
        self.assertIn("setup-semgrep-plugin.sh", scripts["semgrep:check"])
        self.assertIn("bootstrap-kali-iso", scripts["bootstrap-kali-iso:semgrep"])

    def test_btrfs_refuse_wipe_is_nonzero_and_explicit(self) -> None:
        result = subprocess.run(
            ["bash", "scripts/btrfs-journal-safety.sh", "refuse-wipe"],
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing destructive Btrfs", result.stderr)

    def test_semgrep_rules_include_destructive_btrfs_gate(self) -> None:
        rules = (ROOT / ".semgrep.yml").read_text(encoding="utf-8")
        self.assertIn("hum-review-destructive-btrfs-or-wipefs", rules)
        self.assertIn("btrfs", rules.lower())
        self.assertIn("wipefs", rules)


if __name__ == "__main__":
    unittest.main()
