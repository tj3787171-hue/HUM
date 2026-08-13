"""Tests for scripts/fix-cursor-cli-json.py."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fix_cursor_cli_json as fix  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class TestFixCursorCliJson(unittest.TestCase):
    def test_status_detects_display_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            _write_json(
                home / ".cursor" / "cli.json",
                {
                    "version": 1,
                    "editor": {"vimMode": False},
                    "permissions": {"allow": [], "deny": []},
                    "display": {"showLineNumbers": True},
                },
            )
            result = fix.repair_cursor_cli_config(home, dry_run=True)
            self.assertTrue(result.needs_repair)
            self.assertEqual(result.unrecognized_keys, ["display"])
            self.assertFalse(result.project_written)
            self.assertTrue((home / ".cursor" / "cli.json").is_file())
            payload = json.loads((home / ".cursor" / "cli.json").read_text(encoding="utf-8"))
            self.assertIn("display", payload)

    def test_migrates_display_into_global_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            _write_json(
                home / ".cursor" / "cli.json",
                {
                    "version": 1,
                    "editor": {"vimMode": True},
                    "permissions": {"allow": ["Shell(ls)"], "deny": []},
                    "display": {
                        "showLineNumbers": True,
                        "showThinkingBlocks": False,
                    },
                    "approvalMode": "allowlist",
                },
            )
            _write_json(
                home / ".cursor" / "cli-config.json",
                {
                    "version": 1,
                    "editor": {"vimMode": False},
                    "permissions": {"allow": [], "deny": []},
                    "display": {"showStatusIndicators": True},
                },
            )

            result = fix.repair_cursor_cli_config(home)
            self.assertTrue(result.needs_repair)
            self.assertTrue(result.project_written)
            self.assertTrue(result.global_written)
            self.assertEqual(sorted(result.migrated_keys), ["approvalMode", "display"])

            project = json.loads((home / ".cursor" / "cli.json").read_text(encoding="utf-8"))
            self.assertEqual(
                project,
                {
                    "version": 1,
                    "editor": {"vimMode": True},
                    "permissions": {"allow": ["Shell(ls)"], "deny": []},
                },
            )
            self.assertNotIn("display", project)
            self.assertNotIn("approvalMode", project)

            glob = json.loads((home / ".cursor" / "cli-config.json").read_text(encoding="utf-8"))
            self.assertEqual(glob["display"]["showLineNumbers"], True)
            self.assertEqual(glob["display"]["showThinkingBlocks"], False)
            self.assertEqual(glob["display"]["showStatusIndicators"], True)
            self.assertEqual(glob["approvalMode"], "allowlist")
            self.assertGreaterEqual(len(result.backups), 2)

    def test_creates_global_config_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            _write_json(
                home / ".cursor" / "cli.json",
                {"display": {"showLineNumbers": True}},
            )
            result = fix.repair_cursor_cli_config(home)
            self.assertTrue(result.global_written)
            glob = json.loads((home / ".cursor" / "cli-config.json").read_text(encoding="utf-8"))
            self.assertEqual(glob["version"], 1)
            self.assertEqual(glob["editor"]["vimMode"], False)
            self.assertEqual(glob["permissions"]["allow"], [])
            self.assertEqual(glob["display"]["showLineNumbers"], True)

    def test_valid_project_config_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            original = {
                "version": 1,
                "editor": {"vimMode": False},
                "permissions": {"allow": [], "deny": []},
            }
            path = home / ".cursor" / "cli.json"
            _write_json(path, original)
            result = fix.repair_cursor_cli_config(home)
            self.assertFalse(result.needs_repair)
            self.assertFalse(result.project_written)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                original,
            )

    def test_missing_project_config_is_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = fix.repair_cursor_cli_config(Path(tmp))
            self.assertFalse(result.needs_repair)
            self.assertIsNone(result.error)
            self.assertIn("nothing to repair", result.message)

    def test_invalid_json_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            path = home / ".cursor" / "cli.json"
            path.parent.mkdir(parents=True)
            path.write_text("{not-json", encoding="utf-8")
            result = fix.repair_cursor_cli_config(home)
            self.assertIsNotNone(result.error)
            self.assertIn("invalid JSON", result.error or "")
            self.assertEqual(path.read_text(encoding="utf-8"), "{not-json")

    def test_cli_status_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            _write_json(
                home / ".cursor" / "cli.json",
                {"display": {"showLineNumbers": True}},
            )
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = fix.main(
                    ["--home", str(home), "--status", "--json"],
                )
            self.assertEqual(code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertTrue(payload["needs_repair"])
            self.assertEqual(payload["unrecognized_keys"], ["display"])


if __name__ == "__main__":
    unittest.main()
