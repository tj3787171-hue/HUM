#!/usr/bin/env python3
"""Collect systemd service tree and unit states; emit JSON for the HUM pipeline."""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

KNOWN_UNITS = [
    "display-manager.service", "systemd-update-utmp-runlevel.service",
    "avahi-daemon.service", "dbus.service", "e2scrub_reap.service",
    "ModemManager.service", "networking.service", "rtkit-daemon.service",
    "ssh.service", "systemd-ask-password-wall.path", "systemd-logind.service",
    "systemd-user-sessions.service", "wpa_supplicant.service",
    "tmp.mount", "avahi-daemon.socket", "dbus.socket", "ssh.socket",
    "systemd-initctl.socket", "systemd-journald-audit.socket",
    "systemd-journald-dev-log.socket", "systemd-journald.socket",
    "systemd-udevd-control.socket", "systemd-udevd-kernel.socket",
    "dev-hugepages.mount", "dev-mqueue.mount", "kmod-static-nodes.service",
    "nftables.service", "proc-sys-fs-binfmt_misc.automount",
    "sys-fs-fuse-connections.mount", "sys-kernel-config.mount",
    "sys-kernel-debug.mount", "sys-kernel-tracing.mount",
    "systemd-ask-password-console.path", "systemd-binfmt.service",
    "systemd-firstboot.service", "systemd-journal-flush.service",
    "systemd-journald.service", "systemd-machine-id-commit.service",
    "systemd-modules-load.service", "systemd-network-generator.service",
    "systemd-pcrphase-sysinit.service", "systemd-pcrphase.service",
    "systemd-pstore.service", "systemd-random-seed.service",
    "systemd-repart.service", "systemd-sysctl.service",
    "systemd-sysext.service", "systemd-sysusers.service",
    "systemd-timesyncd.service", "systemd-tmpfiles-setup-dev.service",
    "systemd-tmpfiles-setup.service", "systemd-udev-trigger.service",
    "systemd-udevd.service", "systemd-update-utmp.service",
    "systemd-remount-fs.service", "usr-share-fonts-chromeos.mount",
    "apt-daily-upgrade.timer", "apt-daily.timer", "dpkg-db-backup.timer",
    "e2scrub_all.timer", "fstrim.timer", "lynis.timer", "man-db.timer",
    "systemd-tmpfiles-clean.timer", "console-getty.service",
    "getty-static.service", "getty@tty1.service",
    "NetworkManager.service", "systemd-resolved.service",
    "systemd-networkd.service", "docker.service",
]

TARGETS = [
    "default.target", "multi-user.target", "basic.target",
    "paths.target", "slices.target", "sockets.target",
    "sysinit.target", "timers.target", "getty.target",
    "local-fs.target", "swap.target", "cryptsetup.target",
    "integritysetup.target", "veritysetup.target",
    "remote-cryptsetup.target", "remote-fs.target",
    "remote-veritysetup.target",
]


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def get_unit_state(unit: str) -> dict:
    state = _run(["systemctl", "is-active", unit]) or "unknown"
    enabled = _run(["systemctl", "is-enabled", unit]) or "unknown"
    return {"unit": unit, "active": state, "enabled": enabled}


def get_default_target_tree() -> str:
    return _run(["systemctl", "list-dependencies", "default.target", "--no-pager"])


def collect_all() -> dict:
    units = []
    for u in sorted(set(KNOWN_UNITS)):
        units.append(get_unit_state(u))

    targets = []
    for t in TARGETS:
        targets.append(get_unit_state(t))

    active_count = sum(1 for u in units if u["active"] == "active")
    inactive_count = sum(1 for u in units if u["active"] == "inactive")
    failed_count = sum(1 for u in units if u["active"] == "failed")

    tree_raw = get_default_target_tree()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "default_target": _run(["systemctl", "get-default"]) or "unknown",
        "units": units,
        "targets": targets,
        "tree_raw": tree_raw,
        "summary": {
            "total_tracked": len(units),
            "active": active_count,
            "inactive": inactive_count,
            "failed": failed_count,
        },
    }


def main():
    data = collect_all()
    out = HERE / "systemd_tree.json"
    out.write_text(json.dumps(data, indent=2))
    print(f"Wrote {out}")
    s = data["summary"]
    print(f"  Units: {s['total_tracked']} tracked, {s['active']} active, "
          f"{s['inactive']} inactive, {s['failed']} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
