"""Wait for docker0 (or configured bridge) before virtual binding steps."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, Mapping


def _bridge_exists(name: str) -> bool:
    return (Path("/sys/class/net") / name).exists()


def ensure_docker(settings: Mapping[str, Any]) -> None:
    bridge_name = str(
        settings.get("bridge_name")
        or settings.get("required_interface")
        or "docker0"
    ).strip()
    timeout_sec = int(settings.get("wait_timeout_sec", 30))
    poll_interval_sec = float(settings.get("poll_interval_sec", 1.0))
    start_command = str(settings.get("start_command", "")).strip()
    tried_start = False

    deadline = time.time() + max(timeout_sec, 1)
    while time.time() < deadline:
        if _bridge_exists(bridge_name):
            return

        if start_command and not tried_start:
            subprocess.run(
                ["bash", "-lc", start_command],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            tried_start = True

        time.sleep(max(poll_interval_sec, 0.1))

    raise RuntimeError(
        f"Bridge {bridge_name!r} not found within {timeout_sec}s. "
        f"Start Docker (or configure {bridge_name}) and retry."
    )
