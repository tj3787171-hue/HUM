#!/bin/sh
# APT Persistence System
# Prevents APT tool elimination during hostile installation environments.
# Pre-installs tools to /target, creates bind mounts, immutable protection.
set -e

LOG="/tmp/apt-persistence.log"
HUM_SERVER="${HUM_SERVER:-192.168.68.52}"
HUM_PORT="${HUM_PORT:-8080}"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

log "APT PERSISTENCE DEFENSE"

# Phase 1: Snapshot current APT state
snapshot_apt() {
  log "Phase 1: Snapshotting APT state"
  local snap_dir="/tmp/apt-persistence-snapshot"
  mkdir -p "$snap_dir"

  # Save essential binaries
  for bin in apt apt-get apt-cache dpkg dpkg-query apt-key apt-mark; do
    local path
    path="$(command -v "$bin" 2>/dev/null || true)"
    if [ -n "$path" ] && [ -f "$path" ]; then
      cp -a "$path" "$snap_dir/"
      log "  Saved: $path"
    fi
  done

  # Save APT libraries
  for lib in /usr/lib/apt /usr/lib/dpkg /usr/lib/x86_64-linux-gnu/libapt*; do
    if [ -e "$lib" ]; then
      cp -a "$lib" "$snap_dir/" 2>/dev/null || true
    fi
  done

  # Save config
  tar cf "$snap_dir/apt-config.tar" /etc/apt/ 2>/dev/null || true
  tar cf "$snap_dir/dpkg-config.tar" /etc/dpkg/ /var/lib/dpkg/ 2>/dev/null || true

  log "  Snapshot saved to $snap_dir"
}

# Phase 2: Protect APT binaries with immutable flags
protect_apt() {
  log "Phase 2: Protecting APT binaries"

  for bin in /usr/bin/apt /usr/bin/apt-get /usr/bin/apt-cache /usr/bin/dpkg /usr/bin/dpkg-query; do
    if [ -f "$bin" ]; then
      chattr +i "$bin" 2>/dev/null || true
      log "  Immutable: $bin"
    fi
  done

  # Protect APT directories
  for dir in /etc/apt /var/lib/apt /var/cache/apt /var/lib/dpkg; do
    if [ -d "$dir" ]; then
      chattr +i "$dir" 2>/dev/null || true
    fi
  done

  log "  APT binaries and directories protected"
}

# Phase 3: Create recovery bind mounts
create_recovery_mounts() {
  log "Phase 3: Creating recovery bind mounts"
  local recover_dir="/tmp/apt-recovery"
  mkdir -p "$recover_dir"

  # Copy essential tools to recovery location
  for bin in apt apt-get dpkg curl wget; do
    local path
    path="$(command -v "$bin" 2>/dev/null || true)"
    if [ -n "$path" ] && [ -f "$path" ]; then
      cp -a "$path" "$recover_dir/"
    fi
  done

  # Store recovery in tmpfs so it survives fs manipulation
  mount -t tmpfs -o size=100M tmpfs "$recover_dir" 2>/dev/null || true
  for bin in apt apt-get dpkg curl wget; do
    local path
    path="$(command -v "$bin" 2>/dev/null || true)"
    if [ -n "$path" ] && [ -f "$path" ]; then
      cp -a "$path" "$recover_dir/"
    fi
  done

  log "  Recovery tools at $recover_dir"
}

# Phase 4: Watch for APT removal attempts
watch_apt() {
  log "Phase 4: Starting APT watchdog"
  local snap_dir="/tmp/apt-persistence-snapshot"

  while true; do
    for bin in apt apt-get dpkg; do
      if ! command -v "$bin" >/dev/null 2>&1; then
        log "  ALERT: $bin was removed! Restoring..."
        if [ -f "$snap_dir/$bin" ]; then
          cp -a "$snap_dir/$bin" "/usr/bin/$bin"
          chmod +x "/usr/bin/$bin"
          chattr +i "/usr/bin/$bin" 2>/dev/null || true
          log "  Restored: $bin"
        fi
      fi
    done

    # Check APT config integrity
    if [ ! -d /etc/apt ]; then
      log "  ALERT: /etc/apt was removed! Restoring..."
      mkdir -p /etc/apt/sources.list.d /etc/apt/apt.conf.d
      if [ -f "$snap_dir/apt-config.tar" ]; then
        tar xf "$snap_dir/apt-config.tar" -C / 2>/dev/null || true
        log "  Restored: /etc/apt"
      fi
    fi

    sleep 5
  done
}

# Phase 5: Ensure target has APT
protect_target() {
  log "Phase 5: Protecting /target APT"

  if [ -d /target ]; then
    for bin in apt apt-get apt-cache dpkg dpkg-query; do
      local src="/usr/bin/$bin"
      local dst="/target/usr/bin/$bin"
      if [ -f "$src" ] && [ ! -f "$dst" ]; then
        mkdir -p /target/usr/bin
        cp -a "$src" "$dst"
        log "  Copied $bin to /target"
      fi
    done

    # Ensure APT config exists in target
    mkdir -p /target/etc/apt/sources.list.d /target/etc/apt/apt.conf.d
    mkdir -p /target/var/lib/apt/lists /target/var/cache/apt/archives

    # Set DNS in target
    cat > /target/etc/resolv.conf <<'DNS'
nameserver 209.18.47.61
nameserver 209.18.47.62
DNS

    # Disable CDROM in target
    if [ -f /target/etc/apt/sources.list ]; then
      sed -i 's/^deb cdrom:/# deb cdrom:/' /target/etc/apt/sources.list
    fi
    echo 'APT::CDROM::NoMount "true";' > /target/etc/apt/apt.conf.d/99no-cdrom

    log "  /target APT protected"
  fi
}

main() {
  local cmd="${1:-all}"
  case "$cmd" in
    all)
      snapshot_apt
      protect_apt
      create_recovery_mounts
      protect_target
      log "APT persistence setup complete."
      log "Run '$0 watch' in background to maintain protection."
      ;;
    snapshot) snapshot_apt ;;
    protect) protect_apt ;;
    mounts) create_recovery_mounts ;;
    watch) watch_apt ;;
    target) protect_target ;;
    *)
      echo "Usage: $0 {all|snapshot|protect|mounts|watch|target}"
      exit 1
      ;;
  esac
}

main "$@"
