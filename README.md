# HUM

Private-by-default development container configuration for online/local development.

## What's included

- `.devcontainer/Dockerfile` based on Ubuntu 24.04 devcontainer image
- Useful LAN/network tools installed:
  - `iproute2`, `net-tools`
  - `iputils-ping`, `traceroute`
  - `dnsutils`
- Additional virtual-setup tools:
  - `iptables`, `bridge-utils`, `ethtool`
  - `python3`, `jq`, `yq`, `shellcheck`
- `.devcontainer/devcontainer.json` with:
  - secure runtime defaults (`--init`, `no-new-privileges`)
  - `host.docker.internal` mapping via `host-gateway`
  - common forwarded ports (`3000`, `5173`, `8000`, `8080`) plus virtual desktop ports (`5901`, `6080`)
- `.devcontainer/post-create.sh` to print network info when container is created
- `.devcontainer/post-start.sh` to re-import private env and refresh runtime metadata
- `.devcontainer/import-environment.sh` to load `.devcontainer/dev.env` and generate runtime JSON metadata
  - host-network runtime flag (`--network=host`) for Linux LAN access
  - privileged runtime for netns/veth/macsec experiments (`NET_ADMIN`, `NET_RAW`)
  - `host.docker.internal` mapping via `host-gateway`
  - common forwarded ports (`3000`, `5173`, `8000`, `8080`)
- `.devcontainer/post-create.sh` to print network/module/tooling status at container create
- `websetup/` bundle for SDV + virtual phase configuration (`.yml`, `.csv`, `.json`)

## Use it

1. Open this repository in VS Code.
2. Install **Dev Containers** extension if needed.
3. Run **Dev Containers: Reopen in Container**.
4. After build, the terminal will show container network info.

### Devcontainer storage / mountpoints

The devcontainer now provisions a broader scratch + volume layout for large
artifact workflows:

- `/mnt/default` (tmpfs, 128G, in-memory scratch target for fast staging)
- named volumes:
  - `/mnt/default-vol`
  - `/mnt/virtual-drive`
  - `/iso-staging`
  - `/iso-output`
- host downloads bind mount (if available on host):
  - `${HOME}/Downloads` -> `/host-downloads`

Use `scripts/virtual-drive-access.sh` for simple "cdd 0|1" style loop mount
management of local ISO/IMG files.

## LAN notes

- This setup is optimized for Linux with Docker engine networking.
- It defaults to bridge networking and forwarded ports to reduce accidental exposure.
- For local-only access, bind services to `127.0.0.1` and use forwarded ports.
- If you intentionally need host-network mode for LAN testing, use a temporary local override.
- `.devcontainer/docker-compose.lan.yml` remains available as an explicit host-network profile for local Linux LAN experiments.

## Re-container + import environment workflow

1. Rebuild/reopen the dev container.
2. On first create, `.devcontainer/dev.env` is generated from `.devcontainer/dev.env.example`.
3. Edit `.devcontainer/dev.env` with your private values (`chmod 600 .devcontainer/dev.env`).
4. Restart/reopen the container again to re-import values cleanly.

Environment import outputs:

- shell export file: `~/.config/hum-dev/imported.env`
- runtime JSON metadata: `~/.config/hum-dev/runtime.json`

This keeps settings in a JSON-readable form for tools/extensions while keeping secrets out of git.

## LVM / encrypted cloud service planning

Before moving backup data, location metadata, or encrypted cloud-service roots
into LVM-backed storage, generate a non-destructive plan:

```bash
python3 scripts/hum-lvm-cloud-plan.py --output diagnostics/lvm-cloud-plan.json
```

The report includes:

- current mounts and large-block-device candidates
- whether LVM / cryptsetup / rclone tooling is installed
- likely local cloud roots (`~/Dropbox`, `~/Nextcloud`, etc.)
- private listener bind settings imported from `HUM_VDESK_BIND` and `HUM_CHROME_REMOTE_DEBUG_ADDR`

Use `--source /path/to/ssd-or-cloud-root` to include the intended backup source
path in the report. The script does not create physical volumes, encrypt disks,
mount filesystems, or contact cloud providers; it only records state for review.

The default devcontainer is private-by-default bridge networking with explicit
forwarded ports. If you need the older LAN host-network profile for local lab
work, use `.devcontainer/docker-compose.lan.yml` intentionally as a local
override rather than as the default container path.

## Virtual desktop privacy defaults

