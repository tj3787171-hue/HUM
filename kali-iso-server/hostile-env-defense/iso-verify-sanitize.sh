#!/bin/sh
# Live ISO Verification and Sanitization
# Verifies Kali/Debian ISO integrity and sanitizes hostile modifications.
# Checks for tool elimination, /etc/ sabotage, and mirror corruption.
set -e

LOG="/tmp/iso-verify-sanitize.log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

log "ISO VERIFICATION & SANITIZATION"

# Phase 1: Verify ISO mount integrity
verify_iso_mount() {
  log "Phase 1: Verifying ISO mount points"

  for mount_point in /cdrom /media/cdrom /media/cdrom0 /mnt; do
    if mountpoint -q "$mount_point" 2>/dev/null; then
      log "  Mounted: $mount_point"
      log "    Type: $(findmnt -n -o FSTYPE "$mount_point" 2>/dev/null || echo 'unknown')"
      log "    Source: $(findmnt -n -o SOURCE "$mount_point" 2>/dev/null || echo 'unknown')"
      log "    Size: $(df -h "$mount_point" 2>/dev/null | tail -1 | awk '{print $2}' || echo 'unknown')"
    else
      log "  Not mounted: $mount_point"
    fi
  done
}

# Phase 2: Check package pool integrity
check_pool_integrity() {
  log "Phase 2: Checking package pool integrity"
  local corrupt=0

  for mount_point in /cdrom /media/cdrom; do
    local pool="$mount_point/pool"
    if [ -d "$pool" ]; then
      log "  Scanning pool: $pool"
      find "$pool" -name '*.deb' -type f 2>/dev/null | while read -r deb; do
        if ! dpkg-deb -I "$deb" >/dev/null 2>&1; then
          log "  CORRUPT: $deb"
          corrupt=$((corrupt + 1))
        fi
      done
      local total
      total="$(find "$pool" -name '*.deb' -type f 2>/dev/null | wc -l)"
      log "  Total packages: $total"
    fi
  done

  if [ "$corrupt" -gt 0 ]; then
    log "  WARNING: $corrupt corrupt package(s) found"
    return 1
  else
    log "  All packages intact (or pool not mounted)"
    return 0
  fi
}

# Phase 3: Verify essential tools still exist
verify_tools() {
  log "Phase 3: Verifying essential tools"
  local missing=0

  for tool in sh bash apt apt-get dpkg mount umount cat ls mkdir cp mv rm \
              chmod chown grep sed awk find ip ping curl wget \
              passwd ssh sshd systemctl; do
    if command -v "$tool" >/dev/null 2>&1; then
      log "  OK: $tool"
    else
      log "  MISSING: $tool"
      missing=$((missing + 1))
    fi
  done

  if [ "$missing" -gt 0 ]; then
    log "  WARNING: $missing essential tool(s) missing!"
    return 1
  fi
  return 0
}

# Phase 4: Check for hostile modifications
check_hostile_mods() {
  log "Phase 4: Checking for hostile modifications"
  local issues=0

  # Check for suspicious cron entries
  if [ -d /etc/cron.d ]; then
    local cron_count
    cron_count="$(find /etc/cron.d -type f -newer /etc/hostname 2>/dev/null | wc -l)"
    if [ "$cron_count" -gt 0 ]; then
      log "  SUSPECT: $cron_count new cron entries since boot"
      issues=$((issues + 1))
    fi
  fi

  # Check for unauthorized services
  if command -v systemctl >/dev/null 2>&1; then
    systemctl list-units --type=service --state=running 2>/dev/null | \
      grep -v -E '(ssh|networking|systemd|dbus|cron|rsyslog|udev)' | \
      while read -r line; do
        if echo "$line" | grep -q 'running'; then
          log "  SERVICE: $line"
        fi
      done
  fi

  # Check for modified /etc/passwd
  if [ -f /etc/passwd ]; then
    local uid0_count
    uid0_count="$(awk -F: '$3==0{print $1}' /etc/passwd | wc -l)"
    if [ "$uid0_count" -gt 1 ]; then
      log "  SUSPECT: $uid0_count users with UID 0"
      issues=$((issues + 1))
    fi
  fi

  # Check for unusual network listeners
  if command -v ss >/dev/null 2>&1; then
    local listeners
    listeners="$(ss -tlnp 2>/dev/null | grep -v -E '(ssh|:22|:3128|:8080)' | tail -n +2)"
    if [ -n "$listeners" ]; then
      log "  SUSPECT listeners:"
      echo "$listeners" | while read -r line; do
        log "    $line"
      done
      issues=$((issues + 1))
    fi
  fi

  if [ "$issues" -gt 0 ]; then
    log "  $issues suspicious finding(s)"
    return 1
  fi
  log "  No hostile modifications detected"
  return 0
}

