#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ISO_DIR="$ROOT_DIR/iso-build"
OUT_DIR="$ROOT_DIR/data/iso-output"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEBIAN_MIRROR="${HUM_DEBIAN_MIRROR:-https://deb.debian.org/debian/}"
DEBIAN_SECURITY_MIRROR="${HUM_DEBIAN_SECURITY_MIRROR:-https://security.debian.org/debian-security/}"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "This build must run as root (use: sudo bash iso-build/build.sh)." >&2
  exit 1
fi

if ! command -v lb >/dev/null 2>&1; then
  echo "Missing live-build tooling (lb)." >&2
  echo "Install with: sudo apt-get update && sudo apt-get install -y live-build xorriso" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

pushd "$ISO_DIR" >/dev/null
lb clean --purge || true
echo "Using Debian mirror:         $DEBIAN_MIRROR"
echo "Using Debian security mirror: $DEBIAN_SECURITY_MIRROR"
lb config \
  --mode debian \
  --distribution bookworm \
  --archive-areas "main contrib non-free non-free-firmware" \
  --mirror-bootstrap "$DEBIAN_MIRROR" \
  --mirror-chroot "$DEBIAN_MIRROR" \
  --mirror-chroot-security "$DEBIAN_SECURITY_MIRROR" \
  --mirror-binary "$DEBIAN_MIRROR" \
  --mirror-binary-security "$DEBIAN_SECURITY_MIRROR" \
  --binary-images iso-hybrid \
  --debian-installer false
lb build
popd >/dev/null

ISO_SRC="$(ls -1t "$ISO_DIR"/*.iso 2>/dev/null | sed -n "1p" || true)"
if [[ -z "$ISO_SRC" ]]; then
  echo "Build finished but no ISO was produced in $ISO_DIR" >&2
  echo "If bootstrap failed in a restricted network, retry with explicit mirrors:" >&2
  echo "  HUM_DEBIAN_MIRROR=http://<reachable-mirror>/debian/ \\" >&2
  echo "  HUM_DEBIAN_SECURITY_MIRROR=http://<reachable-mirror>/debian-security/ \\" >&2
  echo "  sudo bash iso-build/build.sh" >&2
  exit 1
fi

ISO_DEST="$OUT_DIR/hum-live-$STAMP.iso"
cp -f "$ISO_SRC" "$ISO_DEST"
sha256sum "$ISO_DEST" > "$ISO_DEST.sha256"

echo "ISO saved: $ISO_DEST"
echo "Checksum:  $ISO_DEST.sha256"
