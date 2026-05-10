#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# hum-snap-server.sh
#
# Bootstrap a live snapd environment using loop devices and cgroup v2 scopes
# without requiring systemd as PID 1.  Designed for containerised or minimal
# environments (Cursor Cloud VMs, Penguin terminals, Docker containers) where
# PID 1 is *not* systemd but the kernel supports cgroups v2 and squashfs.
#
# What this script does:
#   1. Moves all root-cgroup processes into a "hum-init" child cgroup so the
#      root subtree_control can be unlocked.
#   2. Enables cpu + memory + pids controllers in the root cgroup.
#   3. Creates a snap.hum cgroup scope that snapd can use.
#   4. Prepares /snap mount directory and required /var/lib/snapd layout.
#   5. Starts the snapd daemon directly (no systemctl).
#   6. Provides loop-mount helpers that replicate what snapd normally does
#      via systemd mount units.
#
# Requirements:
#   - Linux kernel with cgroup2 and squashfs support
#   - /dev/loop0–loop9 (or loop-control) available
#   - snapd package installed (apt-get install snapd)
#   - squashfs-tools, squashfuse for the bypass layer
#   - Root privileges (sudo)
# ---------------------------------------------------------------------------

SNAP_MOUNT_DIR="${HUM_SNAP_MOUNT_DIR:-/snap}"
SNAP_CGROUP="${HUM_SNAP_CGROUP:-snap.hum}"
INIT_CGROUP="${HUM_INIT_CGROUP:-hum-init}"
SNAPD_LOG="${HUM_SNAPD_LOG:-/tmp/hum-snapd.log}"
SNAPD_PID_FILE="${HUM_SNAPD_PID_FILE:-/tmp/hum-snapd.pid}"
CGROUP_ROOT="${HUM_CGROUP_ROOT:-/sys/fs/cgroup}"

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

usage() {
  cat <<'EOF'
Usage:
  sudo bash scripts/hum-snap-server.sh up
  sudo bash scripts/hum-snap-server.sh down
  sudo bash scripts/hum-snap-server.sh status
  sudo bash scripts/hum-snap-server.sh attach       [--pid <pid>|<process-name>]
  sudo bash scripts/hum-snap-server.sh loop-mount   <squashfs-file> <name>
  sudo bash scripts/hum-snap-server.sh loop-unmount  <name>
  sudo bash scripts/hum-snap-server.sh loop-list

Subcommands:
  up              Bootstrap cgroup scope + start snapd daemon.
  down            Stop snapd + tear down cgroup scope.
  status          Report loop mounts, cgroup state, snapd health.
  attach          Move a process into the snap cgroup scope.
  loop-mount      Mount a .snap file at /snap/<name> via loop device.
  loop-unmount    Unmount /snap/<name> and detach loop device.
  loop-list       List all loop-mounted snaps.

Environment overrides:
  HUM_SNAP_MOUNT_DIR   Where snaps are mounted      (default: /snap)
  HUM_SNAP_CGROUP      Cgroup scope name             (default: snap.hum)
  HUM_INIT_CGROUP      Child cgroup for init procs   (default: hum-init)
  HUM_SNAPD_LOG        snapd log path                (default: /tmp/hum-snapd.log)
  HUM_SNAPD_PID_FILE   snapd PID file                (default: /tmp/hum-snapd.pid)
  HUM_CGROUP_ROOT      cgroup2 mount root            (default: /sys/fs/cgroup)
EOF
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    return 1
  fi
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "This action requires root.  Re-run with sudo." >&2
    exit 1
  fi
}

log() { echo "[hum-snap-server] $*"; }

# ---------------------------------------------------------------------------
# cgroup helpers – move procs to child so root subtree_control is writable
# ---------------------------------------------------------------------------

cgroup_root="$CGROUP_ROOT"

