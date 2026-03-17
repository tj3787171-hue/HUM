# HUM

LAN-ready development container configuration for online/local development.

## What's included

- `.devcontainer/Dockerfile` based on Ubuntu 24.04 devcontainer image
- Useful LAN/network tools installed:
  - `iproute2`, `net-tools`
  - `iputils-ping`, `traceroute`
  - `dnsutils`, `curl`, `ca-certificates`
- `.devcontainer/devcontainer.json` with:
  - host-network runtime flag (`--network=host`) for Linux LAN access
  - `host.docker.internal` mapping via `host-gateway`
  - common forwarded ports (`3000`, `5173`, `8000`, `8080`)
- `.devcontainer/post-create.sh` to print network info and run host readiness diagnostics
- `scripts/host-readiness-check.sh` for:
  - mounted large backup media detection (e.g., 2TB SD)
  - GitHub and related endpoint connectivity checks
  - interface and MAC address inventory
  - connectivity index activity logging in `diagnostics/connectivity-index.csv`

## Use it

1. Open this repository in VS Code.
2. Install **Dev Containers** extension if needed.
3. Run **Dev Containers: Reopen in Container**.
4. After build, the terminal will show container network info.
5. For manual checks at any time:
   - `bash scripts/host-readiness-check.sh`
   - Strict mode (non-zero exit if any checks fail): `bash scripts/host-readiness-check.sh --strict`
   - Write JSON summary for external tooling:
     `bash scripts/host-readiness-check.sh --json=diagnostics/readiness.json`

## LAN notes

- This setup is optimized for Linux with Docker engine networking.
- `--network=host` allows services in the container to be reachable on the host/LAN stack.
- On non-Linux hosts, host-network support can be limited by Docker Desktop behavior.
- Backup-device matching is heuristic-based (size + mounted + removable/USB/MMC). If your 2TB SD is mounted, it should be detected and listed.
