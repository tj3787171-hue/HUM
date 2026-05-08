#!/usr/bin/env bash
set -euo pipefail

SEMGREP_CONFIG="${SEMGREP_CONFIG:-.semgrep.yml}"
SEMGREP_TARGET="${SEMGREP_TARGET:-.}"
SEMGREP_VENV="${SEMGREP_VENV:-.venv-semgrep}"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/setup-semgrep-plugin.sh check
  bash scripts/setup-semgrep-plugin.sh scan
  bash scripts/setup-semgrep-plugin.sh bootstrap-kali-iso
  bash scripts/setup-semgrep-plugin.sh help

Modes:
  check               Report Semgrep/Yarn/bootstrap readiness.
  scan                Run Semgrep with .semgrep.yml if Semgrep is available.
  bootstrap-kali-iso  Prepare Semgrep in a local Python venv for Kali bootstrap use.

Environment:
  SEMGREP_CONFIG      Rules file (default: .semgrep.yml)
  SEMGREP_TARGET      Scan target (default: .)
  SEMGREP_VENV        Local venv path (default: .venv-semgrep)

Notes:
  - This script does not wipe filesystems or Btrfs journals.
  - Prefer `yarnpkg run semgrep:check` or `yarnpkg run semgrep:scan`
    when using package scripts.
EOF
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

semgrep_cmd() {
  if has_cmd semgrep; then
    printf '%s\n' "semgrep"
    return 0
  fi
  if [[ -x "$SEMGREP_VENV/bin/semgrep" ]]; then
    printf '%s\n' "$SEMGREP_VENV/bin/semgrep"
    return 0
  fi
  return 1
}

check_ready() {
  echo "=== HUM Semgrep bootstrap check ==="
  echo "config: $SEMGREP_CONFIG"
  echo "target: $SEMGREP_TARGET"
  echo

  if [[ -f "$SEMGREP_CONFIG" ]]; then
    echo "rules: present"
  else
    echo "rules: missing"
    return 1
  fi

  if has_cmd yarnpkg; then
    echo "yarnpkg: $(command -v yarnpkg)"
  elif has_cmd yarn; then
    echo "yarn: $(command -v yarn)"
  else
    echo "yarnpkg/yarn: missing (package scripts optional)"
  fi

  if cmd="$(semgrep_cmd)"; then
    echo "semgrep: $cmd"
    "$cmd" --version || true
  else
    echo "semgrep: missing"
    return 1
  fi
}

install_semgrep_venv() {
  if ! has_cmd python3; then
    echo "python3 is required for Semgrep venv bootstrap." >&2
    return 1
  fi
  if [[ ! -d "$SEMGREP_VENV" ]]; then
    python3 -m venv "$SEMGREP_VENV"
  fi
  "$SEMGREP_VENV/bin/python" -m pip install --upgrade pip semgrep
}

scan() {
  local cmd
  cmd="$(semgrep_cmd)" || {
    echo "Semgrep is not installed. Run: bash scripts/setup-semgrep-plugin.sh bootstrap-kali-iso" >&2
    return 1
  }
  "$cmd" scan --config "$SEMGREP_CONFIG" "$SEMGREP_TARGET"
}

bootstrap_kali_iso() {
  echo "=== HUM Semgrep Kali bootstrap ==="
  if has_cmd apt-get && [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    apt-get update
    apt-get install -y --no-install-recommends python3 python3-venv python3-pip
  else
    echo "Skipping apt package install (not root or apt-get unavailable)."
  fi
  install_semgrep_venv
  check_ready
}

case "${1:-check}" in
  check)
    check_ready
    ;;
  scan)
    scan
    ;;
  bootstrap-kali-iso|bootstrap)
    bootstrap_kali_iso
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
