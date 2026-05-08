#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/btrfs-journal-safety.sh check
  bash scripts/btrfs-journal-safety.sh refuse-wipe
  bash scripts/btrfs-journal-safety.sh help

This helper is intentionally non-destructive. It reports Btrfs state and
refuses journal/filesystem wipe requests. Use vendor recovery documentation and
offline backups for destructive filesystem repair.
EOF
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

check_btrfs() {
  echo "=== HUM Btrfs safety check ==="
  echo "Policy: no automated Btrfs journal/filesystem wipe."
  echo

  echo "[mounted Btrfs filesystems]"
  if grep -w btrfs /proc/mounts 2>/dev/null; then
    true
  else
    echo "(none detected)"
  fi
  echo

  echo "[kernel support]"
  if grep -qw btrfs /proc/filesystems 2>/dev/null; then
    echo "btrfs filesystem support: present"
  else
    echo "btrfs filesystem support: not listed"
  fi
  echo

  echo "[tooling]"
  if has_cmd btrfs; then
    echo "btrfs tool: $(command -v btrfs)"
    btrfs --version 2>/dev/null || true
  else
    echo "btrfs tool: missing"
  fi
}

refuse_wipe() {
  echo "Refusing destructive Btrfs journal/filesystem wipe automation." >&2
  echo "Create verified backups and perform manual offline recovery if needed." >&2
  return 2
}

case "${1:-check}" in
  check)
    check_btrfs
    ;;
  refuse-wipe)
    refuse_wipe
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
