#!/usr/bin/env bash
# Filesystem Format Restoration Script
# Restores btrfs, fat12, fat16, ext2, ext3 support that was overridden.
# HP Pavilion Slimline s5000: Serial MXX116042G, Product BV627AA#ABA
set -euo pipefail

LOG="/var/log/filesystem-restoration-$(date +%Y%m%d-%H%M%S).log"
BACKUP_DIR="/var/backups/filesystem-restoration"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

usage() {
  cat <<'EOF'
Usage: restore-filesystems.sh <command>

Commands:
  scan       Scan current filesystem support
  restore    Restore missing filesystem tools
  fstab      Clean and restore fstab
  grub       Fix grub rootfstype forcing
  debconf    Clean debconf database of forced values
  full       Run all restoration steps
  science    Display scientific reasoning for format choices
EOF
}

cmd_scan() {
  log "=== Filesystem Support Scan ==="

  log "Kernel filesystems (/proc/filesystems):"
  cat /proc/filesystems 2>/dev/null | while read -r nodev fstype; do
    log "  $nodev $fstype"
  done

  log ""
  log "Kernel modules (filesystem):"
  for mod in ext2 ext3 ext4 btrfs vfat fat msdos xfs; do
    if lsmod 2>/dev/null | grep -q "^$mod"; then
      log "  [LOADED] $mod"
    elif modinfo "$mod" >/dev/null 2>&1; then
      log "  [AVAILABLE] $mod (not loaded)"
    else
      log "  [MISSING] $mod"
    fi
  done

  log ""
  log "mkfs tools:"
  for tool in mkfs.ext2 mkfs.ext3 mkfs.ext4 mkfs.btrfs mkfs.vfat mkfs.fat mkfs.xfs; do
    if command -v "$tool" >/dev/null 2>&1; then
      log "  [OK] $tool ($(command -v "$tool"))"
    else
      log "  [MISSING] $tool"
    fi
  done

  log ""
  log "fsck tools:"
  for tool in fsck.ext2 fsck.ext3 fsck.ext4 fsck.vfat btrfsck; do
    if command -v "$tool" >/dev/null 2>&1; then
      log "  [OK] $tool"
    else
      log "  [MISSING] $tool"
    fi
  done
}

cmd_restore() {
  log "=== Restoring Filesystem Tools ==="

  # Load kernel modules
  for mod in ext2 ext3 btrfs vfat fat msdos; do
    if ! lsmod 2>/dev/null | grep -q "^$mod"; then
      modprobe "$mod" 2>/dev/null && log "  Loaded module: $mod" || log "  Cannot load: $mod"
    fi
  done

  # Install filesystem tools via APT
  if command -v apt-get >/dev/null 2>&1; then
    log "Installing filesystem packages..."
    apt-get update -qq 2>/dev/null || true
    apt-get install -y --no-install-recommends \
      e2fsprogs \
      dosfstools \
      btrfs-progs \
      xfsprogs \
      2>/dev/null || log "  Warning: some packages could not be installed"
  else
    log "  APT not available - cannot install filesystem packages"
    log "  Try: source /tmp/tool-preserve/recover.sh"
  fi

  # Verify after restore
  cmd_scan
}

cmd_fstab() {
  log "=== fstab Restoration ==="
  mkdir -p "$BACKUP_DIR"

  if [ ! -f /etc/fstab ]; then
    log "No fstab found"
    return 1
  fi

  # Backup current fstab
  cp -a /etc/fstab "$BACKUP_DIR/fstab.$(date +%Y%m%d-%H%M%S)"
  log "Backed up fstab"

  # Analyze current fstab
  log "Current fstab analysis:"
  local total ext4_count uuid_count label_count
  total="$(grep -c '^[^#]' /etc/fstab 2>/dev/null || echo 0)"
  ext4_count="$(grep -c 'ext4' /etc/fstab 2>/dev/null || echo 0)"
  uuid_count="$(grep -c 'UUID=' /etc/fstab 2>/dev/null || echo 0)"
  label_count="$(grep -c 'LABEL=' /etc/fstab 2>/dev/null || echo 0)"
  log "  Total entries: $total"
  log "  ext4 entries: $ext4_count"
  log "  UUID-based: $uuid_count"
  log "  LABEL-based: $label_count"

  # Remove rootfstype forcing
  if grep -q 'rootfstype=ext4' /etc/fstab 2>/dev/null; then
    sed -i 's/rootfstype=ext4//' /etc/fstab
    log "  Removed rootfstype=ext4 from fstab"
  fi

  # Generate improved fstab template
  cat > "$BACKUP_DIR/fstab.restored" <<'FSTAB_TEMPLATE'
# /etc/fstab: restored filesystem table
# Format: <device> <mount> <type> <options> <dump> <pass>
#
# Filesystem choices restored - use appropriate type per partition:
#   ext4  - default for root/home (journaled, modern)
#   ext3  - legacy compatibility
#   ext2  - embedded/flash (no journal wear)
#   btrfs - snapshots/RAID (if kernel supports)
#   vfat  - EFI boot, USB/SD (universal compatibility)
#
# See restore-filesystems.sh science for format selection guide.
FSTAB_TEMPLATE

  # Copy non-comment lines from current fstab
  grep '^[^#]' /etc/fstab 2>/dev/null >> "$BACKUP_DIR/fstab.restored" || true

  log "  Restored fstab template at $BACKUP_DIR/fstab.restored"
  log "  Review and copy to /etc/fstab when ready"
}

