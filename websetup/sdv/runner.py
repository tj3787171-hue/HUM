"""SDV apply pipeline: validate pool -> init-fs -> wait for Docker -> optional netns setup -> MACsec RX."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from websetup.sdv import docker_wait, macsec_apply, pool


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest = path or (Path(__file__).resolve().parent / "manifest.json")
    with manifest.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _init_fs(manifest: dict[str, Any], root: Path) -> None:
    """Mount the init-fs virtual RAM scratch filesystem when enabled."""
    initfs = manifest.get("initfs", {})
    if not initfs.get("enabled", False):
        print("[sdv] init-fs skipped (disabled)")
        return

    script_rel = initfs.get("script", "scripts/hum-init-fs-vram.sh")
    script = root / script_rel
    if not script.exists():
        raise FileNotFoundError(f"missing init-fs script: {script}")

    env = dict(
        HUM_VRAM_MOUNTPOINT=str(initfs.get("mountpoint", "/mnt/hum-vram")),
        HUM_VRAM_SIZE=str(initfs.get("size", "64M")),
    )
    subdirs = initfs.get("subdirs")
    if subdirs:
        env["HUM_VRAM_SUBDIRS"] = ",".join(subdirs) if isinstance(subdirs, list) else str(subdirs)

    subprocess.run(
        ["sudo", "bash", str(script), "mount"],
        check=True,
        env={**dict(__import__("os").environ), **env},
    )
    print(f"[sdv] init-fs ready at {env['HUM_VRAM_MOUNTPOINT']}")


def apply(manifest: dict[str, Any], root: Path) -> int:
    ok, message = pool.validate_network(manifest)
    if not ok:
        raise ValueError(message)
    print(f"[sdv] {message}")

    _init_fs(manifest, root)

    docker_wait.ensure_docker(manifest["docker"])
    print("[sdv] docker bridge ready")

    scripts_cfg = manifest.get("scripts", {})
    netns_script = scripts_cfg.get("netns_script", "scripts/hum-dev-netns.sh")
    run_netns = bool(scripts_cfg.get("run_netns_up", True))
    if run_netns:
        script = root / netns_script
        if not script.exists():
            raise FileNotFoundError(f"missing netns script: {script}")
        subprocess.run(["sudo", "bash", str(script), "up"], check=True)
        print("[sdv] netns setup complete")
    else:
        print("[sdv] netns setup skipped by manifest")

    applied = macsec_apply.apply_rx(manifest.get("macsec", {}))
    print(f"[sdv] MACsec RX rules applied: {applied}")
    return 0