# Phase 5: Sanitize live environment
sanitize_env() {
  log "Phase 5: Sanitizing environment"

  # Remove temporary .swp files from installers
  find / -maxdepth 3 -name '*.swp' -newer /etc/hostname -delete 2>/dev/null || true
  log "  Cleared .swp files"

  # Clean debconf database of injected values
  if [ -d /var/cache/debconf ]; then
    log "  Checking debconf for pollution..."
    if command -v debconf-get-selections >/dev/null 2>&1; then
      local forced
      forced="$(debconf-get-selections 2>/dev/null | grep -c 'partman/default_filesystem' || echo 0)"
      if [ "$forced" -gt 0 ]; then
        log "  FOUND: partman/default_filesystem forced ($forced entries)"
        echo "partman partman/default_filesystem string ext4" | debconf-set-selections 2>/dev/null || true
        log "  Reset to ext4 (user can change)"
      fi
    fi
  fi

  # Verify /etc/resolv.conf is sane
  if [ -f /etc/resolv.conf ]; then
    if ! grep -q 'nameserver' /etc/resolv.conf 2>/dev/null; then
      log "  DNS missing, restoring..."
      cat > /etc/resolv.conf <<'DNS'
nameserver 209.18.47.61
nameserver 209.18.47.62
DNS
    fi
  fi

  log "  Sanitization complete"
}

# Phase 6: Generate verification report
generate_report() {
  log "Phase 6: Generating verification report"
  local report="/tmp/iso-verification-report-$(date +%Y%m%d-%H%M%S).txt"

  {
    echo "=== ISO Verification Report ==="
    echo "Date: $(date)"
    echo "Hostname: $(hostname)"
    echo ""

    echo "--- Kernel ---"
    uname -a
    echo ""

    echo "--- Block devices ---"
    lsblk 2>/dev/null || echo "(lsblk not available)"
    echo ""

    echo "--- Mounts ---"
    mount | grep -E '(cdrom|iso|loop)'
    echo ""

    echo "--- Filesystems ---"
    cat /proc/filesystems 2>/dev/null | grep -v nodev || echo "(unavailable)"
    echo ""

    echo "--- Network ---"
    ip addr show 2>/dev/null || ifconfig 2>/dev/null || echo "(no network tools)"
    echo ""

    echo "--- DNS ---"
    cat /etc/resolv.conf 2>/dev/null || echo "(no resolv.conf)"
    echo ""

    echo "--- APT sources ---"
    cat /etc/apt/sources.list 2>/dev/null || echo "(no sources.list)"
    echo ""

    echo "--- Running services ---"
    systemctl list-units --type=service --state=running 2>/dev/null || echo "(systemctl not available)"
    echo ""
  } > "$report"

  log "  Report saved to $report"
}

main() {
  local cmd="${1:-all}"
  case "$cmd" in
    all)
      verify_iso_mount
      check_pool_integrity || true
      verify_tools || true
      check_hostile_mods || true
      sanitize_env
      generate_report
      log ""
      log "ISO verification complete. See $LOG"
      ;;
    mount) verify_iso_mount ;;
    pool) check_pool_integrity ;;
    tools) verify_tools ;;
    hostile) check_hostile_mods ;;
    sanitize) sanitize_env ;;
    report) generate_report ;;
    *)
      echo "Usage: $0 {all|mount|pool|tools|hostile|sanitize|report}"
      exit 1
      ;;
  esac
}

main "$@"
