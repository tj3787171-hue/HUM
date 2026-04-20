#!/usr/bin/env bash
set -euo pipefail

# Virtual drive helper for the devcontainer.
# cdd 1 -> mount image/device to /mnt/virtual-drive
# cdd 0 -> unmount /mnt/virtual-drive
# Also exposed as subcommands: mount, umount, status.

MOUNTPOINT="${HUM_VDRIVE_MOUNTPOINT:-/mnt/virtual-drive}"
LOOP_HINT="${HUM_VDRIVE_LOOP_HINT:-/tmp/virtual-drive.loop}"

usage() {
  cat <<'EOF'
Usage:
  sudo bash scripts/virtual-drive-access.sh cdd 1 --source <image-or-block-device>
  sudo bash scripts/virtual-drive-access.sh cdd 0
  sudo bash scripts/virtual-drive-access.sh mount --source <image-or-block-device>
  sudo bash scripts/virtual-drive-access.sh umount
  sudo bash scripts/virtual-drive-access.sh status

Options:
  --source PATH     Image file (.iso/.img) or block device path (required for mount/cdd 1)
  --fstype TYPE     Optional filesystem type override for direct device mount
  --mountpoint DIR  Optional mountpoint (default: /mnt/virtual-drive)
  --readonly        Mount read-only (default for image files)
EOF
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "This action requires root." >&2
    exit 1
  fi
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

is_image_path() {
  local source="$1"
  [[ "$source" == *.iso || "$source" == *.img || "$source" == *.img.xz ]]
}

setup_mountpoint() {
  local target="$1"
  mkdir -p "$target"
}

store_loop() {
  local loopdev="$1"
  printf '%s\n' "$loopdev" > "$LOOP_HINT"
}

load_loop() {
  if [[ -f "$LOOP_HINT" ]]; then
    cat "$LOOP_HINT"
  fi
}

clear_loop() {
  rm -f "$LOOP_HINT"
}

mount_source() {
  local source="$1"
  local fstype="$2"
  local target="$3"
  local readonly="$4"

  setup_mountpoint "$target"

  if [[ ! -e "$source" ]]; then
    echo "Source not found: $source" >&2
    exit 1
  fi

  if mountpoint -q "$target"; then
    echo "$target is already mounted."
    return 0
  fi

  if [[ -f "$source" ]] || is_image_path "$source"; then
    require_cmd losetup
    local loopdev
    if [[ "$source" == *.img.xz ]]; then
      echo "Compressed .img.xz files must be decompressed before mounting." >&2
      exit 1
    fi
    loopdev="$(losetup --find --show "$source")"
    store_loop "$loopdev"
    if [[ "$readonly" == "1" ]]; then
      mount -o ro "$loopdev" "$target"
    else
      mount "$loopdev" "$target"
    fi
    echo "Mounted loop device $loopdev at $target"
    return 0
  fi

  # Assume direct block device.
  if [[ "$readonly" == "1" ]]; then
    if [[ -n "$fstype" ]]; then
      mount -o ro -t "$fstype" "$source" "$target"
    else
      mount -o ro "$source" "$target"
    fi
  else
    if [[ -n "$fstype" ]]; then
      mount -t "$fstype" "$source" "$target"
    else
      mount "$source" "$target"
    fi
  fi
  echo "Mounted $source at $target"
}

umount_target() {
  local target="$1"
  if mountpoint -q "$target"; then
    umount "$target"
    echo "Unmounted $target"
  else
    echo "$target is not mounted."
  fi

  local loopdev
  loopdev="$(load_loop || true)"
  if [[ -n "${loopdev:-}" ]]; then
    if losetup "$loopdev" >/dev/null 2>&1; then
      losetup -d "$loopdev" || true
      echo "Detached loop device $loopdev"
    fi
    clear_loop
  fi
}

show_status() {
  local target="$1"
  echo "Mountpoint: $target"
  if mountpoint -q "$target"; then
    echo "Status: mounted"
    findmnt "$target" || true
  else
    echo "Status: not mounted"
  fi
  local loopdev
  loopdev="$(load_loop || true)"
  if [[ -n "${loopdev:-}" ]]; then
    echo "Loop hint: $loopdev"
  fi
}

parse_and_run() {
  local action="${1:-}"
  shift || true

  local source=""
  local fstype=""
  local target="$MOUNTPOINT"
  local readonly="0"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --source)
        source="${2:-}"
        shift 2
        ;;
      --fstype)
        fstype="${2:-}"
        shift 2
        ;;
      --mountpoint)
        target="${2:-}"
        shift 2
        ;;
      --readonly)
        readonly="1"
        shift
        ;;
      *)
        echo "Unknown option: $1" >&2
        usage
        exit 1
        ;;
    esac
  done

  case "$action" in
    cdd)
      local state="${source:-}"
      # cdd receives state as positional, so we emulate:
      # scripts/... cdd 1 --source ...
      ;;
    mount)
      require_root
      require_cmd mount
      if [[ -z "$source" ]]; then
        echo "--source is required for mount" >&2
        exit 1
      fi
      if [[ "$readonly" == "0" && ( -f "$source" || "$source" == *.iso || "$source" == *.img ) ]]; then
        readonly="1"
      fi
      mount_source "$source" "$fstype" "$target" "$readonly"
      ;;
    umount)
      require_root
      require_cmd umount
      umount_target "$target"
      ;;
    status)
      show_status "$target"
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main() {
  if [[ $# -lt 1 ]]; then
    usage
    exit 1
  fi

  # cdd compatibility mode:
  # cdd 1 --source <path>
  # cdd 0
  if [[ "$1" == "cdd" ]]; then
    require_root
    shift
    local state="${1:-}"
    shift || true
    case "$state" in
      1)
        parse_and_run mount "$@"
        ;;
      0)
        parse_and_run umount "$@"
        ;;
      *)
        echo "cdd requires state 0 or 1" >&2
        usage
        exit 1
        ;;
    esac
    exit 0
  fi

  parse_and_run "$@"
}

main "$@"
