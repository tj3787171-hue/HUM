# HUM

Private-by-default development container configuration for online/local development.

## What's included

- `.devcontainer/Dockerfile` based on Ubuntu 24.04 devcontainer image
- Useful LAN/network tools installed:
  - `iproute2`, `net-tools`
  - `iputils-ping`, `traceroute`
  - `dnsutils`
- `.devcontainer/devcontainer.json` with:
  - secure runtime defaults (`--init`, `no-new-privileges`)
  - `host.docker.internal` mapping via `host-gateway`
  - common forwarded ports (`3000`, `5173`, `8000`, `8080`) plus virtual desktop ports (`5901`, `6080`)
- `.devcontainer/post-create.sh` to print network info when container is created
- `.devcontainer/post-start.sh` to re-import private env and refresh runtime metadata
- `.devcontainer/import-environment.sh` to load `.devcontainer/dev.env` and generate runtime JSON metadata

## Use it

1. Open this repository in VS Code.
2. Install **Dev Containers** extension if needed.
3. Run **Dev Containers: Reopen in Container**.
4. After build, the terminal will show container network info.

## LAN notes

- This setup is optimized for Linux with Docker engine networking.
- It defaults to bridge networking and forwarded ports to reduce accidental exposure.
- For local-only access, bind services to `127.0.0.1` and use forwarded ports.
- If you intentionally need host-network mode for LAN testing, use a temporary local override.

## Re-container + import environment workflow

1. Rebuild/reopen the dev container.
2. On first create, `.devcontainer/dev.env` is generated from `.devcontainer/dev.env.example`.
3. Edit `.devcontainer/dev.env` with your private values (`chmod 600 .devcontainer/dev.env`).
4. Restart/reopen the container again to re-import values cleanly.

Environment import outputs:

- shell export file: `~/.config/hum-dev/imported.env`
- runtime JSON metadata: `~/.config/hum-dev/runtime.json`

This keeps settings in a JSON-readable form for tools/extensions while keeping secrets out of git.

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
