#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# hum-build-iso.sh
#
# Build a bootable ISO image containing the HUM toolkit:
#   - hum-snap-bypass.sh   (userspace snap handling)
#   - hum-snap-server.sh   (loop-mount + cgroup snap server)
#   - hum-dev-netns.sh     (network namespace setup)
#   - deepseek_db_link.py  (DeepSeek backup importer)
#   - post-create.sh       (network summary)
#
# The ISO uses ISOLINUX as the bootloader and is suitable for burning to
# USB/CD or mounting directly.  It includes a minimal boot menu that
# displays HUM version info.
#
# Requirements: genisoimage (or mkisofs), isolinux / syslinux-common
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ISO_LABEL="${HUM_ISO_LABEL:-HUM_TOOLKIT}"
ISO_OUTPUT="${1:-${REPO_ROOT}/dist/hum-toolkit.iso}"
BUILD_DIR="${HUM_ISO_BUILD_DIR:-/tmp/hum-iso-build}"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/hum-build-iso.sh [output-path]

Builds a bootable ISO containing the HUM toolkit scripts.

Default output: dist/hum-toolkit.iso

Environment overrides:
  HUM_ISO_LABEL       Volume label  (default: HUM_TOOLKIT)
  HUM_ISO_BUILD_DIR   Temp staging  (default: /tmp/hum-iso-build)
EOF
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    echo "Install with: sudo apt-get install $2" >&2
    exit 1
  fi
}

log() { echo "[hum-build-iso] $*"; }

main() {
  if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
    usage
    exit 0
  fi

  need_cmd genisoimage genisoimage
  need_cmd isohybrid syslinux-utils

  # Find isolinux.bin
  local isolinux_bin=""
  for candidate in \
    /usr/lib/ISOLINUX/isolinux.bin \
    /usr/lib/syslinux/isolinux.bin \
    /usr/share/syslinux/isolinux.bin \
    /usr/lib/syslinux/modules/bios/isolinux.bin; do
    if [[ -f "$candidate" ]]; then
      isolinux_bin="$candidate"
      break
    fi
  done

  if [[ -z "$isolinux_bin" ]]; then
    echo "Error: cannot find isolinux.bin. Install isolinux package." >&2
    exit 1
  fi

  # Find ldlinux.c32
  local ldlinux_c32=""
  for candidate in \
    /usr/lib/syslinux/modules/bios/ldlinux.c32 \
    /usr/lib/ISOLINUX/ldlinux.c32 \
    /usr/share/syslinux/ldlinux.c32; do
    if [[ -f "$candidate" ]]; then
      ldlinux_c32="$candidate"
      break
    fi
  done

  log "isolinux.bin: $isolinux_bin"
  log "ldlinux.c32: ${ldlinux_c32:-not found (non-fatal)}"

  # Clean + create staging area
  rm -rf "$BUILD_DIR"
  mkdir -p "$BUILD_DIR/isolinux"
  mkdir -p "$BUILD_DIR/hum/scripts"
  mkdir -p "$BUILD_DIR/hum/devcontainer"
  mkdir -p "$BUILD_DIR/hum/docs"

  # Copy ISOLINUX bootloader
  cp "$isolinux_bin" "$BUILD_DIR/isolinux/"
  if [[ -n "$ldlinux_c32" ]]; then
    cp "$ldlinux_c32" "$BUILD_DIR/isolinux/"
  fi

  # Create ISOLINUX config
  local version_date
  version_date="$(date +%Y-%m-%d)"
  cat > "$BUILD_DIR/isolinux/isolinux.cfg" << ISOCFG
UI isolinux/isolinux.bin
DEFAULT hum
PROMPT 1
TIMEOUT 300

LABEL hum
  MENU LABEL HUM Toolkit ($version_date)
  KERNEL /hum/scripts/hum-snap-bypass.sh
  APPEND ---

DISPLAY isolinux/boot.msg
ISOCFG

  # Boot message
  cat > "$BUILD_DIR/isolinux/boot.msg" << 'BOOTMSG'

  ======================================
        HUM - LAN Dev Toolkit ISO
  ======================================

  This ISO contains the HUM toolkit for
  working with snap packages, network
  namespaces, and DeepSeek backups
  without requiring snapd or systemd.

  Contents:
    /hum/scripts/   - All utility scripts
    /hum/docs/       - Documentation
    /hum/devcontainer/ - Dev container config

  Mount this ISO and copy scripts to
  your system, or extract with:

    mount -o loop hum-toolkit.iso /mnt
    cp -r /mnt/hum/scripts/ ~/hum/

  ======================================

BOOTMSG

  # Copy HUM toolkit files
  cp "$REPO_ROOT/scripts/hum-snap-bypass.sh" "$BUILD_DIR/hum/scripts/"
  cp "$REPO_ROOT/scripts/hum-snap-server.sh" "$BUILD_DIR/hum/scripts/"
  cp "$REPO_ROOT/scripts/hum-dev-netns.sh"   "$BUILD_DIR/hum/scripts/"
  cp "$REPO_ROOT/scripts/deepseek_db_link.py" "$BUILD_DIR/hum/scripts/"
  cp "$REPO_ROOT/.devcontainer/post-create.sh" "$BUILD_DIR/hum/devcontainer/"
  cp "$REPO_ROOT/.devcontainer/Dockerfile"     "$BUILD_DIR/hum/devcontainer/"
  cp "$REPO_ROOT/.devcontainer/devcontainer.json" "$BUILD_DIR/hum/devcontainer/"
  cp "$REPO_ROOT/README.md" "$BUILD_DIR/hum/docs/"
  if [[ -f "$REPO_ROOT/AGENTS.md" ]]; then
    cp "$REPO_ROOT/AGENTS.md" "$BUILD_DIR/hum/docs/"
  fi

  # Version manifest
  cat > "$BUILD_DIR/hum/VERSION" << VEOF
HUM Toolkit ISO
Built: $version_date
Git:   $(cd "$REPO_ROOT" && git rev-parse --short HEAD 2>/dev/null || echo 'unknown')
VEOF

  # Checksum file
  (cd "$BUILD_DIR" && find hum -type f -exec sha256sum {} + > "$BUILD_DIR/hum/SHA256SUMS")

  # Create output directory
  mkdir -p "$(dirname "$ISO_OUTPUT")"

  # Build ISO
  log "Building ISO: $ISO_OUTPUT"
  genisoimage \
    -o "$ISO_OUTPUT" \
    -V "$ISO_LABEL" \
    -J -R -l \
    -b isolinux/isolinux.bin \
    -c isolinux/boot.cat \
    -no-emul-boot \
    -boot-load-size 4 \
    -boot-info-table \
    -input-charset utf-8 \
    "$BUILD_DIR" 2>&1

  # Make hybrid (bootable from USB too)
  if command -v isohybrid >/dev/null 2>&1; then
    isohybrid "$ISO_OUTPUT" 2>/dev/null || log "isohybrid skipped (non-fatal)"
  fi

  log "ISO created: $ISO_OUTPUT"
  log "Size: $(stat --printf='%s' "$ISO_OUTPUT") bytes ($(du -h "$ISO_OUTPUT" | cut -f1))"
  log "Label: $ISO_LABEL"
  echo ""
  log "Verify with:"
  log "  file $ISO_OUTPUT"
  log "  isoinfo -d -i $ISO_OUTPUT"

  # Cleanup
  rm -rf "$BUILD_DIR"
}

main "$@"
