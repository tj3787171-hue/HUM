# Websetup virtual-phase bundle

This repository includes a devcontainer-first bundle for staging the next
virtual networking phase.

## Purpose

- Keep virtual setup inputs in version control (`YAML`, `CSV`, `JSON`).
- Align planned topology with the existing host-side helper:
  `scripts/hum-dev-netns.sh`.
- Keep `10.11.8.0/24` as the internal SDV-style segment and map LAN/dev paths
  explicitly.

## In the devcontainer

The `.devcontainer` config is prepared for network namespace work:

- `--privileged`, `NET_ADMIN`, `NET_RAW`
- host networking enabled
- Python, `jq`, `yq`, and shell/network diagnostics installed

Bring up the local namespace chain from the repository root:

```bash
sudo bash scripts/hum-dev-netns.sh up
sudo bash scripts/hum-dev-netns.sh status
```

## Files

- `INDEX.md` — quick navigation.
- `virtual/virtual-setup.yml` — orchestration metadata and node defaults.
- `virtual/inventory.csv` — host/node inventory.
- `virtual/features.json` — feature flags.
- `virtual/network-matrix.json` — logical routing/topology edges.
- `virtual/bindings.json` — wiring between scripts and virtual config.
- `virtual/catalog.json` — artifact catalog.
- `virtual/schemas/*.json` — JSON schema files for editor/validation support.

## Notes

- `192.168.68.x` is represented as a LAN/dev node hint; replace `x` with the
  actual DHCP lease when known.
- Keep secrets/keys out of git. This bundle stores only non-secret planning
  metadata.
