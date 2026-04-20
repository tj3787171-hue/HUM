#!/usr/bin/env bash
# HP Pavilion Slimline s5000 Series System Scan
# Identifies preseed artifacts, takeover files, and filesystem anomalies.
# Serial: MXX116042G, Product: BV627AA#ABA
set -euo pipefail

REPORT_FILE="/tmp/hp-slimline-scan-$(date +%Y%m%d-%H%M%S).txt"

section() { echo "" | tee -a "$REPORT_FILE"; echo "=== $* ===" | tee -a "$REPORT_FILE"; }
line() { echo "$*" | tee -a "$REPORT_FILE"; }

section "HP Pavilion Slimline s5000 System Scan"
line "Date: $(date)"
line "Hostname: $(hostname 2>/dev/null || echo unknown)"

# Hardware identification
section "Hardware"
if [ -f /sys/class/dmi/id/product_name ]; then
  line "Product: $(cat /sys/class/dmi/id/product_name 2>/dev/null || echo unknown)"
fi
if [ -f /sys/class/dmi/id/product_serial ]; then
  line "Serial: $(cat /sys/class/dmi/id/product_serial 2>/dev/null || echo unknown)"
fi
line "Kernel: $(uname -a)"

# Filesystem scan
section "Filesystem Types"
line "Kernel supported:"
cat /proc/filesystems 2>/dev/null | tee -a "$REPORT_FILE" || line "(unavailable)"
line ""
line "Available mkfs tools:"
for tool in mkfs.ext2 mkfs.ext3 mkfs.ext4 mkfs.btrfs mkfs.vfat mkfs.fat mkfs.xfs; do
  if command -v "$tool" >/dev/null 2>&1; then
    line "  [OK] $tool"
  else
    line "  [MISSING] $tool"
  fi
done

# Block devices and partitions
section "Block Devices"
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,UUID 2>/dev/null | tee -a "$REPORT_FILE" || line "(lsblk unavailable)"

# Fstab analysis
section "fstab"
if [ -f /etc/fstab ]; then
  cat /etc/fstab | tee -a "$REPORT_FILE"
  line ""
  line "Analysis:"
  local ext4_count btrfs_count fat_count
  ext4_count="$(grep -c 'ext4' /etc/fstab 2>/dev/null || echo 0)"
  btrfs_count="$(grep -c 'btrfs' /etc/fstab 2>/dev/null || echo 0)"
  fat_count="$(grep -c 'vfat\|fat' /etc/fstab 2>/dev/null || echo 0)"
  line "  ext4 entries: $ext4_count"
  line "  btrfs entries: $btrfs_count"
  line "  fat entries: $fat_count"
  if [ "$ext4_count" -gt 0 ] && [ "$btrfs_count" -eq 0 ] && [ "$fat_count" -eq 0 ]; then
    line "  WARNING: All filesystems forced to ext4 (preseed takeover detected)"
  fi
else
  line "(no fstab)"
fi

# Preseed artifact scan
section "Preseed Artifacts"
line "Searching for .cfg files from preseed/initrd..."
find / -maxdepth 4 -name '*.cfg' -newer /etc/hostname 2>/dev/null | while read -r f; do
  line "  $f ($(stat -c '%Y' "$f" 2>/dev/null || echo '?'))"
done

line ""
line "Debconf database:"
if [ -d /var/cache/debconf ]; then
  line "  Files: $(find /var/cache/debconf -type f 2>/dev/null | wc -l)"
  if command -v debconf-get-selections >/dev/null 2>&1; then
    line "  Partition settings:"
    debconf-get-selections 2>/dev/null | grep 'partman' | while read -r sel; do
      line "    $sel"
    done
  fi
fi

line ""
line "Preseed directories:"
for d in /var/lib/preseed /var/log/installer /var/log/debian-installer; do
  if [ -d "$d" ]; then
    line "  [FOUND] $d"
    ls -la "$d" 2>/dev/null | while read -r entry; do
      line "    $entry"
    done
  fi
done

# Grub analysis
section "Grub Configuration"
if [ -f /boot/grub/grub.cfg ]; then
  line "rootfstype setting:"
  grep -o 'rootfstype=[^ ]*' /boot/grub/grub.cfg 2>/dev/null | sort -u | while read -r rt; do
    line "  $rt"
  done
  if grep -q 'rootfstype=ext4' /boot/grub/grub.cfg 2>/dev/null; then
    line "  WARNING: rootfstype forced to ext4 in grub"
  fi
fi

# Network configuration
section "Network"
ip addr show 2>/dev/null | tee -a "$REPORT_FILE" || line "(ip command unavailable)"
line ""
line "DNS:"
cat /etc/resolv.conf 2>/dev/null | tee -a "$REPORT_FILE" || line "(no resolv.conf)"

# APT state
section "APT State"
if command -v apt >/dev/null 2>&1; then
  line "APT: available"
  line "Sources:"
  cat /etc/apt/sources.list 2>/dev/null | grep -v '^#' | grep -v '^$' | while read -r src; do
    line "  $src"
  done
  if [ -d /etc/apt/sources.list.d ]; then
    find /etc/apt/sources.list.d -name '*.list' -exec cat {} \; 2>/dev/null | grep -v '^#' | grep -v '^$' | while read -r src; do
      line "  $src"
    done
  fi
else
  line "APT: NOT AVAILABLE (tool elimination detected!)"
fi

# .swp file scan
section "Swap/Temp Files"
find / -maxdepth 3 -name '*.swp' -o -name '*.tmp' -o -name '.~*' 2>/dev/null | while read -r f; do
  line "  $f"
done

section "Scan Complete"
line "Report: $REPORT_FILE"