ensure_child_cgroup() {
  local child="$1"
  local child_path="${cgroup_root}/${child}"

  if [[ -d "$child_path" ]]; then
    return 0
  fi

  mkdir -p "$child_path"
  log "Created cgroup: $child_path"
}

migrate_root_procs() {
  local target="$1"
  local target_path="${cgroup_root}/${target}"

  ensure_child_cgroup "$target"

  local moved=0
  local failed=0

  while read -r pid; do
    [[ -z "$pid" ]] && continue
    if echo "$pid" > "${target_path}/cgroup.procs" 2>/dev/null; then
      moved=$((moved + 1))
    else
      failed=$((failed + 1))
    fi
  done < "${cgroup_root}/cgroup.procs"

  log "Migrated $moved processes to ${target} ($failed could not be moved)"
}

enable_controllers() {
  local controllers="$1"
  local target="${cgroup_root}/cgroup.subtree_control"

  if echo "$controllers" > "$target" 2>/dev/null; then
    log "Enabled controllers: $controllers"
    return 0
  fi

  # Try one at a time
  local ok=0
  for ctrl in $controllers; do
    if echo "$ctrl" > "$target" 2>/dev/null; then
      log "  Enabled: $ctrl"
      ok=$((ok + 1))
    else
      log "  Could not enable: $ctrl (non-fatal)"
    fi
  done

  if [[ "$ok" -eq 0 ]]; then
    log "Warning: no controllers could be enabled"
    return 1
  fi
  return 0
}

# ---------------------------------------------------------------------------
# snapd lifecycle
# ---------------------------------------------------------------------------

prepare_snap_dirs() {
  mkdir -p "$SNAP_MOUNT_DIR"
  mkdir -p /var/lib/snapd/snaps
  mkdir -p /var/lib/snapd/snap
  mkdir -p /var/lib/snapd/mount
  mkdir -p /var/lib/snapd/apparmor/profiles
  mkdir -p /var/lib/snapd/seccomp/bpf
  mkdir -p /var/lib/snapd/inhibit
  mkdir -p /var/lib/snapd/cookie
  mkdir -p /var/lib/snapd/cache
  mkdir -p /var/lib/snapd/sequence
  mkdir -p /run/snapd
  mkdir -p /run/snapd/ns

  # Symlink /snap -> /var/lib/snapd/snap if they differ
  if [[ "$SNAP_MOUNT_DIR" == "/snap" ]] && [[ ! -L /snap ]] && [[ ! -d /snap/snapd ]]; then
    ln -sfn /var/lib/snapd/snap /snap 2>/dev/null || true
  fi
  log "Snap directories prepared"
}

start_snapd() {
  if [[ -f "$SNAPD_PID_FILE" ]]; then
    local old_pid
    old_pid="$(cat "$SNAPD_PID_FILE")"
    if kill -0 "$old_pid" 2>/dev/null; then
      log "snapd already running (PID $old_pid)"
      return 0
    fi
    rm -f "$SNAPD_PID_FILE"
  fi

  if ! need_cmd /usr/lib/snapd/snapd; then
    log "snapd binary not found – install with: sudo apt-get install snapd"
    return 1
  fi

  log "Starting snapd (log: $SNAPD_LOG)..."
  /usr/lib/snapd/snapd >> "$SNAPD_LOG" 2>&1 &
  local pid=$!
  echo "$pid" > "$SNAPD_PID_FILE"

  # Wait for socket
  local waited=0
  while [[ ! -S /run/snapd.socket ]] && [[ "$waited" -lt 15 ]]; do
    sleep 1
    waited=$((waited + 1))
  done

  if [[ -S /run/snapd.socket ]]; then
    log "snapd started (PID $pid), socket ready"
  else
    log "snapd started (PID $pid), socket not yet ready after ${waited}s – check $SNAPD_LOG"
  fi
}

