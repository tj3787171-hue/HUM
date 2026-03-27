#!/usr/bin/env bash
set -euo pipefail

# Developer naming defaults (override with HUM_* environment variables).
PROXY_NS="${HUM_PROXY_NS:-hum-proxy-ns}"
PROXY_HOST_IF="${HUM_PROXY_HOST_IF:-hum-proxy-host0}"
PROXY_NS_IF="${HUM_PROXY_NS_IF:-hum-proxy-ns0}"
PROXY_HOST_CIDR="${HUM_PROXY_HOST_CIDR:-10.200.0.1/30}"
PROXY_NS_CIDR="${HUM_PROXY_NS_CIDR:-10.200.0.2/30}"
PROXY_DEFAULT_GW="${HUM_PROXY_DEFAULT_GW:-10.200.0.1}"
PROXY_HOST_LL6="${HUM_PROXY_HOST_LL6:-fe80::1/64}"
PROXY_NS_LL6="${HUM_PROXY_NS_LL6:-fe80::2/64}"

PEER_NS="${HUM_PEER_NS:-hum-peer-ns}"
PROXY_PEER_IF="${HUM_PROXY_PEER_IF:-hum-proxy-peer0}"
PEER_NS_IF="${HUM_PEER_NS_IF:-hum-peer-ns0}"
PROXY_PEER_CIDR="${HUM_PROXY_PEER_CIDR:-10.200.1.1/30}"
PEER_NS_CIDR="${HUM_PEER_NS_CIDR:-10.200.1.2/30}"
PEER_DEFAULT_GW="${HUM_PEER_DEFAULT_GW:-10.200.1.1}"
PROXY_PEER_LL6="${HUM_PROXY_PEER_LL6:-fe80::11/64}"
PEER_NS_LL6="${HUM_PEER_NS_LL6:-fe80::12/64}"

DUMMY_IF="${HUM_DUMMY_IF:-hum-dummy0}"
DUMMY_CIDR="${HUM_DUMMY_CIDR:-198.18.0.1/24}"

DOCKER_HINT_IF="${HUM_DOCKER_HINT_IF:-docker0}"
TRACE_CAPTURE_COUNT="${HUM_TRACE_CAPTURE_COUNT:-10}"
TRACE_CAPTURE_SECONDS="${HUM_TRACE_CAPTURE_SECONDS:-3}"

usage() {
  cat <<'EOF'
Usage:
  sudo bash scripts/hum-dev-netns.sh up
  sudo bash scripts/hum-dev-netns.sh down
  sudo bash scripts/hum-dev-netns.sh status
  sudo bash scripts/hum-dev-netns.sh trace
  sudo bash scripts/hum-dev-netns.sh plot

Optional environment overrides:
  HUM_PROXY_NS
  HUM_PROXY_HOST_IF
  HUM_PROXY_NS_IF
  HUM_PROXY_HOST_CIDR
  HUM_PROXY_NS_CIDR
  HUM_PROXY_DEFAULT_GW
  HUM_PROXY_HOST_LL6
  HUM_PROXY_NS_LL6
  HUM_PEER_NS
  HUM_PROXY_PEER_IF
  HUM_PEER_NS_IF
  HUM_PROXY_PEER_CIDR
  HUM_PEER_NS_CIDR
  HUM_PEER_DEFAULT_GW
  HUM_PROXY_PEER_LL6
  HUM_PEER_NS_LL6
  HUM_DUMMY_IF
  HUM_DUMMY_CIDR
  HUM_DOCKER_HINT_IF
  HUM_TRACE_CAPTURE_COUNT
  HUM_TRACE_CAPTURE_SECONDS
EOF
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

netns_exists() {
  local ns name
  ns="$1"
  while read -r name _; do
    [[ "$name" == "$ns" ]] && return 0
  done < <(ip netns list)
  return 1
}

root_link_exists() {
  ip link show "$1" >/dev/null 2>&1
}

ns_link_exists() {
  ip -n "$1" link show "$2" >/dev/null 2>&1
}

iface_mac() {
  ip -o link show dev "$1" 2>/dev/null | awk '{
    for (i = 1; i <= NF; i++) {
      if ($i == "link/ether") {
        print $(i + 1)
        exit
      }
    }
  }'
}

