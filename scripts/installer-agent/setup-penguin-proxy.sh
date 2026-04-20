#!/usr/bin/env bash
# Setup APT/HTTP proxy on penguin namespace (192.168.68.52)
# Acts as relay for installer targets.
set -euo pipefail

PROXY_PORT="${HUM_PROXY_PORT:-3128}"
PENGUIN_IP="${HUM_PENGUIN_IP:-192.168.68.52}"
PENGUIN_GATEWAY="${HUM_PENGUIN_GATEWAY:-192.168.68.51}"
DNS_SERVERS=("209.18.47.61" "209.18.47.62")
VETH_HOST="penguin-veth0"
VETH_PEER="penguin-peer0"
NS_NAME="penguin"
HTTP_PORT="${HUM_HTTP_PORT:-8080}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="/tmp/penguin-proxy-setup.log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }
err() { log "ERROR: $*" >&2; }

usage() {
  cat <<'EOF'
Usage: setup-penguin-proxy.sh <command>

Commands:
  setup       Configure penguin namespace with veth pair and proxy
  start       Start the APT proxy service
  stop        Stop the APT proxy service
  status      Show proxy and namespace status
  serve       Start HTTP file server for installer configs
  teardown    Remove namespace and proxy

Environment:
  HUM_PROXY_PORT       Proxy port (default: 3128)
  HUM_PENGUIN_IP       Penguin IP (default: 192.168.68.52)
  HUM_PENGUIN_GATEWAY  Gateway (default: 192.168.68.51)
  HUM_HTTP_PORT        HTTP file server port (default: 8080)
EOF
}

require_root() {
  if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    err "This command requires root. Re-run with sudo."
    exit 1
  fi
}

setup_namespace() {
  require_root
  log "Setting up penguin namespace with veth pair"

  # Create namespace if missing
  if ! ip netns list 2>/dev/null | grep -q "^${NS_NAME}"; then
    ip netns add "$NS_NAME"
    log "Created namespace: $NS_NAME"
  fi

  # Create veth pair if missing
  if ! ip link show "$VETH_HOST" >/dev/null 2>&1; then
    ip link add "$VETH_HOST" type veth peer name "$VETH_PEER"
    ip link set "$VETH_PEER" netns "$NS_NAME"
    log "Created veth pair: $VETH_HOST <-> $VETH_PEER"
  fi

  # Configure host side
  ip link set "$VETH_HOST" up
  ip addr replace "${PENGUIN_IP}/22" dev "$VETH_HOST" 2>/dev/null || true

  # Configure namespace side
  ip -n "$NS_NAME" link set lo up
  ip -n "$NS_NAME" link set "$VETH_PEER" up
  ip -n "$NS_NAME" addr replace "${PENGUIN_IP}/22" dev "$VETH_PEER" 2>/dev/null || true
  ip -n "$NS_NAME" route replace default via "$PENGUIN_GATEWAY" dev "$VETH_PEER" 2>/dev/null || true

  # Set DNS in namespace
  mkdir -p "/etc/netns/${NS_NAME}"
  printf 'nameserver %s\n' "${DNS_SERVERS[@]}" > "/etc/netns/${NS_NAME}/resolv.conf"

  log "Namespace $NS_NAME configured:"
  log "  IP: $PENGUIN_IP/22"
  log "  Gateway: $PENGUIN_GATEWAY"
  log "  DNS: ${DNS_SERVERS[*]}"
  log "  veth: $VETH_HOST <-> $VETH_PEER"
}

