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
ENABLE_PEER_CHAIN="${HUM_ENABLE_PEER_CHAIN:-1}"
PEER_NS="${HUM_PEER_NS:-hum-peer-ns}"
PEER_PROXY_IF="${HUM_PEER_PROXY_IF:-hum-peer-host0}"
PEER_NS_IF="${HUM_PEER_NS_IF:-hum-peer-ns0}"
PEER_PROXY_CIDR="${HUM_PEER_PROXY_CIDR:-10.200.0.5/30}"
PEER_NS_CIDR="${HUM_PEER_NS_CIDR:-10.200.0.6/30}"
PEER_DEFAULT_GW="${HUM_PEER_DEFAULT_GW:-10.200.0.5}"
PEER_CHAIN_SUBNET="${HUM_PEER_CHAIN_SUBNET:-10.200.0.4/30}"
PEER_PROXY_LL6="${HUM_PEER_PROXY_LL6:-fe80::5/64}"
PEER_NS_LL6="${HUM_PEER_NS_LL6:-fe80::6/64}"
PEER_CHAIN_ENABLE="${HUM_ENABLE_PEER_CHAIN:-1}"
PEER_NS="${HUM_PEER_NS:-hum-peer-ns}"
PROXY_PEER_IF="${HUM_PROXY_PEER_IF:-hum-proxy-peer0}"
PEER_NS_IF="${HUM_PEER_NS_IF:-hum-peer-ns0}"
PROXY_PEER_CIDR="${HUM_PROXY_PEER_CIDR:-10.200.1.1/30}"
PEER_NS_CIDR="${HUM_PEER_NS_CIDR:-10.200.1.2/30}"
PEER_DEFAULT_GW="${HUM_PEER_DEFAULT_GW:-10.200.1.1}"
PROXY_PEER_LL6="${HUM_PROXY_PEER_LL6:-fe80::11/64}"
PEER_NS_LL6="${HUM_PEER_NS_LL6:-fe80::12/64}"

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
  sudo bash scripts/hum-dev-netns.sh status --json
  sudo bash scripts/hum-dev-netns.sh trace
  sudo bash scripts/hum-dev-netns.sh plot
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
  HUM_PROXY_HOST_LL6
  HUM_PROXY_NS_LL6
  HUM_PEER_NS
  HUM_ENABLE_PEER_CHAIN
  HUM_PEER_NS
  HUM_PEER_PROXY_IF
  HUM_PEER_NS_IF
  HUM_PEER_PROXY_CIDR
  HUM_PEER_NS_CIDR
  HUM_PEER_DEFAULT_GW
  HUM_PEER_CHAIN_SUBNET
  HUM_PEER_PROXY_LL6
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

cidr_ip() {
  printf '%s\n' "${1%%/*}"
}

link_is_up() {
  ip -br link show dev "$1" 2>/dev/null | awk '{print $2}' | grep -q "UP"
}

ns_link_is_up() {
  ip -n "$1" -br link show dev "$2" 2>/dev/null | awk '{print $2}' | grep -q "UP"
}

is_truthy() {
  case "${1,,}" in
    1|true|yes|on)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

peer_chain_enabled() {
  is_truthy "$PEER_CHAIN_ENABLE"
}

peer_recv_ready() {
  netns_exists "$PROXY_NS" && \
    root_link_exists "$PROXY_HOST_IF" && \
    ns_link_exists "$PROXY_NS" "$PROXY_NS_IF" && \
    link_is_up "$PROXY_HOST_IF" && \
    ns_link_is_up "$PROXY_NS" "$PROXY_NS_IF"
}

peer_chain_enabled() {
  [[ "$ENABLE_PEER_CHAIN" != "0" ]]
}