ns_iface_mac() {
  ip -n "$1" -o link show dev "$2" 2>/dev/null | awk '{
    for (i = 1; i <= NF; i++) {
      if ($i == "link/ether") {
        print $(i + 1)
        exit
      }
    }
  }'
}

smac64_from_mac() {
  local mac b1 b2 b3 b4 b5 b6
  mac="$1"
  if [[ ! "$mac" =~ ^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$ ]]; then
    echo "unknown"
    return 0
  fi
  IFS=':' read -r b1 b2 b3 b4 b5 b6 <<< "$mac"
  printf "%02x%s%sfffe%s%s%s" "$((16#$b1 ^ 2))" "$b2" "$b3" "$b4" "$b5" "$b6"
}

root_rx_packets() {
  ip -s link show dev "$1" 2>/dev/null | awk '/RX:/{getline; print $2; exit}'
}

ns_rx_packets() {
  ip -n "$1" -s link show dev "$2" 2>/dev/null | awk '/RX:/{getline; print $2; exit}'
}

link_is_up() {
  ip -br link show dev "$1" 2>/dev/null | awk '{print $2}' | grep -q "UP"
}

ns_link_is_up() {
  ip -n "$1" -br link show dev "$2" 2>/dev/null | awk '{print $2}' | grep -q "UP"
}

peer_recv_ready() {
  netns_exists "$PROXY_NS" && \
    root_link_exists "$PROXY_HOST_IF" && \
    ns_link_exists "$PROXY_NS" "$PROXY_NS_IF" && \
    link_is_up "$PROXY_HOST_IF" && \
    ns_link_is_up "$PROXY_NS" "$PROXY_NS_IF"
}

peer_chain_recv_ready() {
  netns_exists "$PROXY_NS" && \
    netns_exists "$PEER_NS" && \
    ns_link_exists "$PROXY_NS" "$PROXY_PEER_IF" && \
    ns_link_exists "$PEER_NS" "$PEER_NS_IF" && \
    ns_link_is_up "$PROXY_NS" "$PROXY_PEER_IF" && \
    ns_link_is_up "$PEER_NS" "$PEER_NS_IF"
}

enable_ns_forwarding() {
  local ns="$1"
  ip netns exec "$ns" sysctl -q -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || true
  ip netns exec "$ns" sysctl -q -w net.ipv6.conf.all.forwarding=1 >/dev/null 2>&1 || true
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "This action requires root. Re-run with sudo." >&2
    exit 1
  fi
}

