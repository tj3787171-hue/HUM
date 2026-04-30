#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_FILE="${1:-${HUM_ENV_FILE:-${WORKSPACE_DIR}/.devcontainer/dev.env}}"
TARGET_DIR="${HOME}/.config/hum-dev"
TARGET_ENV="${TARGET_DIR}/imported.env"
TARGET_JSON="${TARGET_DIR}/runtime.json"
BASHRC="${HOME}/.bashrc"

mkdir -p "${TARGET_DIR}"
touch "${TARGET_ENV}"
chmod 600 "${TARGET_ENV}"

# Sanitize imported content: only KEY=VALUE lines, comments, and blanks are accepted.
# Values are treated as data and shell-escaped before sourcing to avoid command
# execution from private env files.
: > "${TARGET_ENV}"
if [[ -f "${ENV_FILE}" ]]; then
  while IFS= read -r line || [[ -n "${line}" ]]; do
    if [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]]; then
      continue
    fi
    if [[ "${line}" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
      key="${line%%=*}"
      value="${line#*=}"
      if [[ "${#value}" -ge 2 ]]; then
        first="${value:0:1}"
        last="${value: -1}"
        if [[ ( "${first}" == "'" && "${last}" == "'" ) || ( "${first}" == '"' && "${last}" == '"' ) ]]; then
          value="${value:1:${#value}-2}"
        fi
      fi
      printf -v escaped_value '%q' "${value}"
      printf '%s=%s\n' "${key}" "${escaped_value}" >> "${TARGET_ENV}"
    else
      echo "Skipping invalid environment line: ${line}" >&2
    fi
  done < "${ENV_FILE}"
fi

# shellcheck disable=SC2016
SOURCE_LINE='[ -f "$HOME/.config/hum-dev/imported.env" ] && set -a && . "$HOME/.config/hum-dev/imported.env" && set +a'
if [[ ! -f "${BASHRC}" ]]; then
  touch "${BASHRC}"
fi
if ! grep -Fq "${SOURCE_LINE}" "${BASHRC}"; then
  {
    echo
    echo "# HUM imported environment"
    echo "${SOURCE_LINE}"
  } >> "${BASHRC}"
fi

if [[ -s "${TARGET_ENV}" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "${TARGET_ENV}"
  set +a
fi

export HUM_RUNTIME_JSON_TARGET="${TARGET_JSON}"
export HUM_RUNTIME_JSON_SOURCE="${ENV_FILE}"
python3 - <<'PY'
import json
import os
from pathlib import Path

target = Path(os.environ["HUM_RUNTIME_JSON_TARGET"])
payload = {
    "owner_tag": os.environ.get("HUM_OWNER_TAG", "local-user"),
    "virtual_desktop_bind": os.environ.get("HUM_VDESK_BIND", "127.0.0.1"),
    "virtual_desktop_port": os.environ.get("HUM_VDESK_PORT", "6080"),
    "vnc_port": os.environ.get("HUM_VNC_PORT", "5901"),
    "chrome_remote_debug_bind": os.environ.get("HUM_CHROME_REMOTE_DEBUG_ADDR", "127.0.0.1"),
    "chrome_remote_debug_port": os.environ.get("HUM_CHROME_REMOTE_DEBUG_PORT", "9222"),
    "generated_from": os.environ["HUM_RUNTIME_JSON_SOURCE"],
}
target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
chmod 600 "${TARGET_JSON}"

echo "Imported environment file: ${ENV_FILE}"
echo "Shell source file: ${TARGET_ENV}"
echo "Runtime JSON metadata: ${TARGET_JSON}"
