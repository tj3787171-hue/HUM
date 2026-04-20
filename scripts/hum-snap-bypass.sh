#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# hum-snap-bypass.sh
#
# Work with snap packages (.snap files are squashfs images, typically
# xz-compressed) without requiring snapd, systemd, or cgroup controllers.
#
# snapd normally manages mounts, cgroup scopes, and AppArmor profiles for
# every snap.  In environments where those subsystems are unavailable
# (containers, Chromebook Penguin terminals, minimal VMs) this script lets
# you extract, FUSE-mount, inspect, and run binaries directly from .snap
# files using only squashfs-tools / squashfuse / xz-utils.
# ---------------------------------------------------------------------------

HUM_SNAP_EXTRACT_ROOT="${HUM_SNAP_EXTRACT_ROOT:-/tmp/hum-snap}"
HUM_SNAP_MOUNT_ROOT="${HUM_SNAP_MOUNT_ROOT:-/tmp/hum-snap-mnt}"

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

usage() {
  cat <<'EOF'
Usage:
  hum-snap-bypass.sh extract  <snap-file> [dest-dir]
  hum-snap-bypass.sh mount    <snap-file> [mountpoint]
  hum-snap-bypass.sh unmount  <mountpoint>
  hum-snap-bypass.sh info     <snap-file>
  hum-snap-bypass.sh run      <snap-file> <command> [args...]
  hum-snap-bypass.sh list
  hum-snap-bypass.sh deps

Subcommands:
  extract   Decompress a .snap (squashfs+xz) into a plain directory tree.
  mount     FUSE-mount a .snap without snapd (requires squashfuse).
  unmount   Unmount a previously FUSE-mounted snap.
  info      Print snap metadata: compression, size, squashfs details.
  run       Extract (if needed) and exec a binary from the snap tree.
  list      Show active FUSE-mounted snaps.
  deps      Check / report required host tools.

Environment overrides:
  HUM_SNAP_EXTRACT_ROOT   Base directory for extracted trees
                          (default: /tmp/hum-snap)
  HUM_SNAP_MOUNT_ROOT     Base directory for FUSE mountpoints
                          (default: /tmp/hum-snap-mnt)
EOF
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    echo "Install it with:  sudo apt-get install $2" >&2
    return 1
  fi
}

require_snap_file() {
  local snap="$1"
  if [[ ! -f "$snap" ]]; then
    echo "Error: file not found: $snap" >&2
    exit 1
  fi
}

# Derive a stable directory name from a snap file path.
snap_slug() {
  local snap
  snap="$(realpath "$1")"
  local base
  base="$(basename "$snap" .snap)"
  local hash
  hash="$(printf '%s' "$snap" | sha256sum | cut -c1-12)"
  printf '%s' "${base}-${hash}"
}

# ---------------------------------------------------------------------------
# deps – report / verify required tooling
# ---------------------------------------------------------------------------

cmd_deps() {
  local ok=0
  echo "=== hum-snap-bypass dependency check ==="
  for pair in \
    "unsquashfs:squashfs-tools" \
    "squashfuse:squashfuse" \
    "xz:xz-utils" \
    "file:file" \
    "fusermount:fuse3"; do
    local cmd="${pair%%:*}"
    local pkg="${pair##*:}"
    if command -v "$cmd" >/dev/null 2>&1; then
      printf '  %-14s  OK   (%s)\n' "$cmd" "$(command -v "$cmd")"
    else
      printf '  %-14s  MISSING  (apt-get install %s)\n' "$cmd" "$pkg"
      ok=1
    fi
  done
  if [[ "$ok" -ne 0 ]]; then
    echo
    echo "Install all missing tools:"
    echo "  sudo apt-get install -y squashfs-tools squashfuse xz-utils file fuse3"
  fi
  return "$ok"
}

# ---------------------------------------------------------------------------
# info – print snap / squashfs metadata
# ---------------------------------------------------------------------------

cmd_info() {
  local snap="$1"
  require_snap_file "$snap"
  need_cmd unsquashfs squashfs-tools || exit 1
  need_cmd file file || exit 1

  echo "=== snap file info ==="
  echo "path:        $(realpath "$snap")"
  echo "size:        $(stat --printf='%s' "$snap") bytes"
  echo "file type:   $(file -b "$snap")"
  echo

  echo "=== squashfs superblock ==="
  unsquashfs -s "$snap" 2>/dev/null || true
  echo

  # If the snap contains snap/manifest.yaml or meta/snap.yaml, show it.
  local yaml
  for candidate in meta/snap.yaml snap/manifest.yaml; do
    yaml="$(unsquashfs -cat "$snap" "$candidate" 2>/dev/null)" && break
  done
  if [[ -n "${yaml:-}" ]]; then
    echo "=== snap metadata (${candidate}) ==="
    echo "$yaml"
  fi
}

# ---------------------------------------------------------------------------
# extract – unsquashfs a .snap into a directory
# ---------------------------------------------------------------------------