up() {
  if ! netns_exists "$PROXY_NS"; then
    ip netns add "$PROXY_NS"
  fi
  if ! netns_exists "$PEER_NS"; then
    ip netns add "$PEER_NS"
  fi

  # Keep the pair coherent; recreate if either side is missing.
  if ! root_link_exists "$PROXY_HOST_IF" || ! ns_link_exists "$PROXY_NS" "$PROXY_NS_IF"; then
    ip link del "$PROXY_HOST_IF" 2>/dev/null || true
    ip -n "$PROXY_NS" link del "$PROXY_NS_IF" 2>/dev/null || true
    ip link add "$PROXY_HOST_IF" type veth peer name "$PROXY_NS_IF"
    ip link set "$PROXY_NS_IF" netns "$PROXY_NS"
  fi

  # Proxy namespace <-> peer namespace veth chain.
  if ! ns_link_exists "$PROXY_NS" "$PROXY_PEER_IF" || ! ns_link_exists "$PEER_NS" "$PEER_NS_IF"; then
    ip -n "$PROXY_NS" link del "$PROXY_PEER_IF" 2>/dev/null || true
    ip -n "$PEER_NS" link del "$PEER_NS_IF" 2>/dev/null || true
    ip link add "$PROXY_PEER_IF" type veth peer name "$PEER_NS_IF"
    ip link set "$PROXY_PEER_IF" netns "$PROXY_NS"
    ip link set "$PEER_NS_IF" netns "$PEER_NS"
  fi

  ip link set "$PROXY_HOST_IF" up
  ip addr replace "$PROXY_HOST_CIDR" dev "$PROXY_HOST_IF"
  ip -6 addr replace "$PROXY_HOST_LL6" dev "$PROXY_HOST_IF"

  ip -n "$PROXY_NS" link set lo up
  ip -n "$PROXY_NS" link set "$PROXY_NS_IF" up
  ip -n "$PROXY_NS" link set "$PROXY_PEER_IF" up
  ip -n "$PROXY_NS" addr replace "$PROXY_NS_CIDR" dev "$PROXY_NS_IF"
  ip -n "$PROXY_NS" -6 addr replace "$PROXY_NS_LL6" dev "$PROXY_NS_IF"
  ip -n "$PROXY_NS" addr replace "$PROXY_PEER_CIDR" dev "$PROXY_PEER_IF"
  ip -n "$PROXY_NS" -6 addr replace "$PROXY_PEER_LL6" dev "$PROXY_PEER_IF"
  ip -n "$PROXY_NS" route replace default via "$PROXY_DEFAULT_GW" dev "$PROXY_NS_IF"
  ip -n "$PROXY_NS" -6 route replace default via "${PROXY_HOST_LL6%%/*}" dev "$PROXY_NS_IF"
  enable_ns_forwarding "$PROXY_NS"

  ip -n "$PEER_NS" link set lo up
  ip -n "$PEER_NS" link set "$PEER_NS_IF" up
  ip -n "$PEER_NS" addr replace "$PEER_NS_CIDR" dev "$PEER_NS_IF"
  ip -n "$PEER_NS" -6 addr replace "$PEER_NS_LL6" dev "$PEER_NS_IF"
  ip -n "$PEER_NS" route replace default via "$PEER_DEFAULT_GW" dev "$PEER_NS_IF"
  ip -n "$PEER_NS" -6 route replace default via "${PROXY_PEER_LL6%%/*}" dev "$PEER_NS_IF"

  # Let the root namespace reply to peer namespace IPs through proxy.
  ip route replace "${PEER_NS_CIDR%%/*}/32" via "${PROXY_NS_CIDR%%/*}" dev "$PROXY_HOST_IF"

  if ! root_link_exists "$DUMMY_IF"; then
    if ! ip link add "$DUMMY_IF" type dummy 2>/dev/null; then
      echo "Warning: dummy interface type is unavailable; skipping $DUMMY_IF." >&2
    fi
  fi
  if root_link_exists "$DUMMY_IF"; then
    ip link set "$DUMMY_IF" up
    ip addr replace "$DUMMY_CIDR" dev "$DUMMY_IF"
  fi

  status
}

down() {
  ip link del "$DUMMY_IF" 2>/dev/null || true
  ip route del "${PEER_NS_CIDR%%/*}/32" via "${PROXY_NS_CIDR%%/*}" dev "$PROXY_HOST_IF" 2>/dev/null || true
  ip link del "$PROXY_HOST_IF" 2>/dev/null || true
  ip -n "$PROXY_NS" link del "$PROXY_PEER_IF" 2>/dev/null || true
  ip -n "$PROXY_NS" link del "$PROXY_NS_IF" 2>/dev/null || true
  ip -n "$PEER_NS" link del "$PEER_NS_IF" 2>/dev/null || true
  ip netns delete "$PEER_NS" 2>/dev/null || true
  ip netns delete "$PROXY_NS" 2>/dev/null || true
  echo "Removed dev namespace/interface naming setup (proxy + peer chain)."
}