cmd_grub() {
  log "=== Grub Restoration ==="
  mkdir -p "$BACKUP_DIR"

  if [ -f /etc/default/grub ]; then
    cp -a /etc/default/grub "$BACKUP_DIR/grub.default.$(date +%Y%m%d-%H%M%S)"

    # Remove forced rootfstype
    if grep -q 'rootfstype=ext4' /etc/default/grub; then
      sed -i 's/rootfstype=ext4//' /etc/default/grub
      log "  Removed rootfstype=ext4 from /etc/default/grub"
    fi

    # Clean up double spaces
    sed -i 's/  */ /g' /etc/default/grub

    log "  Run 'update-grub' to apply changes"
  fi

  if [ -f /boot/grub/grub.cfg ]; then
    cp -a /boot/grub/grub.cfg "$BACKUP_DIR/grub.cfg.$(date +%Y%m%d-%H%M%S)"
    log "  Backed up grub.cfg"
  fi
}

cmd_debconf() {
  log "=== Debconf Cleanup ==="

  if ! command -v debconf-set-selections >/dev/null 2>&1; then
    log "debconf-set-selections not available"
    return 1
  fi

  # Clear forced partition settings
  log "Clearing forced partitioning selections..."
  for key in \
    "partman/default_filesystem" \
    "partman-auto/method" \
    "partman-auto/choose_recipe" \
    "partman/choose_partition" \
    "partman-partitioning/confirm_write_new_label"; do
    echo "RESET $key" | debconf-communicate 2>/dev/null || true
    log "  Reset: $key"
  done

  log "  Debconf cleaned"
}

cmd_full() {
  log "=== FULL FILESYSTEM RESTORATION ==="
  cmd_scan
  cmd_restore
  cmd_fstab
  cmd_grub
  cmd_debconf
  log ""
  log "Full restoration complete."
  log "Backup: $BACKUP_DIR"
  log "Log: $LOG"
}

cmd_science() {
  cat <<'SCIENCE'
=== Scientific Reasoning for Filesystem Format Selection ===

Each filesystem format has specific engineering trade-offs. The preseed
"takeover" forced ext4 everywhere, removing your ability to choose the
right format for each partition's purpose.

┌─────────┬──────────────────────┬─────────────────────────────────────┐
│ Format  │ Best Use Case        │ Engineering Rationale               │
├─────────┼──────────────────────┼─────────────────────────────────────┤
│ FAT12   │ <4MB partitions      │ 12-bit FAT. Minimal overhead.      │
│         │ Firmware blobs       │ Universal firmware compatibility.   │
├─────────┼──────────────────────┼─────────────────────────────────────┤
│ FAT16   │ <2GB partitions      │ 16-bit FAT. DOS/Windows/Linux/Mac  │
│         │ Boot/EFI             │ cross-platform support.             │
├─────────┼──────────────────────┼─────────────────────────────────────┤
│ FAT32   │ USB drives, SD cards │ 32-bit FAT. 4GB file size limit.   │
│         │ EFI System Partition │ Required by UEFI specification.     │
├─────────┼──────────────────────┼─────────────────────────────────────┤
│ EXT2    │ Flash/embedded       │ No journal = no flash wear.         │
│         │ Boot partitions      │ Simple, fast, low overhead.         │
├─────────┼──────────────────────┼─────────────────────────────────────┤
│ EXT3    │ Legacy systems       │ Adds journal to ext2.               │
│         │ Backward compat      │ Mountable as ext2 if needed.        │
├─────────┼──────────────────────┼─────────────────────────────────────┤
│ EXT4    │ Root filesystem      │ Extents, delayed allocation,        │
│         │ General purpose      │ up to 1 EiB volumes. Default Linux. │
├─────────┼──────────────────────┼─────────────────────────────────────┤
│ BTRFS   │ Snapshots, RAID      │ Copy-on-write. Self-healing.        │
│         │ Data integrity       │ Inline compression. Subvolumes.     │
│         │                      │ "Deprecated" label is misleading.   │
├─────────┼──────────────────────┼─────────────────────────────────────┤
│ XFS     │ Large files          │ Excellent large file performance.   │
│         │ Databases, media     │ Cannot shrink, only grow.           │
└─────────┴──────────────────────┴─────────────────────────────────────┘

Decision Process:
  1. Partition size < 4MB?     → FAT12
  2. EFI System Partition?     → FAT32 (UEFI requirement)
  3. Boot partition?           → EXT2 or FAT32
  4. Flash/SSD (wear concern)? → EXT2 (no journal wear)
  5. Need snapshots/RAID?      → BTRFS
  6. Large file workloads?     → XFS
  7. General purpose root?     → EXT4

The HP Pavilion Slimline s5000 (BV627AA#ABA) has:
  - BIOS/UEFI: Legacy BIOS with CSM
  - Typical drive: SATA HDD 320GB-1TB
  - Recommended layout:
    /boot    256MB  EXT2 (no journal, fast boot)
    swap     4-8GB  swap
    /        rest   EXT4 (default, journaled)
    /data    opt.   BTRFS if snapshots needed

SCIENCE
}

main() {
  local cmd="${1:-help}"
  case "$cmd" in
    scan)    cmd_scan ;;
    restore) cmd_restore ;;
    fstab)   cmd_fstab ;;
    grub)    cmd_grub ;;
    debconf) cmd_debconf ;;
    full)    cmd_full ;;
    science) cmd_science ;;
    -h|--help|help) usage ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
