#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ ! -f "${WORKSPACE_DIR}/.devcontainer/dev.env" && -f "${WORKSPACE_DIR}/.devcontainer/dev.env.example" ]]; then
  cp "${WORKSPACE_DIR}/.devcontainer/dev.env.example" "${WORKSPACE_DIR}/.devcontainer/dev.env"
  chmod 600 "${WORKSPACE_DIR}/.devcontainer/dev.env"
  echo "Created .devcontainer/dev.env from example. Review and edit private values."
fi

bash "${SCRIPT_DIR}/import-environment.sh" "${WORKSPACE_DIR}/.devcontainer/dev.env"

echo "Dev container ready."
echo "Network summary:"
ip -brief addr || true
echo
echo "Default route:"
ip route show default || true