status() {
  local host_mac proxy_mac proxy_peer_mac peer_mac
  local host_smac64 proxy_smac64 proxy_peer_smac64 peer_smac64
  local host_rx proxy_rx proxy_peer_rx peer_rx
  host_mac="$(iface_mac "$PROXY_HOST_IF" || true)"
  proxy_mac="$(ns_iface_mac "$PROXY_NS" "$PROXY_NS_IF" || true)"
  proxy_peer_mac="$(ns_iface_mac "$PROXY_NS" "$PROXY_PEER_IF" || true)"
  peer_mac="$(ns_iface_mac "$PEER_NS" "$PEER_NS_IF" || true)"
  host_smac64="$(smac64_from_mac "$host_mac")"
  proxy_smac64="$(smac64_from_mac "$proxy_mac")"
  proxy_peer_smac64="$(smac64_from_mac "$proxy_peer_mac")"
  peer_smac64="$(smac64_from_mac "$peer_mac")"
  host_rx="$(root_rx_packets "$PROXY_HOST_IF" || true)"
  proxy_rx="$(ns_rx_packets "$PROXY_NS" "$PROXY_NS_IF" || true)"
  proxy_peer_rx="$(ns_rx_packets "$PROXY_NS" "$PROXY_PEER_IF" || true)"
  peer_rx="$(ns_rx_packets "$PEER_NS" "$PEER_NS_IF" || true)"

  echo "=== HUM dev naming status ==="
  echo "proxy namespace: $PROXY_NS"
  echo "peer namespace: $PEER_NS"
  echo "proxy links: host=$PROXY_HOST_IF ns=$PROXY_NS_IF"
  echo "peer chain links: proxy=$PROXY_PEER_IF peer=$PEER_NS_IF"
  echo "dummy link: $DUMMY_IF"
  if peer_recv_ready; then
    echo "peer recv-ready root<->proxy: yes"
  else
    echo "peer recv-ready root<->proxy: no"
  fi
  if peer_chain_recv_ready; then
    echo "peer recv-ready proxy<->peer: yes"
  else
    echo "peer recv-ready proxy<->peer: no"
  fi
  echo "trace-smac64 host: $host_smac64"
  echo "trace-smac64 proxy:      $proxy_smac64"
  echo "trace-smac64 proxy-peer: $proxy_peer_smac64"
  echo "trace-smac64 peer:       $peer_smac64"
  echo "downstream nested packets (rx): host=${host_rx:-0} proxy=${proxy_rx:-0} proxy-peer=${proxy_peer_rx:-0} peer=${peer_rx:-0}"
  echo

  if netns_exists "$PROXY_NS"; then
    echo "[root] $PROXY_HOST_IF"
    ip -br addr show dev "$PROXY_HOST_IF" 2>/dev/null || true
    echo
    echo "[netns:$PROXY_NS] $PROXY_NS_IF"
    ip -n "$PROXY_NS" -br addr show dev "$PROXY_NS_IF" 2>/dev/null || true
    echo "[netns:$PROXY_NS] $PROXY_PEER_IF"
    ip -n "$PROXY_NS" -br addr show dev "$PROXY_PEER_IF" 2>/dev/null || true
    echo "[netns:$PROXY_NS] default route"
    ip -n "$PROXY_NS" route show default 2>/dev/null || true
    echo "[netns:$PROXY_NS] default route (IPv6)"
    ip -n "$PROXY_NS" -6 route show default 2>/dev/null || true
  else
    echo "Namespace $PROXY_NS does not exist."
  fi

  echo
  if netns_exists "$PEER_NS"; then
    echo "[netns:$PEER_NS] $PEER_NS_IF"
    ip -n "$PEER_NS" -br addr show dev "$PEER_NS_IF" 2>/dev/null || true
    echo "[netns:$PEER_NS] default route"
    ip -n "$PEER_NS" route show default 2>/dev/null || true
    echo "[netns:$PEER_NS] default route (IPv6)"
    ip -n "$PEER_NS" -6 route show default 2>/dev/null || true
  else
    echo "Namespace $PEER_NS does not exist."
  fi

  echo
  echo "[root] dummy"
  ip -br addr show dev "$DUMMY_IF" 2>/dev/null || true

  echo
  if root_link_exists "$DOCKER_HINT_IF"; then
    echo "[root] docker hint interface found: $DOCKER_HINT_IF"
    ip -br addr show dev "$DOCKER_HINT_IF" 2>/dev/null || true
  else
    echo "[root] docker hint interface not found: $DOCKER_HINT_IF"
  fi

  echo
  echo "[root] peer endpoint route"
  ip route show "${PEER_NS_CIDR%%/*}/32" 2>/dev/null || true
}

