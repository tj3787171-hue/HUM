#!/bin/sh
# /etc/ Structure Protection and Recovery
# Prevents sabotage of /etc/ directories (renaming, moving, corrupting).
# Maintains essential /etc/ structure throughout installation.
set -e

LOG="/tmp/etc-structure-protect.log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

log "/ETC STRUCTURE PROTECTION"

# Essential /etc/ directories that must exist
ETC_DIRS="
apt apt/sources.list.d apt/apt.conf.d apt/trusted.gpg.d apt/preferences.d
dpkg dpkg/dpkg.cfg.d
network network/interfaces.d
ssh ssh/sshd_config.d
default
init.d
systemd systemd/system
security security/limits.d
pam.d
ld.so.conf.d
modprobe.d
sysctl.d
resolv.conf.d
"

# Essential /etc/ files that must exist
ETC_FILES="
resolv.conf
hostname
hosts
passwd
shadow
group
fstab
"

# Phase 1: Snapshot /etc structure
snapshot_etc() {
  log "Phase 1: Snapshotting /etc structure"
  local snap="/tmp/etc-snapshot"
  mkdir -p "$snap"

  find /etc -maxdepth 2 -type d 2>/dev/null | sort > "$snap/dirs.txt"
  find /etc -maxdepth 2 -type f -name '*.conf' -o -name '*.list' -o -name '*.cfg' 2>/dev/null | sort > "$snap/configs.txt"

  # Save critical files
  for f in $ETC_FILES; do
    if [ -f "/etc/$f" ]; then
      cp -a "/etc/$f" "$snap/$(echo "$f" | tr '/' '_')" 2>/dev/null || true
    fi
  done

  # Save APT sources
  cp -a /etc/apt/sources.list "$snap/sources.list" 2>/dev/null || true

  # Checksum all files for integrity monitoring
  find /etc -maxdepth 2 -type f 2>/dev/null | xargs md5sum 2>/dev/null > "$snap/checksums.txt" || true

  log "  Snapshot saved to $snap"
  log "  Directories: $(wc -l < "$snap/dirs.txt")"
  log "  Config files: $(wc -l < "$snap/configs.txt")"
}

# Phase 2: Ensure essential directories exist
ensure_dirs() {
  log "Phase 2: Ensuring essential /etc directories"

  for d in $ETC_DIRS; do
    local path="/etc/$d"
    if [ ! -d "$path" ]; then
      mkdir -p "$path"
      log "  Created: $path"
    fi
  done

  # Also ensure /target/etc/ if present
  if [ -d /target ]; then
    for d in $ETC_DIRS; do
      local path="/target/etc/$d"
      if [ ! -d "$path" ]; then
        mkdir -p "$path" 2>/dev/null || true
      fi
    done
    log "  /target/etc/ directories ensured"
  fi
}

# Phase 3: Protect critical files from deletion/corruption
protect_critical() {
  log "Phase 3: Protecting critical files"

  for f in $ETC_FILES; do
    local path="/etc/$f"
    if [ -f "$path" ]; then
      chattr +i "$path" 2>/dev/null || true
      log "  Protected: $path"
    fi
  done

  # Protect APT infrastructure
  for f in /etc/apt/sources.list /etc/apt/apt.conf.d/99force-network /etc/apt/apt.conf.d/01proxy; do
    if [ -f "$f" ]; then
      chattr +i "$f" 2>/dev/null || true
    fi
  done
}

