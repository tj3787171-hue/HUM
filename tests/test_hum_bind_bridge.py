"""Tests for scripts/hum_bind_bridge.py and bind-bridge virtual metadata."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import hum_bind_bridge as bind  # noqa: E402
from scripts.validate_virtual_setup import validate_virtual_setup  # noqa: E402


class TestImageClassification(unittest.TestCase):
    def test_classifies_amd64_iso_and_darwin_kernel_dmg(self) -> None:
        self.assertEqual(
            bind.classify_image(Path("kali-linux-2026.1-installer-amd64.iso")),
            "linux-amd64-iso",
        )
        self.assertEqual(
            bind.classify_image(Path("kernel.dmg")),
            "darwin-kernel-dmg",
        )
        self.assertEqual(
            bind.classify_image(Path("Darwin-kernel.dmg")),
            "darwin-kernel-dmg",
        )
        self.assertEqual(bind.classify_image(Path("live.iso")), "iso-image")


class TestBindTokens(unittest.TestCase):
    def test_token_is_stable_for_same_inputs(self) -> None:
        artifact = bind.ImageArtifact(
            path="/tmp/kali-linux-amd64.iso",
            name="kali-linux-amd64.iso",
            suffix=".iso",
            size_bytes=12,
            role="linux-amd64-iso",
            fingerprint="abc123",
        )
        first = bind.mint_token(
            laptop_nodes=["local-laptop-dev", "penguin"],
            desktop_node="desktop-server",
            desktop_host="192.168.68.53",
            artifacts=[artifact],
        )
        second = bind.mint_token(
            laptop_nodes=["local-laptop-dev", "penguin"],
            desktop_node="desktop-server",
            desktop_host="192.168.68.53",
            artifacts=[artifact],
        )
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("HUM-BIND-"))
        self.assertEqual(len(first), len("HUM-BIND-") + 20)

    def test_plan_discovers_present_images_and_keeps_php_off_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            search = Path(tmp)
            (search / "kali-linux-2026.1-installer-amd64.iso").write_bytes(b"amd64-iso")
            (search / "kernel.dmg").write_bytes(b"darwin-kernel")
            (search / "extra-live.iso").write_bytes(b"other-iso")
            plan = bind.build_plan(
                search_paths=[search],
                desktop_host="192.168.68.53",
                probe=False,
                probe_timeout=0.1,
            )
            roles = {item["role"] for item in plan.artifacts}
            self.assertEqual(
                roles,
                {"linux-amd64-iso", "darwin-kernel-dmg", "iso-image"},
            )
            self.assertIn("snapper-timeline.service", plan.units_allow)
            self.assertIn("snapperd.service", plan.units_allow)
            self.assertIn("fwupd.service", plan.units_allow)
            self.assertIn("phpsessionclean.service", plan.units_deny)
            self.assertIn("apt-listchanges.service", plan.units_deny)
            self.assertEqual(plan.fwupd_tcp_ports, [443, 80])
            self.assertEqual(plan.fwupd_udp_ports, [5353])
            self.assertTrue(plan.token.startswith("HUM-BIND-"))

    def test_emit_units_conflicts_php_and_apt_listchanges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            units_dir = root / "units"
            (root / "scripts").mkdir()
            (root / "scripts" / "hum_bind_bridge.py").write_text("# stub\n", encoding="utf-8")
            plan = bind.build_plan(
                search_paths=[root],
                desktop_host="192.168.68.53",
                probe=False,
                probe_timeout=0.1,
            )
            written = bind.emit_units(plan, units_dir, root)
            self.assertEqual(len(written), 6)
            bridge = (units_dir / "hum-bind-bridge.service").read_text(encoding="utf-8")
            self.assertIn("Conflicts=phpsessionclean.service apt-listchanges.service", bridge)
            after_lines = [
                line for line in bridge.splitlines() if line.startswith("After=")
            ]
            self.assertEqual(len(after_lines), 1)
            self.assertIn("plymouth-quit.service", after_lines[0])
            self.assertNotIn("plymouth-quit-wait.service", after_lines[0])
            self.assertIn("Wants=snapper-timeline.service", bridge)
            self.assertIn("fwupd.service", bridge)
            fwupd = (
                units_dir / "fwupd.service.d" / "hum-bind-bridge.conf"
            ).read_text(encoding="utf-8")
            self.assertIn("TCP 443,80", fwupd)
            self.assertIn("UDP 5353", fwupd)
            self.assertIn("Conflicts=phpsessionclean.service", fwupd)
            wait = (
                units_dir / "plymouth-quit-wait.service.d" / "hum-bind-bridge.conf"
            ).read_text(encoding="utf-8")
            self.assertIn("TimeoutStartSec=20s", wait)
            self.assertIn("Conflicts=phpsessionclean.service apt-listchanges.service", wait)
            self.assertIn("Before=hum-bind-bridge.service", wait)

    def test_mask_mode_emits_plymouth_mask_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            units_dir = root / "units"
            (root / "scripts").mkdir()
            (root / "scripts" / "hum_bind_bridge.py").write_text("# stub\n", encoding="utf-8")
            plan = bind.build_plan(
                search_paths=[root],
                desktop_host="192.168.68.53",
                probe=False,
                probe_timeout=0.1,
                plymouth_mode="mask",
            )
            written = bind.emit_units(plan, units_dir, root)
            self.assertEqual(plan.plymouth_mode, "mask")
            mask_path = units_dir / "MASK-plymouth.cmds"
            self.assertIn(str(mask_path), written)
            text = mask_path.read_text(encoding="utf-8")
            self.assertIn("systemctl mask plymouth-quit-wait.service plymouth-start.service", text)

    def test_cli_plan_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            images = home / "images"
            images.mkdir()
            (images / "kernel.dmg").write_bytes(b"k")
            output = home / "plan.json"
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = bind.main(
                    [
                        "plan",
                        "--repo-root",
                        str(home),
                        "--search",
                        str(images),
                        "--output",
                        str(output),
                        "--no-probe",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["desktop_host"], "192.168.68.53")
            self.assertEqual(payload["artifacts"][0]["role"], "darwin-kernel-dmg")


class TestBindBridgeVirtualMetadata(unittest.TestCase):
    def test_matrix_models_laptop_desktop_bind_bridge(self) -> None:
        matrix_path = ROOT / "websetup" / "virtual" / "network-matrix.json"
        payload = json.loads(matrix_path.read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in payload["nodes"]}
        self.assertIn("desktop-server", nodes)
        self.assertEqual(nodes["desktop-server"]["metadata"]["alias_of"], "HUM")
        self.assertIn("snapper-timeline.service", nodes["desktop-server"]["metadata"]["units_allow"])
        self.assertIn("phpsessionclean.service", nodes["desktop-server"]["metadata"]["units_deny"])

        edges = {(edge["from"], edge["to"], edge["type"]) for edge in payload["edges"]}
        self.assertIn(("local-laptop-dev", "desktop-server", "bind_bridge"), edges)
        self.assertIn(("penguin", "desktop-server", "bind_bridge"), edges)
        self.assertIn(("snapper-timeline", "desktop-server", "snapshot_path"), edges)
        self.assertIn(("fwupd", "desktop-server", "firmware_tcp_udp"), edges)
        self.assertIn(("phpsessionclean", "apt-listchanges", "isolated"), edges)
        self.assertIn(("plymouth-quit-wait", "desktop-server", "boot_gate"), edges)
        self.assertIn(("plymouth-quit-wait", "apt-listchanges", "isolated"), edges)
        self.assertEqual(
            nodes["apt-listchanges"]["metadata"]["runtime"],
            "perl",
        )
        self.assertEqual(
            nodes["plymouth-quit-wait"]["metadata"]["hum_timeout_sec"],
            20,
        )

    def test_bindings_include_iso_dmg_and_snapper_fwupd(self) -> None:
        bindings = json.loads(
            (ROOT / "websetup" / "virtual" / "bindings.json").read_text(encoding="utf-8")
        )
        ids = {entry["id"] for entry in bindings["bindings"]}
        self.assertIn("iso-dmg-to-bind-bridge-tokens", ids)
        self.assertIn("snapper-fwupd-units-to-bind-bridge", ids)

    def test_virtual_setup_validator_still_ok(self) -> None:
        ok, errors = validate_virtual_setup(
            inventory_path=ROOT / "websetup" / "virtual" / "inventory.csv",
            network_matrix_path=ROOT / "websetup" / "virtual" / "network-matrix.json",
            manifest_path=ROOT / "websetup" / "sdv" / "manifest.json",
        )
        self.assertTrue(ok, msg="\n".join(errors))


if __name__ == "__main__":
    unittest.main()
