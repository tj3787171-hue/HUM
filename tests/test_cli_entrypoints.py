from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from websetup.sdv import __main__ as sdv_cli


ROOT = Path(__file__).resolve().parents[1]


class TestTelemetryCli(unittest.TestCase):
    def test_no_subcommand_prints_help_without_traceback(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "hum-telemetry-db.py")],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("HUM network telemetry database", result.stdout)
        self.assertNotIn("Traceback", result.stderr)


class TestSdvCli(unittest.TestCase):
    def test_validate_uses_manifest_validator_once(self) -> None:
        with mock.patch.object(sdv_cli, "load_manifest", return_value={"network": {}}), \
            mock.patch.object(sdv_cli.pool, "validate_network", return_value=(True, "ok")) as validate:
            self.assertEqual(sdv_cli.main(["validate"]), 0)
        validate.assert_called_once_with({"network": {}})

    def test_apply_dispatches_once_with_root(self) -> None:
        manifest = {"network": {}, "docker": {}, "macsec": {}}
        with mock.patch.object(sdv_cli, "load_manifest", return_value=manifest), \
            mock.patch.object(sdv_cli, "apply", return_value=0) as apply:
            self.assertEqual(sdv_cli.main(["apply"]), 0)
        apply.assert_called_once_with(manifest, root=Path.cwd())


if __name__ == "__main__":
    unittest.main()
