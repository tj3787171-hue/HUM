# AGENTS.md

## Cursor Cloud specific instructions

### Overview

HUM is a lightweight utility repository (no package manager, no build step, no lockfiles). It contains:

- **Dev Container config** (`.devcontainer/`) — Ubuntu 24.04-based container with LAN/network tools.
- **`scripts/hum-dev-netns.sh`** — Bash script for Linux network namespace setup (requires `iproute2` and root).
- **`scripts/deepseek_db_link.py`** — Python 3 CLI that indexes DeepSeek backup exports into SQLite. Uses only stdlib modules (zero pip dependencies).

### Running scripts

| Script | Command | Notes |
|---|---|---|
| Post-create | `bash .devcontainer/post-create.sh` | Prints network summary |
| Network namespace status | `bash scripts/hum-dev-netns.sh status` | Requires `iproute2` |
| Network namespace up/down | `sudo bash scripts/hum-dev-netns.sh up` | Requires root + `iproute2` |
| DeepSeek importer | `python3 scripts/deepseek_db_link.py --source <dir> --database <db>` | Stdlib-only Python 3 |
| Snap bypass | `bash scripts/hum-snap-bypass.sh <subcommand>` | Requires `squashfs-tools`, `squashfuse`, `xz-utils`, `file`, `fuse3` |

### Linting

No project-level lint config exists. Use these tools for quality checks:

- **Bash**: `shellcheck scripts/hum-dev-netns.sh .devcontainer/post-create.sh`
- **Python**: `pyright scripts/deepseek_db_link.py` (install via `pip install pyright`)

### Docker / Dev Container build

Building the `.devcontainer/Dockerfile` requires pulling `mcr.microsoft.com/devcontainers/base:ubuntu-24.04` from Microsoft Container Registry. This will fail in environments with restricted egress (e.g., Cursor Cloud VMs). The Dockerfile itself is valid and builds successfully on unrestricted networks.

- Docker must be started manually in the cloud VM: `sudo dockerd &` (wait ~3 seconds before running Docker commands).
- Docker Hub is also blocked for image pulls in cloud VMs.
- The host Ubuntu 24.04 environment matches the Dockerfile's base image, so networking tools can be installed and tested directly on the host as a substitute.

### Snap bypass script

`scripts/hum-snap-bypass.sh` lets you extract, mount, inspect, and run snap packages (squashfs + xz) without snapd/systemd/cgroups. Run `bash scripts/hum-snap-bypass.sh deps` to check required host tooling. See `README.md` for full usage.

### Key caveats

- There are no automated tests in this repository.
- There is no build step — scripts are run directly.
- The `hum-dev-netns.sh up/down` subcommands require root privileges and will modify host network namespaces.
- System dependency `iproute2` must be installed for the network namespace script to work (`sudo apt-get install -y iproute2`).
- The Cloud VM kernel does not support the `dummy` network interface type; `hum-dev-netns.sh up` will print a warning but still works correctly for veth peer chain setup.
- `pyright` installs to `~/.local/bin` which may not be on `PATH` by default. Use `export PATH="$HOME/.local/bin:$PATH"` before running it, or invoke directly as `~/.local/bin/pyright`.
