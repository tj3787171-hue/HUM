# AGENTS.md

## Cursor Cloud specific instructions

This is **HUM** — a LAN-ready devcontainer project with a PHP web presence. The devcontainer origin server hostname is `hum.org`. It includes TestDisk/PhotoRec recup data import and organization into `/home/troy/TEMPLATES` and `/home/troy/PHOTOS`.

### Repository structure

- `.devcontainer/Dockerfile` — image definition (networking tools + testdisk, hostname set to hum.org)
- `.devcontainer/devcontainer.json` — container config (host-network, hostname=hum.org, HUM_ORIGIN/RECUP_HOME env vars)
- `.devcontainer/post-create.sh` — prints network summary, runs recup-setup, displays workspace layout
- `.devcontainer/recup-setup.sh` — scans recup_dir.* from PhotoRec and classifies files into TEMPLATES/PHOTOS
- `site/` — PHP-served web presence with SVG network map, NETNS data, and recup browser

### Running the HUM site

1. **Collect network data:** `python3 site/data/collect_netns.py`
2. **Run recup import:** `HUM_ORIGIN=hum.org RECUP_HOME=/home/troy bash .devcontainer/recup-setup.sh`
3. **Build House of Corps:** `HUM_ORIGIN=hum.org RECUP_HOME=/home/troy python3 site/data/name_factory.py`
4. **Start the dev server:** `php -S 0.0.0.0:8080 -t site` (port 8080)
5. **Browse:** `http://localhost:8080/welcome.html`

Site pages:
- `welcome.html` — portal/splash, auto-redirects to `index.php`
- `index.php` — SVG environment map, interface/route/veth tables
- `navigate.php` — NETNS-veth@peer collector with re-collect and XML source view
- `recup.php` — recup data browser for TEMPLATES and PHOTOS at `/home/troy`
- `palace.php` — Palace of Web final product (House of Corps, wanted comb hierarchy, gram & comb)
- `convo.php` — JSON conversation API for all data sources (corps, gram, comb, palace, topology, etc.)
- `assets/info.css` + `assets/app.js` — styling and client-side SVG renderer

Data pipeline: `collect_netns.py` + `recup-setup.sh` → `name_factory.py` → `corps.json` + `sources.list` + `FINAL-PRODUCT/{gram,comb,palace}.json` → `palace.php`

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
