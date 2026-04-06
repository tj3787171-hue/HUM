#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ISO_DIR="$ROOT_DIR/iso-build"
OUT_DIR="$ROOT_DIR/data/iso-output"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

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
lb config \
  --mode debian \
  --distribution bookworm \
  --archive-areas "main contrib non-free non-free-firmware" \
  --mirror-bootstrap "http://deb.debian.org/debian/" \
  --mirror-chroot "http://deb.debian.org/debian/" \
  --mirror-chroot-security "http://security.debian.org/debian-security/" \
  --mirror-binary "http://deb.debian.org/debian/" \
  --mirror-binary-security "http://security.debian.org/debian-security/" \
  --binary-images iso-hybrid \
  --debian-installer false
lb build
popd >/dev/null

ISO_SRC="$(ls -1t "$ISO_DIR"/*.iso 2>/dev/null | sed -n "1p" || true)"
if [[ -z "$ISO_SRC" ]]; then
  echo "Build finished but no ISO was produced in $ISO_DIR" >&2
  exit 1
fi

ISO_DEST="$OUT_DIR/hum-live-$STAMP.iso"
cp -f "$ISO_SRC" "$ISO_DEST"
sha256sum "$ISO_DEST" > "$ISO_DEST.sha256"

echo "ISO saved: $ISO_DEST"
echo "Checksum:  $ISO_DEST.sha256"
