# HUM

LAN-ready development container configuration for online/local development.

## What's included

- `.devcontainer/Dockerfile` based on Ubuntu 24.04 devcontainer image
- Useful LAN/network tools installed:
  - `iproute2`, `net-tools`
  - `iputils-ping`, `traceroute`
  - `dnsutils`
- `.devcontainer/devcontainer.json` with:
  - host-network runtime flag (`--network=host`) for Linux LAN access
  - `host.docker.internal` mapping via `host-gateway`
  - common forwarded ports (`3000`, `5173`, `8000`, `8080`)
- `.devcontainer/post-create.sh` to print network info when container is created

## Use it

1. Open this repository in VS Code.
2. Install **Dev Containers** extension if needed.
3. Run **Dev Containers: Reopen in Container**.
4. After build, the terminal will show container network info.

## LAN notes

- This setup is optimized for Linux with Docker engine networking.
- `--network=host` allows services in the container to be reachable on the host/LAN stack.
- On non-Linux hosts, host-network support can be limited by Docker Desktop behavior.

## Penguin terminal dev naming (Proxy + Docker + Dummy)

If you want the laptop Penguin terminal to use stable developer names that parallel
the original proxy/docker/dummy model, use:

```bash
sudo bash scripts/hum-dev-netns.sh up
```

Requirement: `ip` command from `iproute2` must be installed in the Penguin terminal.

This creates/maintains:

- proxy namespace: `hum-proxy-ns`
- proxy veth pair: `hum-proxy-host0` (root) <-> `hum-proxy-ns0` (inside netns)
- dummy interface: `hum-dummy0`
- a status view that also reports `docker0` if present

Useful commands:

```bash
sudo bash scripts/hum-dev-netns.sh status
sudo bash scripts/hum-dev-netns.sh down
```

All names can be overridden through `HUM_*` environment variables shown by:

```bash
bash scripts/hum-dev-netns.sh --help
```

## DeepSeek backup -> SQLite database linking

If your DeepSeek standalone backup lives on an attached SSD, you can index it
into a local SQLite database so conversations and files are queryable.

### 1) Mount the SSD (Linux host)

```bash
lsblk -f
sudo mkdir -p /mnt/deepseek-ssd
sudo mount /dev/<your-device-partition> /mnt/deepseek-ssd
```

Example device names are `nvme1n1p1`, `sdb1`, etc. Use the output from
`lsblk -f` to choose the right one.

### 2) Build the DeepSeek backup database

From this repository root:

```bash
python3 scripts/deepseek_db_link.py \
  --source /mnt/deepseek-ssd \
  --database data/deepseek_backup.db
```

Optional: include file hashes (slower for large backups):

```bash
python3 scripts/deepseek_db_link.py \
  --source /mnt/deepseek-ssd \
  --database data/deepseek_backup.db \
  --compute-sha256
```

The importer will:

- index every file path/size/mtime in `source_files`
- parse chat-like `.json` and `.jsonl` exports into:
  - `conversations`
  - `messages`

### 3) Quick database checks

```bash
sqlite3 data/deepseek_backup.db "SELECT COUNT(*) FROM source_files;"
sqlite3 data/deepseek_backup.db "SELECT COUNT(*) FROM conversations;"
sqlite3 data/deepseek_backup.db "SELECT COUNT(*) FROM messages;"
```

## Snap package bypass (no snapd / no cgroups)

Snap packages are squashfs images compressed with xz.  Normally `snapd` manages
them via systemd, cgroup scopes, and AppArmor profiles.  In environments where
those subsystems are missing (containers, Penguin terminals, minimal VMs) you
can use the bypass script instead:

```bash
bash scripts/hum-snap-bypass.sh deps          # check required tools
bash scripts/hum-snap-bypass.sh info  foo.snap # squashfs metadata + snap.yaml
bash scripts/hum-snap-bypass.sh extract foo.snap [dest]
bash scripts/hum-snap-bypass.sh mount   foo.snap [mountpoint]
bash scripts/hum-snap-bypass.sh unmount <mountpoint>
bash scripts/hum-snap-bypass.sh run     foo.snap <binary> [args...]
bash scripts/hum-snap-bypass.sh list           # active FUSE mounts
```

### How it works

1. **extract** uses `unsquashfs` to decompress the xz-compressed squashfs
   image into a plain directory tree—no snapd, no cgroup scope, no AppArmor.
2. **mount** uses `squashfuse` to FUSE-mount the `.snap` file read-only.
   No kernel squashfs module or root privileges needed (FUSE runs in userspace).
3. **run** extracts once, sets the `SNAP*` environment variables and
   `LD_LIBRARY_PATH` that snaps expect, then execs the binary directly.

### Required host packages

```bash
sudo apt-get install -y squashfs-tools squashfuse xz-utils file fuse3
```

These are already included in the dev container Dockerfile.

All paths can be overridden via `HUM_SNAP_EXTRACT_ROOT` and
`HUM_SNAP_MOUNT_ROOT` environment variables.  Run `--help` for full usage.

## Snap server (loop-mount + cgroup scope)

When your environment has loop devices (loop0–9), kernel squashfs support,
and cgroup v2 but **no systemd as PID 1**, the snap server script can:

1. Move root-cgroup processes into a child cgroup (`hum-init`) so the root
   `subtree_control` becomes writable.
2. Create a `snap.hum` cgroup scope for snap workloads.
3. Loop-mount `.snap` files at `/snap/<name>` using the kernel squashfs
   driver — exactly like snapd would, but without snapd.

```bash
sudo bash scripts/hum-snap-server.sh up                           # bootstrap
sudo bash scripts/hum-snap-server.sh loop-mount foo.snap mysnap   # mount at /snap/mysnap
/snap/mysnap/bin/some-binary                                      # run directly
sudo bash scripts/hum-snap-server.sh loop-unmount mysnap          # clean up
sudo bash scripts/hum-snap-server.sh status                       # full report
sudo bash scripts/hum-snap-server.sh down                         # teardown
```

### Why not just use snapd directly?

`snapd` v2.73 has a 5-second idle timeout and exits expecting systemd
socket-activation to restart it.  Without systemd as PID 1 (PID 1 is
`pod-daemon` in Cursor Cloud, `init` in Penguin, etc.) snapd becomes a
zombie within seconds.  The server script replaces the mount/cgroup layer
that snapd would normally manage, while `hum-snap-bypass.sh` handles
the userspace FUSE/extract path for environments without root.

### Choosing between bypass and server

| Feature | `hum-snap-bypass.sh` | `hum-snap-server.sh` |
|---|---|---|
| Root required | No (FUSE/extract) | Yes (loop + mount) |
| Mount type | FUSE userspace | Kernel squashfs |
| Performance | Good | Native (best) |
| cgroup scope | No | Yes |
| Loop devices needed | No | Yes |

Run `--help` on either script for full usage.

## Dev container status indicator (`<>`)

If you see the `<>` style status indicator in the bottom-right status area in
Chromium/Electron VS Code, it generally means the remote/dev environment is
active. In this project, that corresponds to running inside the configured
Dev Container.
