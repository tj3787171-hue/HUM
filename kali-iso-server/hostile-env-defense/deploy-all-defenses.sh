#!/bin/sh
# Master deployment script for hostile environment defense suite.
# Deploys all protection layers in the correct order.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="/tmp/defense-deploy-$(date +%Y%m%d-%H%M%S).log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

log "=========================================="
log "HOSTILE ENVIRONMENT DEFENSE DEPLOYMENT"
log "=========================================="

usage() {
  cat <<'EOF'
Usage: deploy-all-defenses.sh [command]

Commands:
  all         Deploy all defense layers (default)
  apt         APT persistence only
  x11         X11 isolation only
  etc         /etc/ structure protection only
  iso         ISO verification and sanitization only
  mirror      Tool preservation and mirror defense only
  status      Show defense status

Order of deployment (all):
  1. Tool preservation (save binaries before anything can remove them)
  2. APT persistence (protect package management)
  3. X11 isolation (neutralize display interference)
  4. /etc/ structure protection (prevent directory sabotage)
  5. ISO verification (check for corruption)
  6. Mirror authentication (verify network sources)
EOF
}

deploy_all() {
  log "Deploying all defense layers..."
  log ""

  log "--- Layer 1: Tool & Mirror Defense ---"
  sh "$SCRIPT_DIR/tool-mirror-defense.sh" all 2>&1 | tee -a "$LOG"
  log ""

  log "--- Layer 2: APT Persistence ---"
  sh "$SCRIPT_DIR/apt-persistence.sh" all 2>&1 | tee -a "$LOG"
  log ""

  log "--- Layer 3: X11 Isolation ---"
  sh "$SCRIPT_DIR/x11-isolation.sh" all 2>&1 | tee -a "$LOG"
  log ""

  log "--- Layer 4: /etc/ Structure Protection ---"
  sh "$SCRIPT_DIR/etc-structure-protect.sh" all 2>&1 | tee -a "$LOG"
  log ""

  log "--- Layer 5: ISO Verification ---"
  sh "$SCRIPT_DIR/iso-verify-sanitize.sh" all 2>&1 | tee -a "$LOG"
  log ""

  log "=========================================="
  log "ALL DEFENSES DEPLOYED"
  log "=========================================="
  log ""
  log "Active protections:"
  log "  [1] Tools preserved at /tmp/tool-preserve"
  log "  [2] APT binaries made immutable"
  log "  [3] X11/ICE/haveged neutralized"
  log "  [4] /etc/ structure snapshotted and protected"
  log "  [5] ISO verified and sanitized"
  log "  [6] Mirrors authenticated, DNS set to 209.18.47.61/62"
  log ""
  log "Background watchdogs available:"
  log "  sh $SCRIPT_DIR/apt-persistence.sh watch &"
  log "  sh $SCRIPT_DIR/etc-structure-protect.sh watch &"
  log ""
  log "Recovery:"
  log "  source /tmp/tool-preserve/recover.sh"
  log ""
  log "Full log: $LOG"
}

show_status() {
  echo "=== Defense Status ==="
  echo ""

  echo "Tool preservation:"
  if [ -d /tmp/tool-preserve ]; then
    echo "  [ACTIVE] $(ls /tmp/tool-preserve/bin/ 2>/dev/null | wc -l) tools saved"
  else
    echo "  [INACTIVE]"
  fi

  echo ""
  echo "APT protection:"
  if command -v apt-get >/dev/null 2>&1; then
    echo "  [OK] apt-get available"
  else
    echo "  [ALERT] apt-get MISSING"
  fi
  if [ -f /etc/apt/apt.conf.d/99no-cdrom ]; then
    echo "  [OK] CDROM disabled"
  fi

  echo ""
  echo "X11 isolation:"
  if [ -d /tmp/x11-quarantine ]; then
    echo "  [ACTIVE] Quarantine dir exists"
  else
    echo "  [INACTIVE]"
  fi

  echo ""
  echo "/etc/ protection:"
  if [ -d /tmp/etc-snapshot ]; then
    echo "  [ACTIVE] Snapshot exists"
  else
    echo "  [INACTIVE]"
  fi

  echo ""
  echo "Mirror status:"
  if [ -f /etc/apt/sources.list.d/verified-mirrors.list ]; then
    echo "  [ACTIVE] Verified mirrors configured"
    cat /etc/apt/sources.list.d/verified-mirrors.list | grep -v '^#' | grep -v '^$' | while read -r line; do
      echo "    $line"
    done
  else
    echo "  [INACTIVE]"
  fi

  echo ""
  echo "DNS:"
  cat /etc/resolv.conf 2>/dev/null | grep nameserver || echo "  [ALERT] No DNS configured"
}

main() {
  local cmd="${1:-all}"
  case "$cmd" in
    all) deploy_all ;;
    apt) sh "$SCRIPT_DIR/apt-persistence.sh" all ;;
    x11) sh "$SCRIPT_DIR/x11-isolation.sh" all ;;
    etc) sh "$SCRIPT_DIR/etc-structure-protect.sh" all ;;
    iso) sh "$SCRIPT_DIR/iso-verify-sanitize.sh" all ;;
    mirror) sh "$SCRIPT_DIR/tool-mirror-defense.sh" all ;;
    status) show_status ;;
    -h|--help|help) usage ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