start_proxy() {
  log "Starting APT proxy on port $PROXY_PORT"

  if command -v apt-cacher-ng >/dev/null 2>&1; then
    log "Using apt-cacher-ng"
    systemctl start apt-cacher-ng 2>/dev/null || apt-cacher-ng -c /etc/apt-cacher-ng/ &
  else
    log "apt-cacher-ng not installed, using Python HTTP proxy"
    cat > /tmp/apt-proxy.py <<'PROXY_SCRIPT'
import http.server
import urllib.request
import socketserver
import sys

class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            url = self.path if self.path.startswith('http') else f'http://http.kali.org{self.path}'
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in ('transfer-encoding', 'connection'):
                        self.send_header(k, v)
                self.end_headers()
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except Exception as e:
            self.send_error(502, str(e))

    def log_message(self, format, *args):
        sys.stderr.write(f"[proxy] {self.client_address[0]} - {format % args}\n")

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3128
with socketserver.TCPServer(("0.0.0.0", PORT), ProxyHandler) as httpd:
    print(f"APT proxy listening on 0.0.0.0:{PORT}")
    httpd.serve_forever()
PROXY_SCRIPT
    python3 /tmp/apt-proxy.py "$PROXY_PORT" &
    echo $! > /tmp/apt-proxy.pid
    log "Python APT proxy started on port $PROXY_PORT (PID: $(cat /tmp/apt-proxy.pid))"
  fi
}

stop_proxy() {
  log "Stopping APT proxy"
  if [ -f /tmp/apt-proxy.pid ]; then
    kill "$(cat /tmp/apt-proxy.pid)" 2>/dev/null || true
    rm -f /tmp/apt-proxy.pid
    log "Python proxy stopped"
  fi
  systemctl stop apt-cacher-ng 2>/dev/null || true
}

show_status() {
  echo "=== Penguin Namespace Status ==="
  if ip netns list 2>/dev/null | grep -q "^${NS_NAME}"; then
    echo "Namespace: $NS_NAME (exists)"
    ip -n "$NS_NAME" addr show 2>/dev/null || echo "  (no addresses)"
    echo ""
    echo "Routes:"
    ip -n "$NS_NAME" route show 2>/dev/null || echo "  (no routes)"
  else
    echo "Namespace: $NS_NAME (not found)"
  fi

  echo ""
  echo "=== Proxy Status ==="
  if [ -f /tmp/apt-proxy.pid ] && kill -0 "$(cat /tmp/apt-proxy.pid)" 2>/dev/null; then
    echo "Python proxy: running (PID: $(cat /tmp/apt-proxy.pid))"
  else
    echo "Python proxy: not running"
  fi
  if systemctl is-active apt-cacher-ng >/dev/null 2>&1; then
    echo "apt-cacher-ng: running"
  fi

  echo ""
  echo "=== veth Pair ==="
  ip link show "$VETH_HOST" 2>/dev/null || echo "$VETH_HOST: not found"
}

serve_files() {
  log "Starting HTTP file server on port $HTTP_PORT"
  local serve_dir="${SCRIPT_DIR}"
  cd "$serve_dir"
  python3 -m http.server "$HTTP_PORT" --bind 0.0.0.0 &
  echo $! > /tmp/http-file-server.pid
  log "Serving $serve_dir on http://0.0.0.0:${HTTP_PORT}/"
  log "PID: $(cat /tmp/http-file-server.pid)"
  log ""
  log "Available files:"
  ls -la "$serve_dir"/ | tee -a "$LOG"
  log ""
  log "From installer, use:"
  log "  wget http://${PENGUIN_IP}:${HTTP_PORT}/hum-auto-install.preseed"
  log "  wget http://${PENGUIN_IP}:${HTTP_PORT}/fix-cdrom-corruption.sh"
}

teardown() {
  require_root
  log "Tearing down penguin namespace"
  stop_proxy
  ip link del "$VETH_HOST" 2>/dev/null || true
  ip -n "$NS_NAME" link del "$VETH_PEER" 2>/dev/null || true
  ip netns delete "$NS_NAME" 2>/dev/null || true
  rm -rf "/etc/netns/${NS_NAME}" 2>/dev/null || true
  log "Namespace $NS_NAME removed"
}

main() {
  local cmd="${1:-help}"
  case "$cmd" in
    setup)    setup_namespace ;;
    start)    start_proxy ;;
    stop)     stop_proxy ;;
    status)   show_status ;;
    serve)    serve_files ;;
    teardown) teardown ;;
    -h|--help|help) usage ;;
    *)
      err "Unknown command: $cmd"
      usage
      exit 1
      ;;
  esac
}

main "$@"