plot() {
  local root_proxy_state proxy_peer_state
  root_proxy_state="down"
  proxy_peer_state="down"
  if peer_recv_ready; then
    root_proxy_state="up"
  fi
  if peer_chain_recv_ready; then
    proxy_peer_state="up"
  fi

  echo "=== HUM merger plot ==="
  echo "[root] $PROXY_HOST_IF (${PROXY_HOST_CIDR}, ${PROXY_HOST_LL6})"
  echo "  | veth [$root_proxy_state]"
  echo "[netns:$PROXY_NS] $PROXY_NS_IF (${PROXY_NS_CIDR}, ${PROXY_NS_LL6})"
  echo "[netns:$PROXY_NS] $PROXY_PEER_IF (${PROXY_PEER_CIDR}, ${PROXY_PEER_LL6})"
  echo "  | veth [$proxy_peer_state]"
  echo "[netns:$PEER_NS] $PEER_NS_IF (${PEER_NS_CIDR}, ${PEER_NS_LL6})"
  echo

  if [[ "$root_proxy_state" == "up" && "$proxy_peer_state" == "up" ]]; then
    echo "guidance: peer veth chain is ready."
    echo "  sudo ip netns exec $PEER_NS ping -c 2 ${PROXY_PEER_CIDR%%/*}"
    echo "  sudo ip netns exec $PEER_NS ping -c 2 ${PROXY_HOST_CIDR%%/*}"
    echo "  sudo bash scripts/hum-dev-netns.sh trace"
  else
    echo "guidance: bring chain up then inspect."
    echo "  sudo bash scripts/hum-dev-netns.sh up"
    echo "  sudo bash scripts/hum-dev-netns.sh status"
    echo "  sudo bash scripts/hum-dev-netns.sh trace"
  fi
}

trace() {
  status
  echo
  echo "=== HUM downstream trace ==="
  if ! netns_exists "$PROXY_NS"; then
    echo "Namespace $PROXY_NS does not exist; run 'up' first."
    return 1
  fi

  echo "[root] link counters"
  ip -s link show dev "$PROXY_HOST_IF" 2>/dev/null || true
  echo
  echo "[netns:$PROXY_NS] link counters"
  ip -n "$PROXY_NS" -s link show dev "$PROXY_NS_IF" 2>/dev/null || true
  echo
  echo "[netns:$PROXY_NS] chain link counters"
  ip -n "$PROXY_NS" -s link show dev "$PROXY_PEER_IF" 2>/dev/null || true
  echo
  echo "[netns:$PEER_NS] chain link counters"
  ip -n "$PEER_NS" -s link show dev "$PEER_NS_IF" 2>/dev/null || true
  echo
  echo "[netns:$PROXY_NS] IPv6 neighbors"
  ip -n "$PROXY_NS" -6 neigh show dev "$PROXY_NS_IF" 2>/dev/null || true
  echo
  echo "[netns:$PROXY_NS] IPv6 neighbors (chain)"
  ip -n "$PROXY_NS" -6 neigh show dev "$PROXY_PEER_IF" 2>/dev/null || true
  echo
  echo "[netns:$PEER_NS] IPv6 neighbors"
  ip -n "$PEER_NS" -6 neigh show dev "$PEER_NS_IF" 2>/dev/null || true
  echo
  echo "[netns:$PROXY_NS] route table"
  ip -n "$PROXY_NS" route show 2>/dev/null || true
  ip -n "$PROXY_NS" -6 route show 2>/dev/null || true
  echo
  echo "[netns:$PEER_NS] route table"
  ip -n "$PEER_NS" route show 2>/dev/null || true
  ip -n "$PEER_NS" -6 route show 2>/dev/null || true

  if command -v tcpdump >/dev/null 2>&1 && [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    echo
    echo "[root] live capture ($TRACE_CAPTURE_SECONDS s, max $TRACE_CAPTURE_COUNT packets)"
    timeout "$TRACE_CAPTURE_SECONDS" tcpdump -n -i "$PROXY_HOST_IF" -c "$TRACE_CAPTURE_COUNT" \
      "ip or ip6" 2>/dev/null || true
  fi
}

main() {
  local action="${1:-status}"
  case "$action" in
    up)
      need_cmd ip
      require_root
      up
      ;;
    down)
      need_cmd ip
      require_root
      down
      ;;
    status)
      need_cmd ip
      status
      ;;
    trace)
      need_cmd ip
      trace
      ;;
    plot)
      need_cmd ip
      plot
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