- Recommended virtual desktop bind host: `127.0.0.1`
- Recommended Chrome debug bind host: `127.0.0.1`
- Suggested forwarded virtual desktop ports:
  - `5901` (VNC)
  - `6080` (web desktop/noVNC)

These defaults keep access for you (and trusted local forwarding endpoints), not broad network listeners.

## Penguin terminal dev naming (Proxy + Docker + Dummy)

If you want the laptop Penguin terminal to use stable developer names that parallel
the original proxy/docker/dummy model, use:

```bash
sudo bash scripts/hum-dev-netns.sh up
```

Requirement: `ip` command from `iproute2` must be installed in the Penguin terminal.

This creates/maintains:

- proxy namespace: `hum-proxy-ns`
- peer namespace: `hum-peer-ns`
- upstream proxy veth pair: `hum-proxy-host0` (root) <-> `hum-proxy-ns0` (proxy ns)
- downstream peer chain pair: `hum-proxy-peer0` (proxy ns) <-> `hum-peer-ns0` (peer ns)
- dummy interface: `hum-dummy0`
- a status view that reports full chain recv-ready state and `docker0` if present

Useful commands:

```bash
sudo bash scripts/hum-dev-netns.sh status
sudo bash scripts/hum-dev-netns.sh status --json
sudo bash scripts/hum-dev-netns.sh down
```

- peer namespace: `hum-peer-ns`
- proxy veth pair: `hum-proxy-host0` (root) <-> `hum-proxy-ns0` (inside proxy netns)
- peer chain veth pair: `hum-proxy-peer0` (inside proxy netns) <-> `hum-peer-ns0` (inside peer netns)
- proxy veth pair: `hum-proxy-host0` (root) <-> `hum-proxy-ns0` (inside netns)
- peer namespace: `hum-peer-ns`
- peer veth pair: `hum-peer-host0` (inside `hum-proxy-ns`) <-> `hum-peer-ns0` (inside `hum-peer-ns`)
- dummy interface: `hum-dummy0`
- a status view that also reports `docker0` if present

The default topology is now a peer chain:

`root -> hum-proxy-host0 -> hum-proxy-ns -> hum-peer-host0 -> hum-peer-ns`
- peer namespace: `hum-peer-ns` (enabled by default)
- peer veth pair: `hum-proxy-peer0` (inside `hum-proxy-ns`) <-> `hum-peer-ns0` (inside `hum-peer-ns`)
- dummy interface: `hum-dummy0`
- a status view that also reports `docker0` if present and shows peer-route state

Peer veth chain sketch:

```text
root namespace
  hum-proxy-host0 10.200.0.1/30 fe80::1/64
    || veth peer ||
netns hum-proxy-ns
  hum-proxy-ns0   10.200.0.2/30 fe80::2/64
    -> default IPv4 via 10.200.0.1
    -> default IPv6 via fe80::1

side links:
  hum-dummy0
  docker0 (if present)
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
bash scripts/hum-dev-netns.sh guide
sudo bash scripts/hum-dev-netns.sh status
sudo bash scripts/hum-dev-netns.sh collect
sudo bash scripts/hum-dev-netns.sh trace
sudo bash scripts/hum-dev-netns.sh plot
sudo bash scripts/hum-dev-netns.sh down
```

`guide` prints the current peer veth chain plus the exact `up`, `status`,
`ping`, `trace`, and `down` commands to verify it end-to-end. When run
without `sudo`, the netns side can show as `unknown` if `ip -n` introspection
is denied; use `sudo bash scripts/hum-dev-netns.sh status` for authoritative
peer state.

All names can be overridden through `HUM_*` environment variables shown by:

```bash
bash scripts/hum-dev-netns.sh --help
```

The veth chain now carries link-local IPv6 for tracing:

- root<->proxy segment:
  - host side: `fe80::1/64` (default `HUM_PROXY_HOST_LL6`)
  - proxy ns side: `fe80::2/64` (default `HUM_PROXY_NS_LL6`)
- proxy<->peer segment:
  - proxy ns side: `fe80::11/64` (default `HUM_PROXY_PEER_LL6`)
  - peer ns side: `fe80::12/64` (default `HUM_PEER_NS_LL6`)

`trace` reports:

- peer chain recv-ready state
- downstream nested RX packet counters (host + proxy + peer)
- SMAC64-style trace IDs derived from interface MAC addresses
- IPv4/IPv6 route and neighbor snapshots for both proxy + peer namespaces

### Telemetry database

Use `collect` to emit a structured JSON snapshot, then store it in SQLite:

