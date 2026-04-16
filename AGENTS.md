# AGENTS.md

## Cursor Cloud specific instructions

This repository is a **devcontainer configuration** project (HUM). It contains no application source code — only `.devcontainer/` files that define a LAN-ready Docker development container based on Ubuntu 24.04.

### Repository structure

- `.devcontainer/Dockerfile` — image definition (installs `iproute2`, `net-tools`, `iputils-ping`, `traceroute`, `dnsutils`)
- `.devcontainer/devcontainer.json` — container config (host-network mode, port forwarding, VS Code extensions)
- `.devcontainer/post-create.sh` — prints network summary on container creation
- `site/` — PHP-served web presence with SVG network map and NETNS data collection

### Running the HUM site

1. **Collect network data:** `python3 site/data/collect_netns.py` (writes `topology.json` + `topology.xml`)
2. **Start the dev server:** `php -S 0.0.0.0:8080 -t site` (serves on port 8080)
3. **Browse:** `http://localhost:8080/welcome.html` → portals to `index.php` (SVG map) → `navigate.php` (NETNS feedback loop)

Site pages:
- `welcome.html` — portal/splash page, auto-redirects to `index.php`
- `index.php` — main navigation page with SVG environment map, interface/route/veth tables
- `navigate.php` — NETNS-veth@peer collector with re-collect button and XML source view
- `data/topology.xml` — raw XML topology data
- `assets/info.css` + `assets/app.js` — styling and client-side SVG map renderer

### How to verify the setup

There is no traditional build/lint/test cycle. To validate the configuration:

1. **Build the Docker image:** `docker build -f .devcontainer/Dockerfile -t hum-lan-dev .`
2. **Validate devcontainer.json:** `python3 -c "import json; json.load(open('.devcontainer/devcontainer.json'))"`
3. **Run the post-create script:** `bash .devcontainer/post-create.sh`
4. **Verify networking tools:** `which ip ping traceroute dig netstat`

### Cloud VM caveats

- Docker must be started manually: `sudo dockerd &` (wait ~3 seconds before running Docker commands).
- Microsoft Container Registry (`mcr.microsoft.com`) is blocked by cloud VM egress restrictions. The Dockerfile cannot be fully built via `docker build` in this environment. Validation must rely on syntax checks and running equivalent tools on the host (which is also Ubuntu 24.04).
- Docker Hub is also blocked for image pulls.
- The host Ubuntu 24.04 environment matches the Dockerfile's base image, so the networking tools can be installed and tested directly on the host as a substitute for container-based validation.
