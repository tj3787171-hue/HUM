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
- `../scripts/project_evidence_db.py` — SQLite-backed records for papers,
  evidence blobs, device MAC identity hints, and network matrix assertions.

## Notes

- `192.168.68.x` is represented as a LAN/dev node hint; replace `x` with the
  actual DHCP lease when known.
- Keep secrets/keys out of git. This bundle stores only non-secret planning
  metadata.

## Evidence / identity database

Initialize and use the project evidence database:

```bash
python3 scripts/project_evidence_db.py init --database data/project_evidence.db
python3 scripts/project_evidence_db.py upsert-device \
  --database data/project_evidence.db \
  --mac 4C:EA:41:63:E6:C6 \
  --label HUM
python3 scripts/project_evidence_db.py add-paper \
  --database data/project_evidence.db \
  --slug hum-network-paper \
  --title "HUM network matrix notes" \
  --author "team"
python3 scripts/project_evidence_db.py add-evidence \
  --database data/project_evidence.db \
  --paper-slug hum-network-paper \
  --property-hex 0x0101 \
  --payload-file websetup/virtual/network-matrix.json \
  --device-mac 4C:EA:41:63:E6:C6 \
  --source-kind config \
  --source-ref websetup/virtual/network-matrix.json
python3 scripts/project_evidence_db.py export-network-json \
  --database data/project_evidence.db \
  --output data/network-matrix.export.json
python3 scripts/project_evidence_db.py ingest-upnp-xml \
  --database data/project_evidence.db \
  --xml-url http://192.168.68.1:1900/pttlb/rootDesc.xml \
  --device-mac 4C:EA:41:63:E6:C6 \
  --asserted-by team
python3 scripts/project_evidence_db.py list-gateway \
  --database data/project_evidence.db
```

One-shot handoff import (network + UPnP + paper + evidence link):

```bash
python3 scripts/project_evidence_db.py handoff --database data/project_evidence.db \
  --network-json websetup/virtual/network-matrix.json \
  --network-source websetup/virtual/network-matrix.json \
  --xml-file /path/to/rootDesc.xml \
  --source-url http://192.168.68.1:1900/pttlb/rootDesc.xml \
  --device-mac 4C:EA:41:63:E6:C6 \
  --asserted-by team \
  --paper-slug hum-network-paper \
  --paper-title "HUM network matrix notes" \
  --paper-author team \
  --paper-summary "Topology and evidence binding notes." \
  --evidence-key ev-handoff-001 \
  --property-hex 0x0102 \
  --payload-file websetup/virtual/network-matrix.json \
  --source-kind config \
  --source-ref websetup/virtual/network-matrix.json
```
