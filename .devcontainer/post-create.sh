#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Dev container ready."
echo "Workspace: $ROOT_DIR"
echo
echo "Network summary:"
ip -brief addr || true
echo
echo "Default route(s):"
ip route show default || true
echo
echo "Default route(s) IPv6:"
ip -6 route show default || true
echo
echo "Kernel module check (macsec):"
if lsmod | grep -q "^macsec"; then
  echo "macsec module is loaded."
else
  echo "macsec module is not currently loaded (load on demand if needed)."
fi
echo
echo "Tooling check:"
for cmd in ip jq yq python3 shellcheck; do
  if command -v "$cmd" >/dev/null 2>&1; then
    echo "  - $cmd: ok"
  else
    echo "  - $cmd: missing"
  fi
done