peer_chain_recv_ready() {
  peer_chain_enabled && \
    netns_exists "$PROXY_NS" && \
    netns_exists "$PEER_NS" && \
    ns_link_exists "$PROXY_NS" "$PEER_PROXY_IF" && \
    ns_link_exists "$PEER_NS" "$PEER_NS_IF" && \
    ns_link_is_up "$PROXY_NS" "$PEER_PROXY_IF" && \
# True when ip -n can read interfaces in PROXY_NS (fails for non-root with EPERM).
netns_ip_n_readable() {
  ip -n "$PROXY_NS" link show lo >/dev/null 2>&1
}

# Sets HUM_PEER_HOST_STATE, HUM_PEER_NS_STATE, HUM_PEER_RECV_READY for display.
# Non-root users can list namespaces but usually cannot ip -n; avoid reporting "missing"
# when the netns exists and only introspection is blocked.
update_peer_chain_state() {
  HUM_PEER_HOST_STATE="missing"
  HUM_PEER_NS_STATE="missing"
  HUM_PEER_RECV_READY="no"

  if root_link_exists "$PROXY_HOST_IF"; then
    HUM_PEER_HOST_STATE="$(root_link_state "$PROXY_HOST_IF")"
  fi

  if ! netns_exists "$PROXY_NS"; then
    return 0
  fi

  if ! netns_ip_n_readable; then
    HUM_PEER_NS_STATE="unknown (sudo required for ip -n)"
    HUM_PEER_RECV_READY="unknown (sudo required for ip -n)"
    return 0
  fi

  if ns_link_exists "$PROXY_NS" "$PROXY_NS_IF"; then
    HUM_PEER_NS_STATE="$(ns_link_state "$PROXY_NS" "$PROXY_NS_IF")"
  else
    HUM_PEER_NS_STATE="missing"
  fi

  if peer_recv_ready; then
    HUM_PEER_RECV_READY="yes"
  else
    HUM_PEER_RECV_READY="no"
  fi
}

print_peer_veth_chain() {
  update_peer_chain_state

  echo "=== HUM peer veth chain ==="
  echo "root namespace"
  echo "  $PROXY_HOST_IF"
  echo "    ipv4: $PROXY_HOST_CIDR"
  echo "    ipv6: $PROXY_HOST_LL6"
  echo "    state: $HUM_PEER_HOST_STATE"
  echo "    || veth peer (recv-ready: $HUM_PEER_RECV_READY) ||"
  echo "netns $PROXY_NS"
  echo "  $PROXY_NS_IF"
  echo "    ipv4: $PROXY_NS_CIDR"
  echo "    ipv6: $PROXY_NS_LL6"
  echo "    default v4 -> $PROXY_DEFAULT_GW"
  echo "    default v6 -> ${PROXY_HOST_LL6%%/*}"
  echo "    state: $HUM_PEER_NS_STATE"
  echo "side links"
  echo "  dummy: $DUMMY_IF ($DUMMY_CIDR)"
  echo "  docker hint: $DOCKER_HINT_IF"
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

  if peer_chain_enabled; then
    if ! netns_exists "$PEER_NS"; then
      ip netns add "$PEER_NS"
    fi

    # Keep the peer chain coherent; recreate if either side is missing.
    if ! ns_link_exists "$PROXY_NS" "$PEER_PROXY_IF" || ! ns_link_exists "$PEER_NS" "$PEER_NS_IF"; then
      ip -n "$PROXY_NS" link del "$PEER_PROXY_IF" 2>/dev/null || true
      ip -n "$PEER_NS" link del "$PEER_NS_IF" 2>/dev/null || true
      ip -n "$PROXY_NS" link add "$PEER_PROXY_IF" type veth peer name "$PEER_NS_IF"
      ip -n "$PROXY_NS" link set "$PEER_NS_IF" netns "$PEER_NS"
    fi

    ip -n "$PROXY_NS" link set "$PEER_PROXY_IF" up
    ip -n "$PROXY_NS" addr replace "$PEER_PROXY_CIDR" dev "$PEER_PROXY_IF"
    ip -n "$PROXY_NS" -6 addr replace "$PEER_PROXY_LL6" dev "$PEER_PROXY_IF"
    ip netns exec "$PROXY_NS" sysctl -qw net.ipv4.ip_forward=1
    ip netns exec "$PROXY_NS" sysctl -qw net.ipv6.conf.all.forwarding=1
    if ! ns_link_exists "$PROXY_NS" "$PROXY_PEER_IF" || ! ns_link_exists "$PEER_NS" "$PEER_NS_IF"; then
      ip -n "$PROXY_NS" link del "$PROXY_PEER_IF" 2>/dev/null || true
      ip -n "$PEER_NS" link del "$PEER_NS_IF" 2>/dev/null || true
      ip -n "$PROXY_NS" link add "$PROXY_PEER_IF" type veth peer name "$PEER_NS_IF"
      ip -n "$PROXY_NS" link set "$PEER_NS_IF" netns "$PEER_NS"
    fi

    ip -n "$PROXY_NS" link set "$PROXY_PEER_IF" up
    ip -n "$PROXY_NS" addr replace "$PROXY_PEER_CIDR" dev "$PROXY_PEER_IF"
    ip -n "$PROXY_NS" -6 addr replace "$PROXY_PEER_LL6" dev "$PROXY_PEER_IF"

    ip -n "$PEER_NS" link set lo up
    ip -n "$PEER_NS" link set "$PEER_NS_IF" up
    ip -n "$PEER_NS" addr replace "$PEER_NS_CIDR" dev "$PEER_NS_IF"
    ip -n "$PEER_NS" -6 addr replace "$PEER_NS_LL6" dev "$PEER_NS_IF"
    ip -n "$PEER_NS" route replace default via "$PEER_DEFAULT_GW" dev "$PEER_NS_IF"
    ip -n "$PEER_NS" -6 route replace default via "${PEER_PROXY_LL6%%/*}" dev "$PEER_NS_IF"

    ip route replace "$PEER_CHAIN_SUBNET" via "$(cidr_ip "$PROXY_NS_CIDR")" dev "$PROXY_HOST_IF"
    ip -n "$PEER_NS" -6 route replace default via "${PROXY_PEER_LL6%%/*}" dev "$PEER_NS_IF"
  fi

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

  echo "=== HUM dev naming status ==="
  echo "proxy namespace: $PROXY_NS"
  echo "proxy links: host=$PROXY_HOST_IF ns=$PROXY_NS_IF"
  echo "dummy link: $DUMMY_IF"
  ip route del "${PEER_NS_CIDR%%/*}/32" via "${PROXY_NS_CIDR%%/*}" dev "$PROXY_HOST_IF" 2>/dev/null || true
  ip route del "$PEER_CHAIN_SUBNET" via "$(cidr_ip "$PROXY_NS_CIDR")" dev "$PROXY_HOST_IF" 2>/dev/null || true
  ip -n "$PROXY_NS" link del "$PEER_PROXY_IF" 2>/dev/null || true
  ip -n "$PROXY_NS" link del "$PROXY_PEER_IF" 2>/dev/null || true
  ip -n "$PEER_NS" link del "$PEER_NS_IF" 2>/dev/null || true
  ip netns delete "$PEER_NS" 2>/dev/null || true
  ip link del "$PROXY_HOST_IF" 2>/dev/null || true
  ip -n "$PROXY_NS" link del "$PROXY_NS_IF" 2>/dev/null || true
  ip netns delete "$PROXY_NS" 2>/dev/null || true
  echo "Removed dev namespace/interface naming setup."
}

status() {
  local host_mac ns_mac host_smac64 ns_smac64 host_rx ns_rx
  local proxy_peer_mac peer_ns_mac proxy_peer_smac64 peer_ns_smac64 proxy_peer_rx peer_ns_rx
  host_mac="$(iface_mac "$PROXY_HOST_IF" || true)"
  ns_mac="$(ns_iface_mac "$PROXY_NS" "$PROXY_NS_IF" || true)"
  host_smac64="$(smac64_from_mac "$host_mac")"
  ns_smac64="$(smac64_from_mac "$ns_mac")"
  host_rx="$(root_rx_packets "$PROXY_HOST_IF" || true)"
  ns_rx="$(ns_rx_packets "$PROXY_NS" "$PROXY_NS_IF" || true)"
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
  local host_mac ns_mac host_smac64 ns_smac64 host_rx ns_rx
  local peer_proxy_mac peer_ns_mac peer_proxy_smac64 peer_ns_smac64 peer_proxy_rx peer_ns_rx
  local proxy_peer_mac peer_ns_mac proxy_peer_smac64 peer_ns_smac64 proxy_peer_rx peer_ns_rx
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

  ns_rx="$(ns_rx_packets "$PROXY_NS" "$PROXY_NS_IF" || true)"
  peer_proxy_mac="$(ns_iface_mac "$PROXY_NS" "$PEER_PROXY_IF" || true)"
  peer_ns_mac="$(ns_iface_mac "$PEER_NS" "$PEER_NS_IF" || true)"
  peer_proxy_smac64="$(smac64_from_mac "$peer_proxy_mac")"
  peer_ns_smac64="$(smac64_from_mac "$peer_ns_mac")"
  peer_proxy_rx="$(ns_rx_packets "$PROXY_NS" "$PEER_PROXY_IF" || true)"
  peer_ns_rx="$(ns_rx_packets "$PEER_NS" "$PEER_NS_IF" || true)"

  proxy_peer_mac="$(ns_iface_mac "$PROXY_NS" "$PROXY_PEER_IF" || true)"
  peer_ns_mac="$(ns_iface_mac "$PEER_NS" "$PEER_NS_IF" || true)"
  proxy_peer_smac64="$(smac64_from_mac "$proxy_peer_mac")"
  peer_ns_smac64="$(smac64_from_mac "$peer_ns_mac")"
  proxy_peer_rx="$(ns_rx_packets "$PROXY_NS" "$PROXY_PEER_IF" || true)"
  peer_ns_rx="$(ns_rx_packets "$PEER_NS" "$PEER_NS_IF" || true)"

  print_peer_veth_chain
  echo
  echo "=== HUM dev naming status ==="
  echo "peer recv-ready: $HUM_PEER_RECV_READY"
  echo "proxy namespace: $PROXY_NS"
  echo "peer namespace: $PEER_NS"
  echo "proxy links: host=$PROXY_HOST_IF ns=$PROXY_NS_IF"
  echo "peer chain links: proxy=$PROXY_PEER_IF peer=$PEER_NS_IF"
  echo "peer namespace: $PEER_NS"
  echo "peer links: proxy=$PEER_PROXY_IF ns=$PEER_NS_IF"
  if peer_chain_enabled; then
    echo "peer chain: enabled"
    echo "peer namespace: $PEER_NS"
    echo "peer links: proxy=$PROXY_PEER_IF ns=$PEER_NS_IF"
  else
    echo "peer chain: disabled"
  fi
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
  if peer_chain_enabled; then
    if peer_chain_recv_ready; then
      echo "peer chain recv-ready: yes"
    else
      echo "peer chain recv-ready: no"
    fi
    echo "guidance: root -> $PROXY_NS -> $PEER_NS"
  else
    echo "peer chain recv-ready: disabled"
    echo "guidance: set HUM_ENABLE_PEER_CHAIN=1 to create a peer veth chain"
  fi
  echo "trace-smac64 host: $host_smac64"
  echo "trace-smac64 proxy:      $proxy_smac64"
  echo "trace-smac64 proxy-peer: $proxy_peer_smac64"
  echo "trace-smac64 peer:       $peer_smac64"
  echo "downstream nested packets (rx): host=${host_rx:-0} proxy=${proxy_rx:-0} proxy-peer=${proxy_peer_rx:-0} peer=${peer_rx:-0}"
  echo "trace-smac64 ns:   $ns_smac64"
  echo "downstream nested packets (rx): host=${host_rx:-0} ns=${ns_rx:-0}"
  if peer_chain_enabled; then
    echo "trace-smac64 peer-proxy: $peer_proxy_smac64"
    echo "trace-smac64 peer-ns:    $peer_ns_smac64"
    echo "peer chain packets (rx): proxy=${peer_proxy_rx:-0} peer=${peer_ns_rx:-0}"
  fi
  echo "trace-smac64 host: $host_smac64"
  echo "trace-smac64 ns:   $ns_smac64"
  if peer_chain_enabled; then
    echo "trace-smac64 peer-proxy: $proxy_peer_smac64"
    echo "trace-smac64 peer-ns:    $peer_ns_smac64"
    echo "downstream nested packets (rx): host=${host_rx:-0} proxy-main=${ns_rx:-0} proxy-peer=${proxy_peer_rx:-0} peer=${peer_ns_rx:-0}"
  else
    echo "downstream nested packets (rx): host=${host_rx:-0} ns=${ns_rx:-0}"
  fi
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
    if peer_chain_enabled; then
      echo "[netns:$PROXY_NS] $PROXY_PEER_IF"
      ip -n "$PROXY_NS" -br addr show dev "$PROXY_PEER_IF" 2>/dev/null || true
    fi
  else
    echo "Namespace $PROXY_NS does not exist."
  fi

  if peer_chain_enabled; then
    echo
    if netns_exists "$PEER_NS"; then
      echo "[netns:$PROXY_NS] $PEER_PROXY_IF"
      ip -n "$PROXY_NS" -br addr show dev "$PEER_PROXY_IF" 2>/dev/null || true
      echo
      echo "[root] peer chain route"
      ip route show "$PEER_CHAIN_SUBNET" 2>/dev/null || true
      echo
      echo "[netns:$PEER_NS] $PEER_NS_IF"
      ip -n "$PEER_NS" -br addr show dev "$PEER_NS_IF" 2>/dev/null || true
      echo "[netns:$PEER_NS] default route"
      ip -n "$PEER_NS" route show default 2>/dev/null || true
      echo "[netns:$PEER_NS] default route (IPv6)"
      ip -n "$PEER_NS" -6 route show default 2>/dev/null || true
    else
      echo "Namespace $PEER_NS does not exist."
    fi
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
}

status_json() {
  local ns_present docker_present
  local host_if_addr ns_if_addr dummy_if_addr docker_if_addr
  local ns_default_route host_mac ns_mac

  if netns_exists "$PROXY_NS"; then
    ns_present=true
    ns_default_route="$(ip -n "$PROXY_NS" route show default 2>/dev/null | tr -d '\n' || true)"
  else
    ns_present=false
    ns_default_route=""
  fi

  host_if_addr="$(ip -br addr show dev "$PROXY_HOST_IF" 2>/dev/null | tr -d '\n' || true)"
  ns_if_addr="$(ip -n "$PROXY_NS" -br addr show dev "$PROXY_NS_IF" 2>/dev/null | tr -d '\n' || true)"
  dummy_if_addr="$(ip -br addr show dev "$DUMMY_IF" 2>/dev/null | tr -d '\n' || true)"

  host_mac="$(ip -o link show "$PROXY_HOST_IF" 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i=="link/ether") {print $(i+1); exit}}' || true)"
  ns_mac="$(ip -n "$PROXY_NS" -o link show "$PROXY_NS_IF" 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i=="link/ether") {print $(i+1); exit}}' || true)"

  if root_link_exists "$DOCKER_HINT_IF"; then
    docker_present=true
    docker_if_addr="$(ip -br addr show dev "$DOCKER_HINT_IF" 2>/dev/null | tr -d '\n' || true)"
  else
    docker_present=false
    docker_if_addr=""
  fi

  python3 - "$PROXY_NS" "$PROXY_HOST_IF" "$PROXY_NS_IF" "$DUMMY_IF" "$DOCKER_HINT_IF" \
    "$ns_present" "$docker_present" "$host_if_addr" "$ns_if_addr" "$dummy_if_addr" "$docker_if_addr" \
    "$ns_default_route" "$host_mac" "$ns_mac" <<'PY'
import json
import sys

(
    proxy_ns,
    proxy_host_if,
    proxy_ns_if,
    dummy_if,
    docker_hint_if,
    ns_present,
    docker_present,
    host_if_addr,
    ns_if_addr,
    dummy_if_addr,
    docker_if_addr,
    ns_default_route,
    host_mac,
    ns_mac,
) = sys.argv[1:]

print(
    json.dumps(
        {
            "proxy_namespace": proxy_ns,
            "proxy_links": {"host": proxy_host_if, "namespace": proxy_ns_if},
            "dummy_link": dummy_if,
            "docker_hint_link": docker_hint_if,
            "namespace_present": ns_present == "true",
            "docker_hint_present": docker_present == "true",
            "addresses": {
                "host_proxy_if": host_if_addr,
                "ns_proxy_if": ns_if_addr,
                "dummy_if": dummy_if_addr,
                "docker_hint_if": docker_if_addr,
            },
            "routes": {"namespace_default": ns_default_route},
            "mac": {"host_proxy_if": host_mac, "ns_proxy_if": ns_mac},
        },
        indent=2,
    )
)
PY

  echo
  echo "[root] peer endpoint route"
  ip route show "${PEER_NS_CIDR%%/*}/32" 2>/dev/null || true
}

plot() {
  local root_proxy_state proxy_peer_state
  root_proxy_state="down"
  proxy_peer_state="down"
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "=== HUM merger plot ==="
    echo "[root] $PROXY_HOST_IF (${PROXY_HOST_CIDR}, ${PROXY_HOST_LL6})"
    echo "  | veth [requires root for live state]"
    echo "[netns:$PROXY_NS] $PROXY_NS_IF (${PROXY_NS_CIDR}, ${PROXY_NS_LL6})"
    echo "[netns:$PROXY_NS] $PROXY_PEER_IF (${PROXY_PEER_CIDR}, ${PROXY_PEER_LL6})"
    echo "  | veth [requires root for live state]"
    echo "[netns:$PEER_NS] $PEER_NS_IF (${PEER_NS_CIDR}, ${PEER_NS_LL6})"
    echo
    echo "guidance: use sudo for accurate merger state and peer-chain checks."
    echo "  sudo bash scripts/hum-dev-netns.sh plot"
    echo "  sudo bash scripts/hum-dev-netns.sh up"
    echo "  sudo bash scripts/hum-dev-netns.sh status"
    echo "  sudo bash scripts/hum-dev-netns.sh trace"
    return 0
  fi
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

guide() {
  print_peer_veth_chain
  echo
  echo "=== HUM peer veth chain guide ==="
  echo "Note: Without sudo, netns link state shows as unknown — use step 2 for authoritative output."
  echo
  echo "1. Create or repair the chain:"
  echo "   sudo bash scripts/hum-dev-netns.sh up"
  echo "2. Inspect the current peer state and addressing:"
  echo "   sudo bash scripts/hum-dev-netns.sh status"
  echo "3. Verify the netns can reach the host-side peer:"
  echo "   sudo ip netns exec $PROXY_NS ping -c 1 $PROXY_DEFAULT_GW"
  echo "   sudo ip netns exec $PROXY_NS ping -6 -I $PROXY_NS_IF -c 1 ${PROXY_HOST_LL6%%/*}"
  echo "   # Optional: zone-style link-local (some older ping builds):"
  echo "   # sudo ip netns exec $PROXY_NS ping -6 -c 1 ${PROXY_HOST_LL6%%/*}%$PROXY_NS_IF"
  echo "   # If IPv6 still fails while IPv4 works, ping the host veth's other fe80::/64 (EUI-64)"
  echo "   # from status output, and check ip6tables/nft and sysctl net.ipv6.icmp.echo_ignore_all."
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

  if peer_chain_enabled; then
    echo
    echo "[netns:$PROXY_NS] peer link counters"
    ip -n "$PROXY_NS" -s link show dev "$PEER_PROXY_IF" 2>/dev/null || true
    echo
    echo "[netns:$PEER_NS] link counters"
    ip -n "$PEER_NS" -s link show dev "$PEER_NS_IF" 2>/dev/null || true
    echo
    echo "[netns:$PEER_NS] IPv6 neighbors"
    ip -n "$PEER_NS" -6 neigh show dev "$PEER_NS_IF" 2>/dev/null || true
    echo
    echo "[netns:$PEER_NS] route table"
    ip -n "$PEER_NS" route show 2>/dev/null || true
    ip -n "$PEER_NS" -6 route show 2>/dev/null || true
    echo "[netns:$PROXY_NS] peer-link counters"
    ip -n "$PROXY_NS" -s link show dev "$PROXY_PEER_IF" 2>/dev/null || true
    if netns_exists "$PEER_NS"; then
      echo
      echo "[netns:$PEER_NS] link counters"
      ip -n "$PEER_NS" -s link show dev "$PEER_NS_IF" 2>/dev/null || true
      echo
      echo "[netns:$PEER_NS] IPv6 neighbors"
      ip -n "$PEER_NS" -6 neigh show dev "$PEER_NS_IF" 2>/dev/null || true
      echo
      echo "[netns:$PEER_NS] route table"
      ip -n "$PEER_NS" route show 2>/dev/null || true
      ip -n "$PEER_NS" -6 route show 2>/dev/null || true
    else
      echo
      echo "Namespace $PEER_NS does not exist; run 'up' first."
    fi
  fi

  if command -v tcpdump >/dev/null 2>&1 && [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    echo
    echo "[root] live capture ($TRACE_CAPTURE_SECONDS s, max $TRACE_CAPTURE_COUNT packets)"
    timeout "$TRACE_CAPTURE_SECONDS" tcpdump -n -i "$PROXY_HOST_IF" -c "$TRACE_CAPTURE_COUNT" \
      "ip or ip6" 2>/dev/null || true
    if peer_chain_enabled; then
      echo
      echo "[netns:$PROXY_NS] live capture on $PROXY_PEER_IF ($TRACE_CAPTURE_SECONDS s, max $TRACE_CAPTURE_COUNT packets)"
      timeout "$TRACE_CAPTURE_SECONDS" ip netns exec "$PROXY_NS" \
        tcpdump -n -i "$PROXY_PEER_IF" -c "$TRACE_CAPTURE_COUNT" "ip or ip6" 2>/dev/null || true
    fi
  fi
}

main() {
  local action="${1:-status}"
  local arg2="${2:-}"
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
      if [[ "$arg2" == "--json" ]]; then
        need_cmd python3
        status_json
      else
        status
      fi
      ;;
    trace)
      need_cmd ip
      trace
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
