# HUM

LAN-focused development container for online/local development on Linux.

## What's included

- `.devcontainer/Dockerfile` based on Ubuntu 24.04 devcontainer image
- Network diagnostics tools:
  - `iproute2`, `net-tools`
  - `iputils-ping`, `traceroute`
  - `dnsutils`
- `.devcontainer/devcontainer.json` configured to use Docker Compose
- `.devcontainer/docker-compose.lan.yml` with:
  - `network_mode: host` for LAN-friendly behavior on Linux
  - `host.docker.internal` mapping (`host-gateway`)
  - long-running dev service (`sleep infinity`)
- `.devcontainer/post-create.sh` to print interfaces, routes, and listening ports

## Use it (LAN profile)

1. Open this repository in VS Code.
2. Ensure **Dev Containers** extension is installed.
3. Run **Dev Containers: Reopen in Container**.
4. The container starts from `docker-compose.lan.yml` and shares host network stack.
5. Check startup output in terminal for interfaces/routes/ports.

## LAN notes

- Optimized for Linux Docker engine.
- `network_mode: host` means published ports are usually not required for LAN access.
- `forwardPorts` are still listed for editor convenience.
- On Docker Desktop/non-Linux hosts, host networking may behave differently.
