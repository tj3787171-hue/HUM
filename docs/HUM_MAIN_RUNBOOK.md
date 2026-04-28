# HUM main runbook

This document compiles the current HUM development, evidence, artifact, and ISO
workflow into one direct-run entry point. The repository stays lightweight: no
package manager, no lockfiles, and no generated dependencies are required.

## Layer map

| Layer | Inputs | Tools | Outputs |
|---|---|---|---|
| Virtual plan | `websetup/virtual/*.yml`, `*.json`, `inventory.csv` | `python3 scripts/validate_virtual_setup.py` | consistency result |
| SDV manifest | `websetup/sdv/manifest.json` | `python3 -m unittest discover -s tests -v` | validation tests |
| Runtime topology | `scripts/hum-dev-netns.sh` | `sudo bash scripts/hum-dev-netns.sh up/status/trace` | netns/veth chain |
| Lab UI | `site/*.php`, `site/assets/*.js` | `php -S 127.0.0.1:8000 -t site` | browser dashboard |
| Artifact layers | YAML/JSON/JAR/TAR/DEB/ISO/SNAP/TD.ZZ files | `python3 scripts/hum_artifact_layers.py` | JSON + Markdown evidence |
| Evidence database | network matrix, UPnP XML, payload files | `python3 scripts/project_evidence_db.py` | SQLite records |
| Toolkit ISO | scripts, docs, devcontainer files | `bash scripts/hum-build-iso.sh` | `dist/hum-toolkit.iso` |
| Live ISO | `iso-build/config/` | `sudo bash iso-build/build.sh` | `data/iso-output/*.iso` |

## Fresh setup check

Install only host tools that are needed by the commands you run:

```bash
sudo apt-get update
sudo apt-get install -y iproute2 php-cli shellcheck python3-pip jq yq
python3 -m pip install --user pyright
```

Optional ISO and package inspection tools:

```bash
sudo apt-get install -y genisoimage syslinux-utils isolinux squashfs-tools squashfuse xz-utils file fuse3
```

## One-pass validation

```bash
export PATH="$HOME/.local/bin:$PATH"
python3 -m unittest discover -s tests -v
python3 scripts/validate_virtual_setup.py
shellcheck scripts/hum-dev-netns.sh .devcontainer/post-create.sh
pyright scripts/deepseek_db_link.py
```

## Interactive lab

Start the PHP lab:

```bash
php -S 127.0.0.1:8000 -t site
```

Open:

- `http://127.0.0.1:8000/index.php` for live topology.
- `http://127.0.0.1:8000/layers.html` for artifact-layer filtering after a scan.

## Artifact-layer scan

Generate refreshed artifact evidence from disk:

```bash
python3 scripts/hum_artifact_layers.py \
  --root . \
  --output-json site/data/artifact-layers.json \
  --output-markdown docs/HUM_ARTIFACT_LAYERS.generated.md \
  --benchmark
```

The scanner classifies:

- structured inputs: `.yaml`, `.yml`, `.json`
- JVM payloads: `.jar`
- archive layers: `.tar`, `.tar.gz`, `.tgz`, `.tar.xz`, `.tar.zst`
- package layers: `.deb`, `.snap`
- compressed transfer layers: `.td.zz`, `.zz`
- final media: `.iso`

It records size, mtime, SHA-256, source path, and optional read throughput. Use
the Markdown output for reviews and the JSON output for browser filtering.

## Debian and `.deb` path

For Debian mirror/package workflows:

- Prefer standard Debian mirrors such as `http://deb.debian.org/debian/` when
  building the live ISO.
- Verify pool packages with `dpkg-deb -I` before trusting media contents.
- Use `kali-iso-server/hostile-env-defense/iso-verify-sanitize.sh` when checking
  ISO pool integrity.

## ISO creation

Small toolkit ISO:

```bash
sudo apt-get install -y genisoimage syslinux-utils isolinux
bash scripts/hum-build-iso.sh dist/hum-toolkit.iso
```

Live ISO recipe:

```bash
sudo apt-get install -y live-build xorriso isolinux syslinux grub-efi-amd64-bin
sudo HUM_DEBIAN_MIRROR="http://deb.debian.org/debian/" \
  HUM_DEBIAN_SECURITY_MIRROR="http://deb.debian.org/debian-security/" \
  bash iso-build/build.sh
```

Expected live outputs:

- `data/iso-output/hum-live-<timestamp>.iso`
- `data/iso-output/hum-live-<timestamp>.iso.sha256`

## Direct-run evidence loop

1. Refresh artifact evidence with `hum_artifact_layers.py`.
2. Validate virtual and SDV config.
3. Run the netns chain when network state matters.
4. Open the PHP/JS lab and inspect the Layers page.
5. Build the toolkit ISO or live ISO.
6. Re-run the artifact scan over `dist/` or `data/iso-output/` to capture ISO
   hashes and benchmark evidence from actual disk reads.