stop_snapd() {
  if [[ -f "$SNAPD_PID_FILE" ]]; then
    local pid
    pid="$(cat "$SNAPD_PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      log "Stopping snapd (PID $pid)..."
      kill "$pid" 2>/dev/null || true
      sleep 1
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
      fi
    fi
    rm -f "$SNAPD_PID_FILE"
  fi
  log "snapd stopped"
}

# ---------------------------------------------------------------------------
# loop-mount: replicate what snapd's systemd mount units do
# ---------------------------------------------------------------------------

loop_mount() {
  local snap_file="$1"
  local name="$2"
  local mount_target="${SNAP_MOUNT_DIR}/${name}"

  if [[ ! -f "$snap_file" ]]; then
    echo "Error: file not found: $snap_file" >&2
    return 1
  fi

  if mountpoint -q "$mount_target" 2>/dev/null; then
    log "Already mounted: $mount_target"
    return 0
  fi

  local loop_dev
  loop_dev="$(losetup --find --show "$snap_file")"
  log "Attached $snap_file -> $loop_dev"

  mkdir -p "$mount_target"
  mount -t squashfs -o ro "$loop_dev" "$mount_target"
  log "Mounted: $mount_target (via $loop_dev)"
}

loop_unmount() {
  local name="$1"
  local mount_target="${SNAP_MOUNT_DIR}/${name}"

  if ! mountpoint -q "$mount_target" 2>/dev/null; then
    log "Not mounted: $mount_target"
    return 0
  fi

  # Find the loop device backing this mount
  local loop_dev
  loop_dev="$(mount | grep "$mount_target" | awk '{print $1}')" || true

  umount "$mount_target"
  rmdir "$mount_target" 2>/dev/null || true

  if [[ -n "$loop_dev" ]] && [[ "$loop_dev" == /dev/loop* ]]; then
    losetup -d "$loop_dev" 2>/dev/null || true
    log "Detached: $loop_dev"
  fi
  log "Unmounted: $mount_target"
}

loop_list() {
  echo "=== Loop-mounted snaps at ${SNAP_MOUNT_DIR} ==="
  local found=0
  while read -r line; do
    if echo "$line" | grep -q "$SNAP_MOUNT_DIR"; then
      echo "$line"
      found=1
    fi
  done < <(mount)

  if [[ "$found" -eq 0 ]]; then
    echo "(none)"
  fi

  echo ""
  echo "=== Active loop devices ==="
  losetup -a 2>/dev/null || echo "(none)"
}

# ---------------------------------------------------------------------------
# attach: move a running process into the snap cgroup scope
# ---------------------------------------------------------------------------

is_pid() {
  [[ "$1" =~ ^[0-9]+$ ]]
}

target_cgroup_path() {
  printf '%s/%s\n' "$cgroup_root" "$SNAP_CGROUP"
}