```bash
sudo bash scripts/hum-dev-netns.sh collect > diagnostics/netns-snapshot.json
python3 scripts/hum-telemetry-db.py ingest --database data/telemetry.db --file diagnostics/netns-snapshot.json
python3 scripts/hum-telemetry-db.py query --database data/telemetry.db --last 5
python3 scripts/hum-telemetry-db.py alerts --database data/telemetry.db
```

For continuous local collection:

```bash
sudo python3 scripts/hum-telemetry-db.py watch --database data/telemetry.db --interval 5
```

The telemetry database records snapshots, hops, counters, routes, and alerts.
It uses only Python stdlib modules.

## FF0000 merger plot guidance

`/ff0000.html` now includes an on-screen **Merger plot guidance** block so users can
quickly tune and validate auto-refresh behavior:

- set Lines/Columns first to define density
- raise Velocity to merge faster
- use Start auto refresh after changes
- watch live refresh interval feedback in milliseconds
`plot` prints a merger-style topology and guidance commands for bringing the
peer veth chain up or validating traffic when it is already up.

The veth chain carries link-local IPv6 for tracing:

- root side: `fe80::1/64` on `hum-proxy-host0` (default `HUM_PROXY_HOST_LL6`)
- proxy side (root link): `fe80::2/64` on `hum-proxy-ns0` (default `HUM_PROXY_NS_LL6`)
- proxy side (peer link): `fe80::11/64` on `hum-proxy-peer0` (default `HUM_PROXY_PEER_LL6`)
- peer side: `fe80::12/64` on `hum-peer-ns0` (default `HUM_PEER_NS_LL6`)

The peer chain also carries link-local IPv6 for tracing:

- proxy side: `fe80::5/64` (default `HUM_PEER_PROXY_LL6`)
- peer side: `fe80::6/64` (default `HUM_PEER_NS_LL6`)

Set `HUM_ENABLE_PEER_CHAIN=0` if you want to keep the original single-pair setup.

`trace` reports:

- peer recv-ready state for both root<->proxy and proxy<->peer links
- downstream nested RX packet counters (host + proxy + peer)
- SMAC64-style trace IDs derived from interface MAC addresses
- IPv4/IPv6 route and neighbor snapshots for the proxy + peer namespaces
- peer recv-ready state
- peer chain recv-ready state plus the guidance path
- downstream nested RX packet counters (host + netns)
- peer chain RX packet counters (proxy + peer)
- SMAC64-style trace IDs derived from interface MAC addresses
- IPv4/IPv6 route and neighbor snapshots for the proxy and peer namespaces
- peer-chain recv-ready state (when enabled)
- downstream nested RX packet counters (host + netns, or host + proxy-main + proxy-peer + peer when enabled)
- SMAC64-style trace IDs derived from interface MAC addresses
- IPv4/IPv6 route and neighbor snapshots for the proxy namespace
- IPv4/IPv6 route and neighbor snapshots for the peer namespace (when enabled)

## Merger plot – peer veth chain

A multi-hop peer veth chain extends the single proxy veth pair into a
series of namespaces connected end-to-end.  Each namespace acts as a
forwarding peer, and the final namespace is the **merger point** where
traffic from every preceding hop converges.

```
[root] ──veth── [peer:1] ──veth── [peer:2] ──veth── [merge:3]
```

### Quick start

```bash
# Bring up a 3-hop chain (default)
sudo bash scripts/hum-veth-chain.sh up

# Print the ASCII merger-plot diagram
bash scripts/hum-veth-chain.sh plot

# Check per-hop peer readiness and rx counters
sudo bash scripts/hum-veth-chain.sh status

# Tear down
sudo bash scripts/hum-veth-chain.sh down
```

Use `--length N` to change the number of hops (1–16):

```bash
sudo bash scripts/hum-veth-chain.sh up --length 5
bash scripts/hum-veth-chain.sh plot --length 5
```

### Addressing scheme

Each hop gets a `/30` IPv4 subnet plus link-local IPv6:

| Hop | Left (upstream) | Right (downstream) |
|-----|----------------|--------------------|
| 1 | `10.201.1.1/30` (root) | `10.201.1.2/30` (ns-1) |
| 2 | `10.201.2.1/30` (ns-1) | `10.201.2.2/30` (ns-2) |
| 3 | `10.201.3.1/30` (ns-2) | `10.201.3.2/30` (ns-3) |

IPv6 link-local follows the pattern `fe80::H:1/64` / `fe80::H:2/64`
per hop H.

Override the base network with `HUM_CHAIN_BASE_NET` (default `10.201`).

