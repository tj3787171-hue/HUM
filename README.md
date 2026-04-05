# HUM

LAN-ready development container configuration for online/local development.

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

## LAN notes

- This setup is optimized for Linux with Docker engine networking.
- `--network=host` allows services in the container to be reachable on the host/LAN stack.
- On non-Linux hosts, host-network support can be limited by Docker Desktop behavior.

## Virtual setup config bundle

The repository now includes a `websetup/` tree for virtual phase planning:

- `websetup/sdv/manifest.json` and `python3 -m websetup.sdv validate`
- `websetup/virtual/virtual-setup.yml`
- `websetup/virtual/inventory.csv`
- `websetup/virtual/*.json` with schemas

Start points:

```bash
PYTHONPATH=/workspaces/<repo> python3 -m websetup.sdv validate
PYTHONPATH=/workspaces/<repo> python3 -m websetup.sdv apply
```

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
  --source websetup/virtual/network-matrix.json \
  --xml-file ./rootDesc.xml \
  --source-url http://192.168.68.1:1900/pttlb/rootDesc.xml \
  --device-mac 4C:EA:41:63:E6:C6 \
  --asserted-by team \
  --paper-slug hum-network-paper \
  --paper-title "HUM network phase notes" \
  --paper-author team \
  --paper-summary "Combined network + gateway handoff snapshot." \
  --evidence-key ev-handoff-001 \
  --property-hex 0x0102 \
  --payload-file websetup/virtual/network-matrix.json \
  --source-kind handoff \
  --source-ref websetup/virtual/network-matrix.json
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
