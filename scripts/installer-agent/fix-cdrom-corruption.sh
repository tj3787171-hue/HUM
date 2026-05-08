#!/bin/sh
# Emergency CDROM corruption fix for Debian/Kali installer
# Run at the installer shell when libmd0 or other packages are corrupt.
# Unmounts CDROM, forces network-only sources, removes corrupt .deb files.
set -e

echo "[CDROM-FIX] Bypassing corrupt CDROM packages..."

# Unmount cdrom to force network-only
echo "[CDROM-FIX] Unmounting CDROM..."
umount /cdrom 2>/dev/null || true
umount /media/cdrom 2>/dev/null || true
umount /media/cdrom0 2>/dev/null || true

# Remove known corrupt packages
echo "[CDROM-FIX] Removing known corrupt packages from pool..."
rm -f /cdrom/pool/main/libm/libmd/libmd0_1.1.0-2+b1_amd64.deb 2>/dev/null || true

# Disable CDROM in apt sources
echo "[CDROM-FIX] Disabling CDROM sources..."
if [ -f /etc/apt/sources.list ]; then
  sed -i 's/^deb cdrom:/# deb cdrom:/' /etc/apt/sources.list
fi
find /etc/apt/sources.list.d/ -name '*.list' -exec sed -i 's/^deb cdrom:/# deb cdrom:/' {} \; 2>/dev/null || true

# Also fix target if mounted
if [ -f /target/etc/apt/sources.list ]; then
  sed -i 's/^deb cdrom:/# deb cdrom:/' /target/etc/apt/sources.list
fi

# Force APT to use network only
mkdir -p /etc/apt/apt.conf.d
cat > /etc/apt/apt.conf.d/99force-network <<'FORCE'
APT::CDROM::NoMount "true";
Acquire::cdrom::AutoDetect "false";
Acquire::Retries "5";
Acquire::http::Timeout "30";
Acquire::https::Timeout "30";
FORCE

# Set DNS
echo "[CDROM-FIX] Setting DNS..."
cat > /etc/resolv.conf <<'DNS'
nameserver 209.18.47.61
nameserver 209.18.47.62
DNS

# Add network mirror
echo "[CDROM-FIX] Adding network mirror..."
cat >> /etc/apt/sources.list <<'MIRROR'

# Network sources (CDROM bypass)
deb https://http.kali.org/kali kali-rolling main contrib non-free non-free-firmware
deb https://deb.debian.org/debian bookworm main contrib non-free non-free-firmware
MIRROR

# Set proxy if penguin is reachable
if ping -c 1 -W 2 192.168.68.52 >/dev/null 2>&1; then
  echo "[CDROM-FIX] Penguin proxy reachable, configuring..."
  cat > /etc/apt/apt.conf.d/01proxy <<'PROXY'
Acquire::http::Proxy "http://192.168.68.52:3128";
PROXY
fi

# Update package lists
echo "[CDROM-FIX] Updating package lists..."
apt-get update --fix-missing 2>/dev/null || apt-get update -o Acquire::AllowInsecureRepositories=true 2>/dev/null || true

echo "[CDROM-FIX] Done. Network sources are now primary."
echo "[CDROM-FIX] You can now exit the shell and retry 'Install the base system'."
