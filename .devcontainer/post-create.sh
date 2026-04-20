#!/usr/bin/env bash
set -euo pipefail

echo "Dev container ready (LAN profile)."
echo "Network interfaces:"
ip -brief addr || true
echo
echo "Default route:"
ip route show default || true
echo
echo "Listening ports (if any):"
ss -lntup || true
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ ! -f "${WORKSPACE_DIR}/.devcontainer/dev.env" && -f "${WORKSPACE_DIR}/.devcontainer/dev.env.example" ]]; then
  cp "${WORKSPACE_DIR}/.devcontainer/dev.env.example" "${WORKSPACE_DIR}/.devcontainer/dev.env"
  chmod 600 "${WORKSPACE_DIR}/.devcontainer/dev.env"
  echo "Created .devcontainer/dev.env from example. Review and edit private values."
fi

bash "${SCRIPT_DIR}/import-environment.sh" "${WORKSPACE_DIR}/.devcontainer/dev.env"
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
if command -v lsmod >/dev/null 2>&1; then
  if lsmod | grep -q "^macsec"; then
    echo "macsec module is loaded."
  else
    echo "macsec module is not currently loaded (load on demand if needed)."
  fi
else
  echo "lsmod command is unavailable; cannot inspect kernel modules."
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

echo
echo "Mountpoint check:"
for mp in /iso-staging /iso-output /mnt/default /mnt/default-vol /mnt/virtual-drive; do
  if mountpoint -q "$mp" 2>/dev/null; then
    echo "  - $mp: mounted"
  elif [[ -d "$mp" ]]; then
    echo "  - $mp: present (not mounted)"
  else
    echo "  - $mp: missing"
  fi
done