cmd_extract() {
  local snap="$1"
  local dest="${2:-}"
  require_snap_file "$snap"
  need_cmd unsquashfs squashfs-tools || exit 1

  if [[ -z "$dest" ]]; then
    dest="${HUM_SNAP_EXTRACT_ROOT}/$(snap_slug "$snap")"
  fi

  if [[ -d "$dest" ]]; then
    echo "Destination already exists: $dest"
    echo "Re-extracting (overwriting)..."
    rm -rf "$dest"
  fi

  mkdir -p "$(dirname "$dest")"
  echo "Extracting: $snap"
  echo "       to:  $dest"
  unsquashfs -d "$dest" -f "$snap"
  echo
  echo "Done. Tree root: $dest"
}

# ---------------------------------------------------------------------------
# mount – FUSE-mount without snapd
# ---------------------------------------------------------------------------

cmd_mount() {
  local snap="$1"
  local mountpoint="${2:-}"
  require_snap_file "$snap"
  need_cmd squashfuse squashfuse || exit 1

  if [[ -z "$mountpoint" ]]; then
    mountpoint="${HUM_SNAP_MOUNT_ROOT}/$(snap_slug "$snap")"
  fi

  if mountpoint -q "$mountpoint" 2>/dev/null; then
    echo "Already mounted at: $mountpoint"
    return 0
  fi

  mkdir -p "$mountpoint"
  echo "FUSE-mounting: $snap"
  echo "           at: $mountpoint"
  squashfuse "$snap" "$mountpoint"
  echo "Mounted. Browse with:  ls $mountpoint"
}

# ---------------------------------------------------------------------------
# unmount
# ---------------------------------------------------------------------------

cmd_unmount() {
  local mountpoint="$1"
  if ! mountpoint -q "$mountpoint" 2>/dev/null; then
    echo "Not a mountpoint: $mountpoint" >&2
    exit 1
  fi

  if command -v fusermount >/dev/null 2>&1; then
    fusermount -u "$mountpoint"
  elif command -v fusermount3 >/dev/null 2>&1; then
    fusermount3 -u "$mountpoint"
  else
    umount "$mountpoint"
  fi
  echo "Unmounted: $mountpoint"
  rmdir "$mountpoint" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# list – show FUSE-mounted snaps
# ---------------------------------------------------------------------------

cmd_list() {
  echo "=== FUSE-mounted squashfs (snap) filesystems ==="
  if ! mount | grep -E 'squashfuse|fuse.*squash' 2>/dev/null; then
    echo "(none)"
  fi
}

# ---------------------------------------------------------------------------
# run – extract-then-exec a command from a snap tree
# ---------------------------------------------------------------------------

cmd_run() {
  local snap="$1"; shift
  local cmd="$1"; shift
  require_snap_file "$snap"
  need_cmd unsquashfs squashfs-tools || exit 1

  local tree
  tree="${HUM_SNAP_EXTRACT_ROOT}/$(snap_slug "$snap")"

  if [[ ! -d "$tree" ]]; then
    echo "Extracting snap for first run..." >&2
    cmd_extract "$snap" "$tree" >&2
  fi

  # Resolve the binary: try exact path, then common snap binary locations.
  local bin=""
  for candidate in \
    "${tree}/${cmd}" \
    "${tree}/bin/${cmd}" \
    "${tree}/usr/bin/${cmd}" \
    "${tree}/usr/local/bin/${cmd}" \
    "${tree}/snap/${cmd}" \
    "${tree}/command-${cmd}.wrapper"; do
    if [[ -x "$candidate" ]]; then
      bin="$candidate"
      break
    fi
  done

  if [[ -z "$bin" ]]; then
    echo "Error: could not find executable '$cmd' in snap tree: $tree" >&2
    echo "Available executables:" >&2
    find "$tree" -maxdepth 3 -type f -executable 2>/dev/null | head -20 >&2
    exit 1
  fi

  # Provide a minimal environment that snaps typically expect.
  export SNAP="$tree"
  export SNAP_COMMON="${tree}/common"
  export SNAP_DATA="${tree}/data"
  export SNAP_USER_COMMON="${HOME}/snap/hum-bypass/common"
  export SNAP_USER_DATA="${HOME}/snap/hum-bypass/current"
  mkdir -p "$SNAP_USER_COMMON" "$SNAP_USER_DATA" 2>/dev/null || true

  # Prepend snap's own paths so its bundled libraries are found.
  export PATH="${tree}/usr/bin:${tree}/bin:${tree}/usr/sbin:${tree}/sbin:${PATH}"
  export LD_LIBRARY_PATH="${tree}/usr/lib:${tree}/usr/lib/x86_64-linux-gnu:${tree}/lib:${tree}/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"

  exec "$bin" "$@"
}

# ---------------------------------------------------------------------------
# main dispatch
# ---------------------------------------------------------------------------

main() {
  local action="${1:-}"
  case "$action" in
    extract)
      [[ $# -lt 2 ]] && { usage; exit 1; }
      cmd_extract "$2" "${3:-}"
      ;;
    mount)
      [[ $# -lt 2 ]] && { usage; exit 1; }
      cmd_mount "$2" "${3:-}"
      ;;
    unmount)
      [[ $# -lt 2 ]] && { usage; exit 1; }
      cmd_unmount "$2"
      ;;
    info)
      [[ $# -lt 2 ]] && { usage; exit 1; }
      cmd_info "$2"
      ;;
    run)
      [[ $# -lt 3 ]] && { usage; exit 1; }
      shift
      cmd_run "$@"
      ;;
    list)
      cmd_list
      ;;
    deps)
      cmd_deps
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
