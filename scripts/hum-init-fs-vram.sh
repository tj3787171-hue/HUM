#!/usr/bin/env bash
set -euo pipefail

# Init-FS virtual RAM — tmpfs-backed scratch filesystem for SDV workloads.
# Provides an ephemeral RAM-backed mountpoint that persists only until
# unmount or reboot. Used by the SDV pipeline for fast staging of
# validation artifacts, netns state, and MACsec handoff material.

VRAM_MOUNTPOINT="${HUM_VRAM_MOUNTPOINT:-/mnt/hum-vram}"
VRAM_SIZE="${HUM_VRAM_SIZE:-64M}"
VRAM_MODE="${HUM_VRAM_MODE:-1777}"
VRAM_OWNER="${HUM_VRAM_OWNER:-}"
VRAM_SUBDIRS="${HUM_VRAM_SUBDIRS:-staging,state,handoff}"

usage() {
  cat <<'EOF'
Usage:
  sudo bash scripts/hum-init-fs-vram.sh mount
  sudo bash scripts/hum-init-fs-vram.sh umount
  bash scripts/hum-init-fs-vram.sh status
  bash scripts/hum-init-fs-vram.sh plan

Commands:
  mount    Create and mount tmpfs-backed virtual RAM filesystem
  umount   Unmount and clean up the virtual RAM filesystem
  status   Print current mount/usage status
  plan     Show exactly what mount would execute

Environment overrides:
  HUM_VRAM_MOUNTPOINT   Mount target           (default: /mnt/hum-vram)
  HUM_VRAM_SIZE         tmpfs size limit       (default: 64M)
  HUM_VRAM_MODE         Directory permissions  (default: 1777)
  HUM_VRAM_OWNER        Optional chown target  (default: none)
  HUM_VRAM_SUBDIRS      Comma-separated subdirs to create (default: staging,state,handoff)

Notes:
- Data in the virtual RAM FS is ephemeral and lost on umount or reboot.
- The SDV pipeline uses this for fast artifact staging and handoff state.
EOF
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "This action requires root. Re-run with sudo." >&2
    exit 1
  fi
}

log() {
  printf '[%(%H:%M:%S)T] %s\n' -1 "$*"
}

is_mounted() {
  mountpoint -q "$VRAM_MOUNTPOINT" 2>/dev/null
}

show_plan() {
  echo "=== Planned init-fs virtual RAM actions ==="
  echo "Mountpoint: $VRAM_MOUNTPOINT"
  echo "Size:       $VRAM_SIZE"
  echo "Mode:       $VRAM_MODE"
  echo "Subdirs:    $VRAM_SUBDIRS"
  echo
  echo "Would run:"
  echo "  mkdir -p \"$VRAM_MOUNTPOINT\""
  echo "  mount -t tmpfs -o size=$VRAM_SIZE,mode=$VRAM_MODE tmpfs \"$VRAM_MOUNTPOINT\""
  IFS=',' read -ra dirs <<< "$VRAM_SUBDIRS"
  for d in "${dirs[@]}"; do
    echo "  mkdir -p \"$VRAM_MOUNTPOINT/$d\""
  done
  if [[ -n "$VRAM_OWNER" ]]; then
    echo "  chown -R \"$VRAM_OWNER\" \"$VRAM_MOUNTPOINT\""
  fi
}

show_status() {
  echo "=== Init-FS virtual RAM status ==="
  echo "Mountpoint: $VRAM_MOUNTPOINT"
  echo "Configured size: $VRAM_SIZE"
  echo

  if is_mounted; then
    echo "[mounted] YES"
    echo
    echo "[usage]"
    df -h "$VRAM_MOUNTPOINT" 2>/dev/null || true
    echo
    echo "[contents]"
    ls -la "$VRAM_MOUNTPOINT" 2>/dev/null || true
    echo
    echo "[mount info]"
    grep " ${VRAM_MOUNTPOINT} " /proc/mounts 2>/dev/null || \
      mount | grep "$VRAM_MOUNTPOINT" 2>/dev/null || true
  else
    echo "[mounted] NO"
    if [[ -d "$VRAM_MOUNTPOINT" ]]; then
      echo "[directory exists] YES (empty mount target)"
    else
      echo "[directory exists] NO"
    fi
  fi
}

do_mount() {
  log "Initializing virtual RAM filesystem at $VRAM_MOUNTPOINT"

  if is_mounted; then
    log "Already mounted — skipping"
    show_status
    return 0
  fi

  mkdir -p "$VRAM_MOUNTPOINT"
  mount -t tmpfs -o "size=$VRAM_SIZE,mode=$VRAM_MODE" tmpfs "$VRAM_MOUNTPOINT"
  log "Mounted tmpfs ($VRAM_SIZE) at $VRAM_MOUNTPOINT"

  IFS=',' read -ra dirs <<< "$VRAM_SUBDIRS"
  for d in "${dirs[@]}"; do
    d="$(echo "$d" | xargs)"
    if [[ -n "$d" ]]; then
      mkdir -p "$VRAM_MOUNTPOINT/$d"
      log "Created subdir: $d"
    fi
  done

  if [[ -n "$VRAM_OWNER" ]]; then
    chown -R "$VRAM_OWNER" "$VRAM_MOUNTPOINT"
    log "Ownership set to $VRAM_OWNER"
  fi

  log "Init-FS virtual RAM ready"
  show_status
}

do_umount() {
  log "Unmounting virtual RAM filesystem at $VRAM_MOUNTPOINT"

  if ! is_mounted; then
    log "Not currently mounted — nothing to do"
    return 0
  fi

  umount "$VRAM_MOUNTPOINT"
  log "Unmounted $VRAM_MOUNTPOINT"

  if [[ -d "$VRAM_MOUNTPOINT" ]]; then
    rmdir "$VRAM_MOUNTPOINT" 2>/dev/null || true
  fi

  log "Cleanup complete"
}

main() {
  need_cmd mount
  need_cmd mountpoint

  local action="${1:-status}"

  case "$action" in
    mount|up)
      require_root
      do_mount
      ;;
    umount|unmount|down)
      require_root
      do_umount
      ;;
    status)
      show_status
      ;;
    plan)
      show_plan
      ;;
    help|-h|--help)
      usage
      ;;
    *)
      usage
      exit 2
      ;;
  esac
}

main "$@"
