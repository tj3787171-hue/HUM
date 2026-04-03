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
