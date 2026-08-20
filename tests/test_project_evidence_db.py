from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "project_evidence_db.py"


class TestProjectEvidenceApiPhoneTracking(unittest.TestCase):
    def run_cli(self, db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--database", str(db_path), *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def test_api_connection_can_be_registered_and_listed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "project.db"

            result = self.run_cli(
                db_path,
                "upsert-api-connection",
                "--connection-key",
                "api5",
                "--api-name",
                "API5",
                "--status",
                "initiated",
                "--endpoint",
                "https://api5.local/phone-sync",
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("API connection upserted", result.stdout)

            listed = self.run_cli(db_path, "list-api-connections")
            self.assertEqual(listed.returncode, 0, msg=listed.stderr)
            payload = json.loads(listed.stdout)
            self.assertEqual(
                payload,
                [
                    {
                        "connection_key": "api5",
                        "api_name": "API5",
                        "status": "initiated",
                        "endpoint": "https://api5.local/phone-sync",
                        "initiated_at": payload[0]["initiated_at"],
                        "last_seen": payload[0]["last_seen"],
                        "metadata": {},
                    }
                ],
            )

    def test_phone_flow_records_api_connection_and_device_direction(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "project.db"

            result = self.run_cli(
                db_path,
                "record-phone-flow",
                "--connection-key",
                "api5",
                "--api-name",
                "API5",
                "--status",
                "initiated",
                "--device-mac",
                "AA-BB-CC-DD-EE-FF",
                "--device-label",
                "field-phone",
                "--direction",
                "from-phone",
                "--payload-kind",
                "telemetry",
                "--byte-count",
                "512",
                "--source-ref",
                "api5-session-001",
                "--metadata-json",
                '{"transport":"cell"}',
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("Phone flow recorded", result.stdout)

            flows = self.run_cli(db_path, "list-phone-flows")
            self.assertEqual(flows.returncode, 0, msg=flows.stderr)
            payload = json.loads(flows.stdout)
            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0]["connection_key"], "api5")
            self.assertEqual(payload[0]["api_name"], "API5")
            self.assertEqual(payload[0]["device_mac"], "aa:bb:cc:dd:ee:ff")
            self.assertEqual(payload[0]["device_label"], "field-phone")
            self.assertEqual(payload[0]["direction"], "from-phone")
            self.assertEqual(payload[0]["payload_kind"], "telemetry")
            self.assertEqual(payload[0]["byte_count"], 512)
            self.assertEqual(payload[0]["source_ref"], "api5-session-001")
            self.assertEqual(payload[0]["metadata"], {"transport": "cell"})

            summary = self.run_cli(db_path, "export-summary")
            self.assertEqual(summary.returncode, 0, msg=summary.stderr)
            counts = json.loads(summary.stdout)["counts"]
            self.assertEqual(counts["api_connections"], 1)
            self.assertEqual(counts["phone_data_flows"], 1)

    def test_phone_flow_preserves_existing_api_connection_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "project.db"
            registered = self.run_cli(
                db_path,
                "upsert-api-connection",
                "--connection-key",
                "api5",
                "--api-name",
                "API5",
                "--status",
                "active",
                "--metadata-json",
                '{"owner":"lab"}',
            )
            self.assertEqual(registered.returncode, 0, msg=registered.stderr)

            recorded = self.run_cli(
                db_path,
                "record-phone-flow",
                "--connection-key",
                "api5",
                "--device-mac",
                "AA:BB:CC:DD:EE:FF",
                "--direction",
                "to-phone",
                "--payload-kind",
                "control",
            )
            self.assertEqual(recorded.returncode, 0, msg=recorded.stderr)

            listed = self.run_cli(db_path, "list-api-connections")
            self.assertEqual(listed.returncode, 0, msg=listed.stderr)
            connection = json.loads(listed.stdout)[0]
            self.assertEqual(connection["api_name"], "API5")
            self.assertEqual(connection["status"], "active")
            self.assertEqual(connection["metadata"], {"owner": "lab"})


if __name__ == "__main__":
    unittest.main()
