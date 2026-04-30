#!/usr/bin/env bash
set -euo pipefail

# Host static IPv4 helper for lab process networking.
# Purpose:
# - Pin a host-process IPv4 (default 192.168.68.100) on a selected interface.
# - Keep DNS untouched.
# - Report proxy/docker/bridge/VNC/TTY-relevant network state.

STATIC_CIDR="${HUM_HOST_STATIC_CIDR:-192.168.68.100/22}"
GATEWAY="${HUM_HOST_GATEWAY:-192.168.68.51}"
PREFERRED_IFACE="${HUM_HOST_STATIC_IF:-}"
PROXY_PORT="${HUM_PROXY_PORT:-3128}"
VNC_PORT="${HUM_VNC_PORT:-5901}"
NOVNC_PORT="${HUM_VDESK_PORT:-6080}"
TTY_PORT="${HUM_TTY_PORT:-22}"

log() {
  echo "[$(date '+%H:%M:%S')] $*"
}

usage() {
  cat <<'EOF'
Usage:
  sudo bash scripts/hum-host-static-ip.sh apply
  sudo bash scripts/hum-host-static-ip.sh remove
  bash scripts/hum-host-static-ip.sh status
  bash scripts/hum-host-static-ip.sh plan
  bash scripts/hum-host-static-ip.sh env

Commands:
  apply   Add static host IPv4 (default 192.168.68.100/22) to host interface
  remove  Remove static host IPv4 from host interface
  status  Print current interface/route/listener status (DNS untouched)
  plan    Show exactly what apply would execute
  env     Print proxy environment exports using static host IP

Environment overrides:
  HUM_HOST_STATIC_CIDR   Static IPv4 CIDR      (default: 192.168.68.100/22)
  HUM_HOST_GATEWAY       LAN gateway           (default: 192.168.68.51)
  HUM_HOST_STATIC_IF     Interface to modify   (default: auto-detect)
  HUM_PROXY_PORT         Host proxy port       (default: 3128)
  HUM_VNC_PORT           VNC port              (default: 5901)
  HUM_VDESK_PORT         noVNC/web VNC port    (default: 6080)
  HUM_TTY_PORT           TTY/SSH port          (default: 22)

Notes:
- This script does NOT modify DNS files or resolvers.
- This config is host-process focused (proxy/docker/bridges/VNC/TTY listeners).
EOF
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "This action requires root. Re-run with sudo." >&2
    exit 1
  fi
}

static_ip() {
  printf '%s\n' "${STATIC_CIDR%%/*}"
}

detect_iface() {
  if [[ -n "$PREFERRED_IFACE" ]]; then
    printf '%s\n' "$PREFERRED_IFACE"
    return 0
  fi

  local detected
  detected="$(ip route get "$(static_ip)" 2>/dev/null | awk '
    {
      for (i = 1; i <= NF; i++) {
        if ($i == "dev" && (i + 1) <= NF) {
          print $(i + 1)
          exit
        }
      }
    }'
  )"

  if [[ -n "$detected" ]]; then
    printf '%s\n' "$detected"
    return 0
  fi

  detected="$(ip route show default 2>/dev/null | awk '
    {
      for (i = 1; i <= NF; i++) {
        if ($i == "dev" && (i + 1) <= NF) {
          print $(i + 1)
          exit
        }
      }
    }'
  )"

  if [[ -n "$detected" ]]; then
    printf '%s\n' "$detected"
    return 0
  fi

  echo "Unable to auto-detect interface. Set HUM_HOST_STATIC_IF." >&2
  exit 1
}

check_iface_exists() {
  local iface="$1"
  ip link show "$iface" >/dev/null 2>&1 || {
    echo "Interface not found: $iface" >&2
    exit 1
  }
}

print_dns_note() {
  echo "DNS policy: unchanged (host-process static IP only)"
}

