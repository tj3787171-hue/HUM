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
