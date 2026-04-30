#!/usr/bin/env bash
set -euo pipefail

STATIC_CIDR="${HUM_HOST_STATIC_CIDR:-192.168.68.100/22}"
GATEWAY="${HUM_HOST_GATEWAY:-192.168.68.51}"
STATIC_IF="${HUM_HOST_STATIC_IF:-}"
PROXY_PORT="${HUM_PROXY_PORT:-3128}"
VNC_PORT="${HUM_VNC_PORT:-5901}"
VDESK_PORT="${HUM_VDESK_PORT:-6080}"
TTY_PORT="${HUM_TTY_PORT:-22}"

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
- The static address is for host-process connectivity, not DNS.
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

log() {
  printf '[%(%H:%M:%S)T] %s\n' -1 "$*"
}

static_ip() {
  printf '%s\n' "${STATIC_CIDR%%/*}"
}

detect_iface() {
  if [[ -n "$STATIC_IF" ]]; then
    printf '%s\n' "$STATIC_IF"
    return
  fi
  ip -o route show default 2>/dev/null | awk '{print $5; exit}'
}

listener_status() {
  local label="$1"
  local port="$2"
  if ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)${port}$"; then
    printf '%s listener :%s -> present\n' "$label" "$port"
  else
    printf '%s listener :%s -> not present\n' "$label" "$port"
  fi
}

show_plan() {
  local iface="$1"
  echo "=== Planned host static IP actions ==="
  echo "Interface: $iface"
  echo "Would run:"
  echo "  sudo ip link set \"$iface\" up"
  echo "  sudo ip addr replace \"$STATIC_CIDR\" dev \"$iface\""
  echo "  sudo ip route replace \"$GATEWAY/32\" dev \"$iface\" proto static"
  echo
  echo "DNS policy: unchanged (host-process static IP only)"
  echo "No /etc/resolv.conf changes will be made."
}

show_status() {
  local iface="$1"
  local ip_addr
  ip_addr="$(static_ip)"
  echo "=== Host static IPv4 status ==="
  echo "Interface: $iface"
  echo "Target static CIDR: $STATIC_CIDR"
  echo "Gateway hint: $GATEWAY"
  echo "DNS policy: unchanged (host-process static IP only)"
  echo
  echo "[interface addresses]"
  ip -br addr show dev "$iface" 2>/dev/null || true
  echo
  echo "[route to static IP and gateway]"
  ip route get "$ip_addr" 2>/dev/null || true
  ip route show "$GATEWAY/32" 2>/dev/null || true
  echo
  echo "[docker bridge]"
  ip -br addr show dev docker0 2>/dev/null || echo "docker0 not present"
  echo
  echo "[bridge interfaces]"
  ip -br link show type bridge 2>/dev/null || true
  echo
  echo "[host listeners: proxy/vnc/novnc/tty]"
  listener_status proxy "$PROXY_PORT"
  listener_status vnc "$VNC_PORT"
  listener_status novnc "$VDESK_PORT"
  listener_status tty "$TTY_PORT"
}

apply_static() {
  local iface="$1"
  log "Applying host static IPv4: $STATIC_CIDR on interface $iface"
  ip link set "$iface" up
  ip addr replace "$STATIC_CIDR" dev "$iface"
  ip route replace "$GATEWAY/32" dev "$iface" proto static
  log "Applied static address. DNS untouched."
  show_status "$iface"
}

remove_static() {
  local iface="$1"
  log "Removing host static IPv4: $STATIC_CIDR from interface $iface"
  ip addr del "$STATIC_CIDR" dev "$iface" 2>/dev/null || true
  ip route del "$GATEWAY/32" dev "$iface" 2>/dev/null || true
  log "Removed static address/route if present. DNS untouched."
  show_status "$iface"
}

print_env() {
  local ip_addr
  ip_addr="$(static_ip)"
  cat <<EOF
export HTTP_PROXY=http://${ip_addr}:${PROXY_PORT}
export HTTPS_PROXY=http://${ip_addr}:${PROXY_PORT}
export ALL_PROXY=http://${ip_addr}:${PROXY_PORT}
export NO_PROXY=localhost,127.0.0.1,${ip_addr},host.docker.internal
export HUM_VNC_URL=vnc://${ip_addr}:${VNC_PORT}
export HUM_VDESK_URL=http://${ip_addr}:${VDESK_PORT}
export HUM_TTY_TARGET=${ip_addr}:${TTY_PORT}
EOF
}

main() {
  need_cmd ip
  local action="${1:-status}"
  local iface
  iface="$(detect_iface)"
  if [[ -z "$iface" ]]; then
    echo "Could not detect interface. Set HUM_HOST_STATIC_IF." >&2
    exit 1
  fi

  case "$action" in
    apply)
      require_root
      apply_static "$iface"
      ;;
    remove)
      require_root
      remove_static "$iface"
      ;;
    status)
      show_status "$iface"
      ;;
    plan)
      show_plan "$iface"
      ;;
    env)
      print_env
      ;;
    help|-h|--help)
      usage
      ;;
    *)
      usage
      exit 2
      ;;
  esac
}

main "$@"
