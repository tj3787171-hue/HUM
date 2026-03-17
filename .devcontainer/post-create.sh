#!/usr/bin/env bash
set -euo pipefail

echo "Dev container ready."
echo "Network summary:"
ip -brief addr || true
echo
echo "Default route:"
ip route show default || true
echo
echo "Running host readiness diagnostics (backup media, connectivity, MAC inventory)..."
bash scripts/host-readiness-check.sh || true
