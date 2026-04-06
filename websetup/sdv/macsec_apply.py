"""Apply MACsec RX SAs from manifest when enabled."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Mapping


def _read_key_hex(path: str) -> str:
    raw = Path(path).expanduser().read_text(encoding="utf-8").strip()
    key = raw.replace(" ", "").replace(":", "")
    if len(key) not in {32, 64} or any(c not in "0123456789abcdefABCDEF" for c in key):
        raise ValueError(f"MACsec key in {path} must be 32 or 64 hex chars")
    return key.lower()


def apply_rx(material: Mapping[str, Any]) -> int:
    applied = 0
    links = material.get("links", [])
    for link in links:
        if not isinstance(link, Mapping):
            continue
        macsec_dev = str(link.get("macsec_dev", "")).strip()
        rx = link.get("rx", {})
        if not macsec_dev or not isinstance(rx, Mapping):
            continue
        if not bool(rx.get("enabled", False)):
            continue

        sci = rx.get("sci_hex") or rx.get("sci")
        if sci is None:
            raise ValueError(f"{macsec_dev}: missing sci_hex")
        sci_u64 = int(str(sci), 0)
        sa_idx = int(rx.get("sa_index", 0))
        key_id = int(rx["key_id"])
        key_file = str(rx.get("key_hex_file", "")).strip()
        if not key_file:
            raise ValueError(f"{macsec_dev}: rx.enabled is true but key_hex_file is empty")
        key_hex = _read_key_hex(key_file)

        cmd = [
            "sudo",
            "ip",
            "macsec",
            "add",
            macsec_dev,
            "rx",
            "sci",
            str(sci_u64),
            "sa",
            str(sa_idx),
            "on",
            "key",
            str(key_id),
            key_hex,
        ]
        subprocess.run(cmd, check=True)
        applied += 1
    return applied
