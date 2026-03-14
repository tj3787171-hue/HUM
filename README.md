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
