"""SDV apply pipeline: validate pool -> wait for Docker -> optional netns setup -> MACsec RX."""

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


def apply(manifest: dict[str, Any], root: Path) -> int:
    ok, message = pool.validate_network(manifest)
    if not ok:
        raise ValueError(message)
    print(f"[sdv] {message}")
    pool.validate_network(manifest["network"])
    print("[sdv] manifest network block OK")

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
    applied = macsec_apply.apply(manifest["macsec"])
    print(f"[sdv] MACsec RX rules applied: {applied}")
    return 0