### Merger plot guidance

The merger plot is a traffic-convergence model:

- **Peer namespaces** (intermediate hops) have `ip_forward=1` enabled
  automatically.  They relay packets toward the next hop.
- **The merger namespace** (final hop) is where all forwarded traffic
  arrives.  Use it for captures, filters, or services that need to
  observe the full chain's traffic.
- **Verification** – from the tail of the chain, confirm end-to-end
  reachability:
  ```bash
  sudo ip netns exec hum-chain-ns3 ping -c2 10.201.1.1
  ```
- **Traffic shaping** – add `iptables`/`nftables` rules in any peer
  namespace to mark, redirect, or rate-limit packets as they traverse
  the chain.
- **Capture at the merger point**:
  ```bash
  sudo ip netns exec hum-chain-ns3 tcpdump -n -i hum-chain-h3R
  ```
- **Coexistence** – the chain uses the `10.201.x.y` range and
  `hum-chain-*` names, so it runs alongside the existing
  `hum-proxy-*` setup without conflicts.

### Environment overrides

| Variable | Default | Description |
|----------|---------|-------------|
| `HUM_CHAIN_PREFIX` | `hum-chain` | Namespace/interface name prefix |
| `HUM_CHAIN_LENGTH` | `3` | Number of hops |
| `HUM_CHAIN_BASE_NET` | `10.201` | First two octets of hop subnets |

Quick peer verification:

```bash
sudo ip netns exec hum-proxy-ns ping -c 1 10.200.0.1
sudo ip netns exec hum-proxy-ns ping -6 -I hum-proxy-ns0 -c 1 fe80::1
# optional zone-style form:
# sudo ip netns exec hum-proxy-ns ping -6 -c 1 fe80::1%hum-proxy-ns0
```

If IPv6 still fails while IPv4 works, use `status` to inspect the host veth's
other `fe80::/64` address and test that EUI-64 address, then check ICMPv6
policy such as `ip6tables`/`nft` rules or
`sysctl net.ipv6.icmp.echo_ignore_all`.

### Merger plot workflow

The FF0000 page at `/ff0000.html` now includes a merger-plot guide for the peer
veth chain. Before using the plot, bring up the proxy path and confirm the chain
is ready:

```bash
sudo bash scripts/hum-dev-netns.sh up
sudo bash scripts/hum-dev-netns.sh status
```

The guide and plot assume the default chain:

- root namespace interface: `hum-proxy-host0` (`10.200.0.1/30`, `fe80::1/64`)
- proxy namespace interface: `hum-proxy-ns0` (`10.200.0.2/30`, `fe80::2/64`)
- proxy namespace: `hum-proxy-ns`
- dummy endpoint: `hum-dummy0` (`198.18.0.1/24`)

Readiness checks before relying on the plot:

- `peer recv-ready: yes`
- populated `trace-smac64 host` and `trace-smac64 ns` values
- root and netns addresses that match the chain shown in the page

Use trace mode when the merger plot suggests changed redraw cadence or
downstream activity:

```bash
sudo bash scripts/hum-dev-netns.sh trace
sudo bash scripts/hum-dev-netns.sh down
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

## Build a bootable ISO

Generate a bootable ISO containing all HUM toolkit scripts:

```bash
sudo apt-get install -y genisoimage syslinux-utils isolinux
bash scripts/hum-build-iso.sh dist/hum-toolkit.iso
```

The ISO uses ISOLINUX, includes all scripts and documentation, and can be
burned to USB/CD or loop-mounted:

```bash
sudo mount -o loop dist/hum-toolkit.iso /mnt
ls /mnt/hum/scripts/
```

A download page is available at `docs/download.html`—host it on any static
server and point the download link to wherever you publish the ISO.

## Chromebook lab download-site + Stripe visibility

Use the Chromebook lab helper to verify MAGMA/KALI startup visibility and host
the toolkit download page from one command:

```bash
MAGMA_CHECK_URL="http://<magma-startup>/stripe" \
KALI_CHECK_URL="http://<kali-startup>/stripe" \
LAB_PORT=8088 \
bash scripts/chromebook-lab-download-site.sh all
```

Useful modes:

```bash
bash scripts/chromebook-lab-download-site.sh check-stripe
bash scripts/chromebook-lab-download-site.sh serve
bash scripts/chromebook-lab-download-site.sh all
```

Local test override:

```bash
STRIPE_EXPECT_TEXT="HUM Toolkit" \
MAGMA_CHECK_URL="http://127.0.0.1:8088/download.html" \
KALI_CHECK_URL="http://127.0.0.1:8088/download.html" \
bash scripts/chromebook-lab-download-site.sh check-stripe
```

## Host static IPv4 for proxy / Docker / VNC / TTY

Use `scripts/hum-host-static-ip.sh` when the host process should own a LAN
address such as `192.168.68.100/22`, while DNS remains untouched:

```bash
sudo HUM_HOST_STATIC_IF=eth0 \
  HUM_HOST_STATIC_CIDR=192.168.68.100/22 \
  HUM_HOST_GATEWAY=192.168.68.51 \
  bash scripts/hum-host-static-ip.sh apply
