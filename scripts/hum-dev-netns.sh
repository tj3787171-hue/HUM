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
  bash scripts/hum-dev-netns.sh guide

Optional environment overrides:
  HUM_PROXY_NS
  HUM_PROXY_HOST_IF
  HUM_PROXY_NS_IF
  HUM_PROXY_HOST_CIDR
  HUM_PROXY_NS_CIDR
  HUM_PROXY_DEFAULT_GW
  HUM_PROXY_HOST_LL6
  HUM_PROXY_NS_LL6
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

root_link_state() {
  ip -br link show dev "$1" 2>/dev/null | awk '{print $2}'
}

ns_link_state() {
  ip -n "$1" -br link show dev "$2" 2>/dev/null | awk '{print $2}'
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

print_peer_veth_chain() {
  local host_state="missing" ns_state="missing" recv_ready="no"

  if root_link_exists "$PROXY_HOST_IF"; then
    host_state="$(root_link_state "$PROXY_HOST_IF")"
  fi
  if netns_exists "$PROXY_NS" && ns_link_exists "$PROXY_NS" "$PROXY_NS_IF"; then
    ns_state="$(ns_link_state "$PROXY_NS" "$PROXY_NS_IF")"
  fi
  if peer_recv_ready; then
    recv_ready="yes"
  fi

  echo "=== HUM peer veth chain ==="
  echo "root namespace"
  echo "  $PROXY_HOST_IF"
  echo "    ipv4: $PROXY_HOST_CIDR"
  echo "    ipv6: $PROXY_HOST_LL6"
  echo "    state: $host_state"
  echo "    || veth peer (recv-ready: $recv_ready) ||"
  echo "netns $PROXY_NS"
  echo "  $PROXY_NS_IF"
  echo "    ipv4: $PROXY_NS_CIDR"
  echo "    ipv6: $PROXY_NS_LL6"
  echo "    default v4 -> $PROXY_DEFAULT_GW"
  echo "    default v6 -> ${PROXY_HOST_LL6%%/*}"
  echo "    state: $ns_state"
  echo "side links"
  echo "  dummy: $DUMMY_IF ($DUMMY_CIDR)"
  echo "  docker hint: $DOCKER_HINT_IF"
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

  # Keep the pair coherent; recreate if either side is missing.
  if ! root_link_exists "$PROXY_HOST_IF" || ! ns_link_exists "$PROXY_NS" "$PROXY_NS_IF"; then
    ip link del "$PROXY_HOST_IF" 2>/dev/null || true
    ip -n "$PROXY_NS" link del "$PROXY_NS_IF" 2>/dev/null || true
    ip link add "$PROXY_HOST_IF" type veth peer name "$PROXY_NS_IF"
    ip link set "$PROXY_NS_IF" netns "$PROXY_NS"
  fi

  ip link set "$PROXY_HOST_IF" up
  ip addr replace "$PROXY_HOST_CIDR" dev "$PROXY_HOST_IF"
  ip -6 addr replace "$PROXY_HOST_LL6" dev "$PROXY_HOST_IF"

  ip -n "$PROXY_NS" link set lo up
  ip -n "$PROXY_NS" link set "$PROXY_NS_IF" up
  ip -n "$PROXY_NS" addr replace "$PROXY_NS_CIDR" dev "$PROXY_NS_IF"
  ip -n "$PROXY_NS" -6 addr replace "$PROXY_NS_LL6" dev "$PROXY_NS_IF"
  ip -n "$PROXY_NS" route replace default via "$PROXY_DEFAULT_GW" dev "$PROXY_NS_IF"
  ip -n "$PROXY_NS" -6 route replace default via "${PROXY_HOST_LL6%%/*}" dev "$PROXY_NS_IF"

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
  echo
  echo "Run 'bash scripts/hum-dev-netns.sh guide' for the peer veth chain walk-through."
}

down() {
  ip link del "$DUMMY_IF" 2>/dev/null || true
  ip link del "$PROXY_HOST_IF" 2>/dev/null || true
  ip -n "$PROXY_NS" link del "$PROXY_NS_IF" 2>/dev/null || true
  ip netns delete "$PROXY_NS" 2>/dev/null || true
  echo "Removed dev namespace/interface naming setup."
}

status() {
  local host_mac ns_mac host_smac64 ns_smac64 host_rx ns_rx
  host_mac="$(iface_mac "$PROXY_HOST_IF" || true)"
  ns_mac="$(ns_iface_mac "$PROXY_NS" "$PROXY_NS_IF" || true)"
  host_smac64="$(smac64_from_mac "$host_mac")"
  ns_smac64="$(smac64_from_mac "$ns_mac")"
  host_rx="$(root_rx_packets "$PROXY_HOST_IF" || true)"
  ns_rx="$(ns_rx_packets "$PROXY_NS" "$PROXY_NS_IF" || true)"

  print_peer_veth_chain
  echo
  echo "=== HUM dev naming status ==="
  if peer_recv_ready; then
    echo "peer recv-ready: yes"
  else
    echo "peer recv-ready: no"
  fi
  echo "trace-smac64 host: $host_smac64"
  echo "trace-smac64 ns:   $ns_smac64"
  echo "downstream nested packets (rx): host=${host_rx:-0} ns=${ns_rx:-0}"
  echo

  if netns_exists "$PROXY_NS"; then
    echo "[root] $PROXY_HOST_IF"
    ip -br addr show dev "$PROXY_HOST_IF" 2>/dev/null || true
    echo
    echo "[netns:$PROXY_NS] $PROXY_NS_IF"
    ip -n "$PROXY_NS" -br addr show dev "$PROXY_NS_IF" 2>/dev/null || true
    echo "[netns:$PROXY_NS] default route"
    ip -n "$PROXY_NS" route show default 2>/dev/null || true
    echo "[netns:$PROXY_NS] default route (IPv6)"
    ip -n "$PROXY_NS" -6 route show default 2>/dev/null || true
  else
    echo "Namespace $PROXY_NS does not exist."
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
}

guide() {
  print_peer_veth_chain
  echo
  echo "=== HUM peer veth chain guide ==="
  echo "1. Create or repair the chain:"
  echo "   sudo bash scripts/hum-dev-netns.sh up"
  echo "2. Inspect the current peer state and addressing:"
  echo "   sudo bash scripts/hum-dev-netns.sh status"
  echo "3. Verify the netns can reach the host-side peer:"
  echo "   sudo ip netns exec $PROXY_NS ping -c 1 $PROXY_DEFAULT_GW"
  echo "   sudo ip netns exec $PROXY_NS ping -6 -c 1 ${PROXY_HOST_LL6%%/*}%$PROXY_NS_IF"
  echo "4. Inspect counters, routes, neighbors, and optional capture output:"
  echo "   sudo bash scripts/hum-dev-netns.sh trace"
  echo "5. Remove the peer veth chain when done:"
  echo "   sudo bash scripts/hum-dev-netns.sh down"
  echo
  echo "Override names and addresses with the HUM_* variables listed in:"
  echo "   bash scripts/hum-dev-netns.sh --help"
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
  echo "[netns:$PROXY_NS] IPv6 neighbors"
  ip -n "$PROXY_NS" -6 neigh show dev "$PROXY_NS_IF" 2>/dev/null || true
  echo
  echo "[netns:$PROXY_NS] route table"
  ip -n "$PROXY_NS" route show 2>/dev/null || true
  ip -n "$PROXY_NS" -6 route show 2>/dev/null || true

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
    guide)
      need_cmd ip
      guide
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
