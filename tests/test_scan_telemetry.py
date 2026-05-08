from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestScanTelemetry(unittest.TestCase):
    def run_node(self, script: str) -> object:
        result = subprocess.run(
            ["node", "-e", script],
            check=True,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return json.loads(result.stdout)

    def test_chrome_extension_url_flags_target_extension(self) -> None:
        payload = self.run_node(
            """
            const { scanTelemetry } = require("./scripts/scanTelemetry.js");
            const flags = scanTelemetry(
              "chrome-extension://bpmcpldpdmajfigpchkicefoigmkfalc/",
              { log: () => {} }
            );
            console.log(JSON.stringify(flags));
            """
        )

        self.assertIn("CHROME_EXTENSION", payload)
        self.assertIn("TARGET_EXTENSION", payload)

    def test_extracts_unique_chrome_extension_ids(self) -> None:
        payload = self.run_node(
            """
            const { extractChromeExtensionIds } = require("./scripts/scanTelemetry.js");
            const ids = extractChromeExtensionIds(
              "chrome-extension://bpmcpldpdmajfigpchkicefoigmkfalc/ " +
              "chrome-extension://bpmcpldpdmajfigpchkicefoigmkfalc/options.html"
            );
            console.log(JSON.stringify(ids));
            """
        )

        self.assertEqual(payload, ["bpmcpldpdmajfigpchkicefoigmkfalc"])


if __name__ == "__main__":
    unittest.main()