resolve_attach_pids() {
  local target="$1"
  shift || true

  if [[ "$target" == "--pid" ]]; then
    [[ $# -lt 1 ]] && { echo "Usage: attach --pid <pid>" >&2; return 1; }
    is_pid "$1" || { echo "Error: invalid pid: $1" >&2; return 1; }
    printf '%s\n' "$1"
    return 0
  fi

  if is_pid "$target"; then
    printf '%s\n' "$target"
    return 0
  fi

  need_cmd pgrep || return 1
  pgrep -x "$target" 2>/dev/null || pgrep -f "(^|/)$target([[:space:]]|$)" 2>/dev/null
}

attach_process() {
  local target="${1:-}"
  [[ -z "$target" ]] && { echo "Usage: attach [--pid <pid>|<process-name>]" >&2; return 1; }

  if [[ "$cgroup_root" == "/sys/fs/cgroup" ]]; then
    require_root
  fi

  local target_path
  target_path="$(target_cgroup_path)"
  if [[ ! -d "$target_path" ]]; then
    echo "Error: snap cgroup does not exist: $target_path" >&2
    echo "Run first: sudo bash scripts/hum-snap-server.sh up" >&2
    return 1
  fi
  if [[ ! -w "${target_path}/cgroup.procs" ]]; then
    echo "Error: cgroup.procs is not writable: ${target_path}/cgroup.procs" >&2
    return 1
  fi

  local pids
  if ! pids="$(resolve_attach_pids "$@")" || [[ -z "$pids" ]]; then
    echo "Error: no matching process found: $target" >&2
    return 1
  fi

  local attached=0
  local failed=0
  local pid
  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    if ! is_pid "$pid"; then
      log "Skipping non-pid match: $pid"
      failed=$((failed + 1))
      continue
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      log "Skipping stale pid: $pid"
      failed=$((failed + 1))
      continue
    fi
    if printf '%s\n' "$pid" >> "${target_path}/cgroup.procs" 2>/dev/null; then
      echo "attached pid: $pid -> $target_path"
      attached=$((attached + 1))
    else
      log "Could not attach pid: $pid"
      failed=$((failed + 1))
    fi
  done <<< "$pids"

  if [[ "$attached" -eq 0 ]]; then
    echo "Error: no processes were attached ($failed failed)" >&2
    return 1
  fi

  log "Attached $attached process(es) to $target_path ($failed failed)"
}

# ---------------------------------------------------------------------------
# up / down / status
# ---------------------------------------------------------------------------

up() {
  require_root

  log "=== Bootstrapping snap environment ==="
  echo ""

  # Step 1: cgroup setup
  log "Step 1/4: cgroup v2 setup"
  local cg_type
  cg_type="$(stat -fc %T /sys/fs/cgroup/ 2>/dev/null || echo unknown)"
  if [[ "$cg_type" != "cgroup2fs" ]]; then
    log "Warning: /sys/fs/cgroup is $cg_type, not cgroup2fs. Proceeding anyway."
  fi

  # Move root procs to child so subtree_control becomes writable
  migrate_root_procs "$INIT_CGROUP"
  enable_controllers "+cpu +memory +pids" || true

  # Create snap scope
  ensure_child_cgroup "$SNAP_CGROUP"
  log "Snap cgroup scope: ${cgroup_root}/${SNAP_CGROUP}"
  echo ""

  # Step 2: verify loop + squashfs
  log "Step 2/4: Loop device + squashfs check"
  if [[ -e /dev/loop-control ]]; then
    log "  loop-control: present"
  else
    log "  loop-control: MISSING (may need mknod)"
  fi
  if grep -q squashfs /proc/filesystems 2>/dev/null; then
    log "  squashfs: kernel support present"
  else
    log "  squashfs: NOT in /proc/filesystems (mount via loop may fail)"
  fi
  echo ""

  # Step 3: snap directories
  log "Step 3/4: Preparing snap directories"
  prepare_snap_dirs
  echo ""

  # Step 4: start snapd
  log "Step 4/4: Starting snapd"
  start_snapd
  echo ""

  log "=== Bootstrap complete ==="
  echo ""
  status_report
}

down() {
  require_root

  log "=== Tearing down snap environment ==="

  # Unmount all loop-mounted snaps
  local any_unmounted=0
  while read -r line; do
    local mnt
    mnt="$(echo "$line" | awk '{print $3}')"
    if [[ "$mnt" == ${SNAP_MOUNT_DIR}/* ]]; then
      local name
      name="$(basename "$mnt")"
      loop_unmount "$name"
      any_unmounted=1
    fi
  done < <(mount | grep "$SNAP_MOUNT_DIR" || true)

  if [[ "$any_unmounted" -eq 0 ]]; then
    log "No loop-mounted snaps to clean up"
  fi

  stop_snapd

  # Remove snap cgroup scope
  if [[ -d "${cgroup_root}/${SNAP_CGROUP}" ]]; then
    if rmdir "${cgroup_root}/${SNAP_CGROUP}" 2>/dev/null; then
      log "Removed cgroup scope: $SNAP_CGROUP"
    else
      log "Could not remove cgroup scope (may have active processes)"
    fi
  fi

  log "=== Teardown complete ==="
}

status_report() {
  echo "=== HUM snap server status ==="
  echo ""

  echo "[cgroup v2]"
  echo "  type:               $(stat -fc %T "$cgroup_root" 2>/dev/null || echo unknown)"
  echo "  subtree_control:    $(cat "${cgroup_root}/cgroup.subtree_control" 2>/dev/null || echo '(empty)')"
  echo "  init cgroup:        ${cgroup_root}/${INIT_CGROUP} $(test -d "${cgroup_root}/${INIT_CGROUP}" && echo EXISTS || echo MISSING)"
  echo "  snap cgroup:        ${cgroup_root}/${SNAP_CGROUP} $(test -d "${cgroup_root}/${SNAP_CGROUP}" && echo EXISTS || echo MISSING)"
  if [[ -d "${cgroup_root}/${SNAP_CGROUP}" ]]; then
    echo "  snap cgroup controllers: $(cat "${cgroup_root}/${SNAP_CGROUP}/cgroup.controllers" 2>/dev/null || echo none)"
  fi
  echo ""

  echo "[loop devices]"
  local loop_info
  loop_info="$(losetup -a 2>/dev/null)"
  if [[ -n "$loop_info" ]]; then
    while IFS= read -r li; do echo "  $li"; done <<< "$loop_info"
  else
    echo "  (no active loop devices)"
  fi
  echo ""

  echo "[snap mounts]"
  local snap_mounts
  snap_mounts="$(mount | grep "${SNAP_MOUNT_DIR}" 2>/dev/null || true)"
  if [[ -n "$snap_mounts" ]]; then
    while IFS= read -r sm; do echo "  $sm"; done <<< "$snap_mounts"
  else
    echo "  (no snap mounts)"
  fi
  echo ""

  echo "[snapd]"
  if [[ -f "$SNAPD_PID_FILE" ]]; then
    local pid
    pid="$(cat "$SNAPD_PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "  status:  running (PID $pid)"
    else
      echo "  status:  dead (stale PID $pid)"
    fi
  else
    echo "  status:  not started"
  fi
  echo "  socket:  $(test -S /run/snapd.socket && echo READY || echo 'not ready')"
  echo "  log:     $SNAPD_LOG"
  echo ""

  echo "[kernel]"
  echo "  squashfs:   $(grep -q squashfs /proc/filesystems && echo supported || echo 'NOT in /proc/filesystems')"
  echo "  loop-ctl:   $(test -e /dev/loop-control && echo present || echo missing)"
  local avail_loops
  avail_loops=0
  for i in $(seq 0 9); do
    if [[ -b "/dev/loop${i}" ]] && ! losetup "/dev/loop${i}" >/dev/null 2>&1; then
      avail_loops=$((avail_loops + 1))
    fi
  done
  local total_loops
  total_loops="$(find /dev -maxdepth 1 -name 'loop[0-9]*' -type b 2>/dev/null | wc -l)"
  echo "  available loops: $avail_loops / $total_loops"
}

# ---------------------------------------------------------------------------
# main dispatch
# ---------------------------------------------------------------------------

main() {
  local action="${1:-}"
  case "$action" in
    up)
      up
      ;;
    down)
      down
      ;;
    status)
      status_report
      ;;
    attach)
      [[ $# -lt 2 ]] && { echo "Usage: attach [--pid <pid>|<process-name>]" >&2; exit 1; }
      shift
      attach_process "$@"
      ;;
    loop-mount)
      require_root
      [[ $# -lt 3 ]] && { echo "Usage: loop-mount <snap-file> <name>" >&2; exit 1; }
      loop_mount "$2" "$3"
      ;;
    loop-unmount)
      require_root
      [[ $# -lt 2 ]] && { echo "Usage: loop-unmount <name>" >&2; exit 1; }
      loop_unmount "$2"
      ;;
    loop-list)
      loop_list
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
