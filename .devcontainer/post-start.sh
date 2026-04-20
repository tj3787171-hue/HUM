#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${HUM_ENV_FILE:-${WORKSPACE_DIR}/.devcontainer/dev.env}"

bash "${SCRIPT_DIR}/import-environment.sh" "${ENV_FILE}"

echo
echo "Post-start security checks:"
echo "- Recommended listener bind: ${HUM_VDESK_BIND:-127.0.0.1}"
echo "- Recommended Chrome debug bind: ${HUM_CHROME_REMOTE_DEBUG_ADDR:-127.0.0.1}"
if [[ -f "${WORKSPACE_DIR}/.devcontainer/dev.env" ]]; then
  if command -v stat >/dev/null 2>&1; then
    perms="$(stat -c '%a' "${WORKSPACE_DIR}/.devcontainer/dev.env" 2>/dev/null || true)"
    if [[ -n "${perms}" && "${perms}" -gt 600 ]]; then
      echo "WARNING: .devcontainer/dev.env permissions are ${perms}; run: chmod 600 .devcontainer/dev.env"
    fi
  fi
else
  echo "No .devcontainer/dev.env found. Copy .devcontainer/dev.env.example when ready."
fi