```

Inspect and remove:

```bash
bash scripts/hum-host-static-ip.sh status
bash scripts/hum-host-static-ip.sh env
sudo bash scripts/hum-host-static-ip.sh remove
```

The script reports proxy (`3128`), VNC (`5901`), noVNC (`6080`), and TTY/SSH
(`22`) listener state. It never edits `/etc/resolv.conf` or resolver settings.

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
node scripts/scanTelemetry.js "chrome-extension://bpmcpldpdmajfigpchkicefoigmkfalc/"
```

The scanner emits normalized flags like:

- `PHONE`
- `TRAP`
- `AI`
- `TELEGRAPHY`
- `BROWSER_HOOK`
- `CHROME_EXTENSION`
- `TARGET_EXTENSION` (for `bpmcpldpdmajfigpchkicefoigmkfalc`)

For JSON/conversation pipelines, the browser helper also exposes:

```javascript
extractChromeExtensionIds("chrome-extension://bpmcpldpdmajfigpchkicefoigmkfalc/");
```

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

## Evidence + network matrix database (SQLite)

When you need durable project records (papers, evidence blobs, MAC-linked devices,
and network matrix assertions), use:

```bash
python3 scripts/project_evidence_db.py --database data/project_evidence.db init
```

Create or update a normalized network matrix JSON:

```bash
python3 scripts/project_evidence_db.py --database data/project_evidence.db ingest-network \
  --network-json websetup/virtual/network-matrix.json
```

Insert a paper record:

```bash
python3 scripts/project_evidence_db.py --database data/project_evidence.db add-paper \
  --slug hum-network-paper \
  --title "HUM network phase notes" \
  --author "team" \
  --summary "Topology and evidence binding notes."
```

Insert a binary evidence blob linked to a paper and MAC:

```bash
python3 scripts/project_evidence_db.py --database data/project_evidence.db add-evidence \
  --evidence-key ev-001 \
  --paper-slug hum-network-paper \
  --property-hex 0x0101 \
  --payload-file ./some-capture.bin \
  --device-mac 4C:EA:41:63:E6:C6 \
  --source-kind manual-import
```

List data quickly:

```bash
python3 scripts/project_evidence_db.py --database data/project_evidence.db list-devices
python3 scripts/project_evidence_db.py --database data/project_evidence.db list-evidence
```

Capture UPnP root description metadata (from file or URL):

```bash
python3 scripts/project_evidence_db.py --database data/project_evidence.db ingest-upnp-xml \
  --xml-url http://192.168.68.1:1900/pttlb/rootDesc.xml \
  --source-url http://192.168.68.1:1900/pttlb/rootDesc.xml \
  --device-mac 4C:EA:41:63:E6:C6 \
  --asserted-by team

python3 scripts/project_evidence_db.py --database data/project_evidence.db list-gateway-metadata
```

One-shot handoff importer (network + UPnP + paper + evidence):

```bash
python3 scripts/project_evidence_db.py --database data/project_evidence.db handoff \
  --network-json websetup/virtual/network-matrix.json \
  --network-source websetup/virtual/network-matrix.json \
  --upnp-xml-file ./rootDesc.xml \
  --upnp-source-url http://192.168.68.1:1900/pttlb/rootDesc.xml \
  --device-mac 4C:EA:41:63:E6:C6 \
  --upnp-asserted-by team \
  --paper-slug hum-network-paper \
  --paper-title "HUM network phase notes" \
  --paper-author team \
  --paper-summary "Combined network + gateway handoff snapshot." \
  --evidence-key ev-handoff-001 \
  --evidence-property-hex 0x0102 \
  --evidence-payload-file websetup/virtual/network-matrix.json \
  --evidence-source-kind handoff \
  --evidence-source-ref websetup/virtual/network-matrix.json
```

Add `--dry-run` to preview the plan without writing.

