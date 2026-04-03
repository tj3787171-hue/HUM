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

## Penguin terminal dev naming (Proxy + Peer Chain + Docker + Dummy)

If you want the laptop Penguin terminal to use stable developer names that parallel
the original proxy/docker/dummy model, use:

```bash
sudo bash scripts/hum-dev-netns.sh up
```

Requirement: `ip` command from `iproute2` must be installed in the Penguin terminal.

This creates/maintains:

- proxy namespace: `hum-proxy-ns`
- proxy veth pair: `hum-proxy-host0` (root) <-> `hum-proxy-ns0` (inside netns)
- peer namespace: `hum-peer-ns` (enabled by default)
- peer veth pair: `hum-proxy-peer0` (inside `hum-proxy-ns`) <-> `hum-peer-ns0` (inside `hum-peer-ns`)
- dummy interface: `hum-dummy0`
- a status view that also reports `docker0` if present

### Merger plot guidance

For merger plot work, use the default peer veth chain so traces include both legs:

```bash
sudo bash scripts/hum-dev-netns.sh up
sudo bash scripts/hum-dev-netns.sh trace
```

Topology:

- `root` -> `hum-proxy-host0` <-> `hum-proxy-ns0` -> `hum-proxy-peer0` <-> `hum-peer-ns0`

Quick peer-chain checks:

```bash
sudo bash scripts/hum-dev-netns.sh status
sudo ip netns exec hum-peer-ns ping -c 2 10.200.1.1
sudo ip netns exec hum-proxy-ns ping -c 2 10.200.1.2
```

Disable peer-chain mode if you only need the original single pair:

```bash
sudo env HUM_ENABLE_PEER_CHAIN=0 bash scripts/hum-dev-netns.sh up
```

Useful commands:

```bash
sudo bash scripts/hum-dev-netns.sh status
sudo bash scripts/hum-dev-netns.sh trace
sudo bash scripts/hum-dev-netns.sh down
```

All names can be overridden through `HUM_*` environment variables shown by:

```bash
bash scripts/hum-dev-netns.sh --help
```

The proxy veth pair now also carries link-local IPv6 for tracing:

- host side: `fe80::1/64` (default `HUM_PROXY_HOST_LL6`)
- netns side: `fe80::2/64` (default `HUM_PROXY_NS_LL6`)

`trace` reports:

- peer recv-ready state
- peer-chain recv-ready state (when enabled)
- downstream nested RX packet counters (host + netns, or host + proxy-main + proxy-peer + peer when enabled)
- SMAC64-style trace IDs derived from interface MAC addresses
- IPv4/IPv6 route and neighbor snapshots for the proxy namespace
- IPv4/IPv6 route and neighbor snapshots for the peer namespace (when enabled)

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

## Dev container status indicator (`<>`)

If you see the `<>` style status indicator in the bottom-right status area in
Chromium/Electron VS Code, it generally means the remote/dev environment is
active. In this project, that corresponds to running inside the configured
Dev Container.

## Telemetry scanner helper (including browser hooks)

Use this helper to flag potentially relevant terms in free text, including
browser/electron/chromium hook-up phrases:

```bash
node scripts/scanTelemetry.js "hook redirect force browser chromium agent"
```

The scanner emits normalized flags like:

- `PHONE`
- `TRAP`
- `AI`
- `TELEGRAPHY`
- `BROWSER_HOOK`

Browser polling example (every 3s):

```html
<input id="telemetry" />
<script src="scripts/scanTelemetry.js"></script>
<script>
  setInterval(() => {
    const el = document.getElementById("telemetry");
    if (el) scanTelemetry(el.value);
  }, 3000);
</script>
```

Or use the built-in helper:

```html
<script>
  startTelemetryPolling("telemetry", 3000);
</script>
```