# Phase 4: Detect and revert tampering
detect_tampering() {
  log "Phase 4: Detecting tampering"
  local snap="/tmp/etc-snapshot"
  local tampered=0

  if [ ! -f "$snap/checksums.txt" ]; then
    log "  No snapshot found. Run '$0 snapshot' first."
    return 1
  fi

  md5sum -c "$snap/checksums.txt" 2>/dev/null | grep -v ': OK' | while read -r line; do
    log "  TAMPERED: $line"
    tampered=1
  done

  # Check for missing directories
  for d in $ETC_DIRS; do
    if [ ! -d "/etc/$d" ]; then
      log "  MISSING: /etc/$d"
      tampered=1
    fi
  done

  # Check for missing critical files
  for f in $ETC_FILES; do
    if [ ! -f "/etc/$f" ]; then
      log "  MISSING FILE: /etc/$f"
      tampered=1
    fi
  done

  if [ "$tampered" -eq 0 ]; then
    log "  No tampering detected"
  fi
}

# Phase 5: Restore from snapshot
restore_from_snapshot() {
  log "Phase 5: Restoring from snapshot"
  local snap="/tmp/etc-snapshot"

  if [ ! -d "$snap" ]; then
    log "  No snapshot found. Cannot restore."
    return 1
  fi

  # Unlock protected files first
  for f in $ETC_FILES; do
    chattr -i "/etc/$f" 2>/dev/null || true
  done

  # Restore critical files
  for f in $ETC_FILES; do
    local safe_name
    safe_name="$(echo "$f" | tr '/' '_')"
    if [ -f "$snap/$safe_name" ]; then
      cp -a "$snap/$safe_name" "/etc/$f"
      log "  Restored: /etc/$f"
    fi
  done

  # Restore APT sources
  if [ -f "$snap/sources.list" ]; then
    cp -a "$snap/sources.list" /etc/apt/sources.list
    log "  Restored: /etc/apt/sources.list"
  fi

  # Re-ensure directories
  ensure_dirs

  # Re-protect
  protect_critical

  log "  Restoration complete"
}

# Phase 6: Watch for changes (background daemon)
watch_etc() {
  log "Phase 6: Starting /etc watchdog"

  while true; do
    # Check essential directories
    for d in $ETC_DIRS; do
      if [ ! -d "/etc/$d" ]; then
        log "  ALERT: /etc/$d disappeared! Recreating..."
        mkdir -p "/etc/$d"
      fi
    done

    # Check essential files
    for f in $ETC_FILES; do
      if [ ! -f "/etc/$f" ]; then
        log "  ALERT: /etc/$f was deleted! Restoring..."
        local snap="/tmp/etc-snapshot"
        local safe_name
        safe_name="$(echo "$f" | tr '/' '_')"
        if [ -f "$snap/$safe_name" ]; then
          cp -a "$snap/$safe_name" "/etc/$f"
          chattr +i "/etc/$f" 2>/dev/null || true
          log "  Restored: /etc/$f"
        fi
      fi
    done

    # Check APT sources haven't been sabotaged
    if [ -f /etc/apt/sources.list ]; then
      if ! grep -q 'kali\|debian' /etc/apt/sources.list 2>/dev/null; then
        log "  ALERT: APT sources.list may be corrupted"
        local snap="/tmp/etc-snapshot"
        if [ -f "$snap/sources.list" ]; then
          chattr -i /etc/apt/sources.list 2>/dev/null || true
          cp -a "$snap/sources.list" /etc/apt/sources.list
          chattr +i /etc/apt/sources.list 2>/dev/null || true
          log "  Restored APT sources"
        fi
      fi
    fi

    sleep 10
  done
}

main() {
  local cmd="${1:-all}"
  case "$cmd" in
    all)
      snapshot_etc
      ensure_dirs
      protect_critical
      log ""
      log "/etc protection setup complete."
      log "Run '$0 watch' in background to maintain protection."
      log "Run '$0 detect' to check for tampering."
      ;;
    snapshot) snapshot_etc ;;
    ensure) ensure_dirs ;;
    protect) protect_critical ;;
    detect) detect_tampering ;;
    restore) restore_from_snapshot ;;
    watch) watch_etc ;;
    *)
      echo "Usage: $0 {all|snapshot|ensure|protect|detect|restore|watch}"
      exit 1
      ;;
  esac
}

main "$@"