## Backup helper

Create a timestamped backup bundle of project artifacts:

```bash
bash scripts/backup_project_bundle.sh /path/to/mounted/storage
```

It copies:

- `README.md`
- `.devcontainer/`
- `scripts/`
- `websetup/`
- `data/` (if present)

Use a mounted path you control (for example an exposed external drive path under your
Linux environment). The script creates:

`<target>/hum-backups/hum-backup-YYYYmmdd-HHMMSS/`

## Virtual drive helper (`cdd 0|1`)

For convenient mount/unmount inside the devcontainer:

```bash
# mount image at /mnt/virtual-drive/m0
bash scripts/virtual-drive-access.sh cdd 1 --source /host-downloads/kali-linux-2026.1-installer-amd64.iso

# unmount and detach loop
bash scripts/virtual-drive-access.sh cdd 0
```

Other commands:

```bash
bash scripts/virtual-drive-access.sh status
bash scripts/virtual-drive-access.sh mount --source /path/to/image.iso --mountpoint /mnt/virtual-drive/custom
bash scripts/virtual-drive-access.sh umount
```

## Host-only multi-user / graphical service guidance (AMD64)

If you are configuring a real host (not inside devcontainer) for
`multi-user.target` + optional GUI + service/socket units:

```bash
# host only
sudo systemctl set-default multi-user.target
sudo systemctl enable --now ssh
sudo systemctl status ssh
```

Optional GUI switch on host:

```bash
sudo apt install -y lightdm
sudo systemctl set-default graphical.target
```

For service-oriented app bootstrap, prefer explicit units under
`/etc/systemd/system/*.service` with optional `.socket` activation. Keep this
outside devcontainer unless you intentionally run a nested init system.

## Reproducible ISO build recipe (repo-owned)

To avoid losing custom ISO work between sessions, use the committed
`iso-build/` recipe in this repo. It writes artifacts to `data/iso-output/`.

Build dependencies (host/container with apt):

```bash
sudo apt-get update
sudo apt-get install -y live-build xorriso isolinux syslinux grub-efi-amd64-bin
```

Build:

```bash
bash iso-build/build.sh
```

Expected outputs:

- `data/iso-output/hum-custom-live.iso`
- `data/iso-output/hum-custom-live.iso.sha256`

## HTTPS file serving (optional, with HSTS support)

Use this when you want to serve generated ISO artifacts over TLS:

```bash
python3 scripts/https-file-server.py 8443 \
  --bind 0.0.0.0 \
  --directory data/iso-output \
  --cert /path/to/server.crt \
  --key /path/to/server.key
```

The server uses `ssl.SSLContext(...).load_cert_chain(cert, key)`.

Optional Strict-Transport-Security:

```bash
python3 scripts/https-file-server.py 8443 \
  --bind 0.0.0.0 \
  --directory data/iso-output \
  --cert /path/to/server.crt \
  --key /path/to/server.key \
  --hsts-max-age 31536000 \
  --hsts-include-subdomains
```

To disable HSTS explicitly, set `--hsts-max-age 0` (default is disabled).

## Encrypted cloud directory pack (chunked + compressed)

Create an encrypted cloud-friendly directory layout from any source folder. The
packer writes:

- `index.json` (manifest with aggregate checksum + per-file/per-chunk hashes)
- `online-index.html` (simple web directory page)
- `chunks/*.bin` (compressed + encrypted chunk files)

Defaults:

- chunk size: `4096` bytes
- minimum chunk size: `1024` bytes
- compression: `zlib` level `6`

Pack:

```bash
python3 scripts/hum_cloud_pack.py pack \
  --source ./data \
  --cloud-dir ./dist/cloud-data \
  --passphrase "change-me"
```

Validate against a known aggregate checksum:

```bash
python3 scripts/hum_cloud_pack.py pack \
  --source ./data \
  --cloud-dir ./dist/cloud-data \
  --passphrase "change-me" \
  --expected-aggregate-sha256 c058fd133d909759028353fea46d228c2fd8bcf945cf27680bb751fe1066fc3e
```

Restore:

```bash
python3 scripts/hum_cloud_pack.py restore \
  --cloud-dir ./dist/cloud-data \
  --target-dir ./dist/cloud-restored \
  --passphrase "change-me"
```

Host the generated cloud directory with:

```bash
python3 scripts/https-file-server.py 8443 \
  --bind 0.0.0.0 \
  --directory ./dist/cloud-data \
  --cert /path/to/server.crt \
  --key /path/to/server.key
```
