from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hum-snap-server.sh"


class TestHumSnapServerAttach(unittest.TestCase):
    def run_attach(self, args: list[str], *, cgroup_root: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        merged_env = os.environ.copy()
        merged_env["HUM_CGROUP_ROOT"] = str(cgroup_root)
        if env:
            merged_env.update(env)
        return subprocess.run(
            ["bash", str(SCRIPT), "attach", *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=merged_env,
        )

    def test_attach_writes_explicit_pid_to_snap_cgroup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cgroup_root = Path(tmp)
            snap_group = cgroup_root / "snap.hum"
            snap_group.mkdir()
            (snap_group / "cgroup.procs").write_text("")

            sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            try:
                result = self.run_attach(["--pid", str(sleeper.pid)], cgroup_root=cgroup_root)
            finally:
                sleeper.terminate()
                sleeper.wait(timeout=5)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"attached pid: {sleeper.pid}", result.stdout)
            self.assertEqual((snap_group / "cgroup.procs").read_text().strip(), str(sleeper.pid))

    def test_attach_resolves_process_name_with_pgrep(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            cgroup_root = temp_root / "cgroup"
            snap_group = cgroup_root / "snap.hum"
            bin_dir = temp_root / "bin"
            snap_group.mkdir(parents=True)
            bin_dir.mkdir()
            (snap_group / "cgroup.procs").write_text("")
            pgrep = bin_dir / "pgrep"
            pgrep.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env bash
                    [[ "$1" == "-x" ]] || exit 2
                    [[ "$2" == "copilot-desktop" ]] || exit 1
                    echo "{os.getpid()}"
                    """
                )
            )
            pgrep.chmod(0o755)

            result = self.run_attach(
                ["copilot-desktop"],
                cgroup_root=cgroup_root,
                env={"PATH": f"{bin_dir}:{os.environ['PATH']}"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"attached pid: {os.getpid()}", result.stdout)
            self.assertEqual((snap_group / "cgroup.procs").read_text().strip(), str(os.getpid()))


if __name__ == "__main__":
    unittest.main()