print_listener() {
  local port="$1"
  local label="$2"
  if ss -ltn "( sport = :$port )" 2>/dev/null | awk 'NR > 1 {found=1} END {exit found?0:1}'; then
    echo "$label listener :$port -> present"
  else
    echo "$label listener :$port -> not present"
  fi
}

apply_static() {
  need_cmd ip
  require_root

  local iface
  iface="$(detect_iface)"
  check_iface_exists "$iface"

  log "Applying host static IPv4: $STATIC_CIDR on interface $iface"
  ip link set "$iface" up
  ip addr replace "$STATIC_CIDR" dev "$iface"
  ip route replace "${GATEWAY}/32" dev "$iface" proto static

  log "Applied static address. DNS untouched."
  status_report "$iface"
}

remove_static() {
  need_cmd ip
  require_root

  local iface
  iface="$(detect_iface)"
  check_iface_exists "$iface"

  log "Removing host static IPv4: $STATIC_CIDR from interface $iface"
  ip addr del "$STATIC_CIDR" dev "$iface" 2>/dev/null || true
  ip route del "${GATEWAY}/32" dev "$iface" proto static 2>/dev/null || true

  log "Removed static address (if present). DNS untouched."
  status_report "$iface"
}

print_env_exports() {
  local ip
  ip="$(static_ip)"
  cat <<EOF
export HUM_HOST_STATIC_CIDR="${STATIC_CIDR}"
export HUM_HOST_STATIC_IF="${PREFERRED_IFACE:-$(detect_iface)}"
export HUM_HOST_GATEWAY="${GATEWAY}"
export HTTP_PROXY="http://${ip}:${PROXY_PORT}"
export HTTPS_PROXY="http://${ip}:${PROXY_PORT}"
export NO_PROXY="localhost,127.0.0.1,${ip},host.docker.internal"
EOF
}

status_report() {
  need_cmd ip
  need_cmd ss

  local iface="${1:-$(detect_iface)}"
  check_iface_exists "$iface"

  echo "=== Host static IPv4 status ==="
  echo "Interface: $iface"
  echo "Target static CIDR: $STATIC_CIDR"
  echo "Gateway hint: $GATEWAY"
  print_dns_note
  echo

  echo "[interface addresses]"
  ip -br addr show dev "$iface"
  echo

  echo "[route to static IP and gateway]"
  ip route get "$(static_ip)" 2>/dev/null || true
  ip route show "${GATEWAY}/32" 2>/dev/null || true
  echo

  echo "[docker bridge]"
  if ip link show docker0 >/dev/null 2>&1; then
    ip -br addr show dev docker0
  else
    echo "docker0 not present"
  fi
  echo

  echo "[bridge interfaces]"
  ip -br link show type bridge 2>/dev/null || echo "No bridge interfaces found"
  echo

  echo "[host listeners: proxy/vnc/novnc/tty]"
  print_listener "$PROXY_PORT" "proxy"
  print_listener "$VNC_PORT" "vnc"
  print_listener "$NOVNC_PORT" "novnc"
  print_listener "$TTY_PORT" "tty"
  echo

  echo "[proxy environment suggestion]"
  print_env_exports
}

plan_report() {
  local iface
  iface="$(detect_iface)"
  echo "=== Planned host static IP actions ==="
  echo "Interface: $iface"
  echo "Would run:"
  echo "  sudo ip link set \"$iface\" up"
  echo "  sudo ip addr replace \"$STATIC_CIDR\" dev \"$iface\""
  echo "  sudo ip route replace \"${GATEWAY}/32\" dev \"$iface\" proto static"
  echo
  print_dns_note
  echo "No /etc/resolv.conf changes will be made."
}

main() {
  local cmd="${1:-status}"
  case "$cmd" in
    apply)
      apply_static
      ;;
    remove)
      remove_static
      ;;
    status)
      status_report
      ;;
    plan)
      plan_report
      ;;
    env)
      print_env_exports
      ;;
    help|-h|--help)
      usage
      ;;
    *)
      echo "Unknown command: $cmd" >&2
      usage >&2
      exit 1
      ;;
  esac
}

main "$@"
