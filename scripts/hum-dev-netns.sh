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
PEER_CHAIN_ENABLE="${HUM_ENABLE_PEER_CHAIN:-1}"
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
  sudo bash scripts/hum-dev-netns.sh collect   # JSON snapshot for telemetry DB

Optional environment overrides:
  HUM_PROXY_NS
  HUM_PROXY_HOST_IF
  HUM_PROXY_NS_IF
  HUM_PROXY_HOST_CIDR
  HUM_PROXY_NS_CIDR
  HUM_PROXY_DEFAULT_GW
  HUM_PROXY_HOST_LL6
  HUM_PROXY_NS_LL6
  HUM_ENABLE_PEER_CHAIN
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

peer_chain_recv_ready() {
  netns_exists "$PROXY_NS" && \
    netns_exists "$PEER_NS" && \
    ns_link_exists "$PROXY_NS" "$PROXY_PEER_IF" && \
    ns_link_exists "$PEER_NS" "$PEER_NS_IF" && \
    ns_link_is_up "$PROXY_NS" "$PROXY_PEER_IF" && \
    ns_link_is_up "$PEER_NS" "$PEER_NS_IF"
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

  if peer_chain_enabled; then
    if ! netns_exists "$PEER_NS"; then
      ip netns add "$PEER_NS"
    fi

    # Keep the peer chain coherent; recreate if either side is missing.
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
}

down() {
  ip link del "$DUMMY_IF" 2>/dev/null || true
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
  proxy_peer_mac="$(ns_iface_mac "$PROXY_NS" "$PROXY_PEER_IF" || true)"
  peer_ns_mac="$(ns_iface_mac "$PEER_NS" "$PEER_NS_IF" || true)"
  proxy_peer_smac64="$(smac64_from_mac "$proxy_peer_mac")"
  peer_ns_smac64="$(smac64_from_mac "$peer_ns_mac")"
  proxy_peer_rx="$(ns_rx_packets "$PROXY_NS" "$PROXY_PEER_IF" || true)"
  peer_ns_rx="$(ns_rx_packets "$PEER_NS" "$PEER_NS_IF" || true)"

  echo "=== HUM dev naming status ==="
  echo "proxy namespace: $PROXY_NS"
  echo "proxy links: host=$PROXY_HOST_IF ns=$PROXY_NS_IF"
  if peer_chain_enabled; then
    echo "peer chain: enabled"
    echo "peer namespace: $PEER_NS"
    echo "peer links: proxy=$PROXY_PEER_IF ns=$PEER_NS_IF"
  else
    echo "peer chain: disabled"
  fi
  echo "dummy link: $DUMMY_IF"
  if peer_recv_ready; then
    echo "peer recv-ready: yes"
  else
    echo "peer recv-ready: no"
  fi
  if peer_chain_enabled; then
    if peer_chain_recv_ready; then
      echo "peer chain recv-ready: yes"
    else
      echo "peer chain recv-ready: no"
    fi
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

  if peer_chain_enabled; then
    echo
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

# ---------------------------------------------------------------------------
# collect – emit structured JSON snapshot for telemetry DB ingestion
# ---------------------------------------------------------------------------

json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }

stat_field() {
  ip -n "$1" -s link show dev "$2" 2>/dev/null | awk "/$3/"'{getline; print $2; exit}'
}

root_stat_field() {
  ip -s link show dev "$1" 2>/dev/null | awk "/$2/"'{getline; print $2; exit}'
}

root_tx_packets() { root_stat_field "$1" "TX:"; }
ns_tx_packets()   { stat_field "$1" "$2" "TX:"; }

collect() {
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"

  local chain_on=false pr=false cr=false
  peer_chain_enabled && chain_on=true
  peer_recv_ready && pr=true
  [[ "$chain_on" == "true" ]] && peer_chain_recv_ready && cr=true

  # --- hops ---
  local hops=""
  local m s
  m="$(iface_mac "$PROXY_HOST_IF" 2>/dev/null || true)"
  s="$(smac64_from_mac "$m")"
  hops="$hops{\"role\":\"host\",\"namespace\":\"root\",\"interface\":\"$(json_escape "$PROXY_HOST_IF")\",\"mac\":\"$m\",\"smac64\":\"$s\",\"ipv4_cidr\":\"$PROXY_HOST_CIDR\",\"ipv6_cidr\":\"${PROXY_HOST_LL6}\",\"link_up\":$(link_is_up "$PROXY_HOST_IF" && echo true || echo false)}"

  m="$(ns_iface_mac "$PROXY_NS" "$PROXY_NS_IF" 2>/dev/null || true)"
  s="$(smac64_from_mac "$m")"
  hops="$hops,{\"role\":\"proxy-main\",\"namespace\":\"$(json_escape "$PROXY_NS")\",\"interface\":\"$(json_escape "$PROXY_NS_IF")\",\"mac\":\"$m\",\"smac64\":\"$s\",\"ipv4_cidr\":\"$PROXY_NS_CIDR\",\"ipv6_cidr\":\"${PROXY_NS_LL6}\",\"link_up\":$(ns_link_is_up "$PROXY_NS" "$PROXY_NS_IF" && echo true || echo false)}"

  if [[ "$chain_on" == "true" ]]; then
    m="$(ns_iface_mac "$PROXY_NS" "$PROXY_PEER_IF" 2>/dev/null || true)"
    s="$(smac64_from_mac "$m")"
    hops="$hops,{\"role\":\"proxy-peer\",\"namespace\":\"$(json_escape "$PROXY_NS")\",\"interface\":\"$(json_escape "$PROXY_PEER_IF")\",\"mac\":\"$m\",\"smac64\":\"$s\",\"ipv4_cidr\":\"$PROXY_PEER_CIDR\",\"ipv6_cidr\":\"${PROXY_PEER_LL6}\",\"link_up\":$(ns_link_is_up "$PROXY_NS" "$PROXY_PEER_IF" && echo true || echo false)}"

    m="$(ns_iface_mac "$PEER_NS" "$PEER_NS_IF" 2>/dev/null || true)"
    s="$(smac64_from_mac "$m")"
    hops="$hops,{\"role\":\"peer\",\"namespace\":\"$(json_escape "$PEER_NS")\",\"interface\":\"$(json_escape "$PEER_NS_IF")\",\"mac\":\"$m\",\"smac64\":\"$s\",\"ipv4_cidr\":\"$PEER_NS_CIDR\",\"ipv6_cidr\":\"${PEER_NS_LL6}\",\"link_up\":$(ns_link_is_up "$PEER_NS" "$PEER_NS_IF" && echo true || echo false)}"
  fi

  # --- counters ---
  local ctrs=""
  local rx tx
  rx="$(root_rx_packets "$PROXY_HOST_IF" 2>/dev/null || true)"
  tx="$(root_tx_packets "$PROXY_HOST_IF" 2>/dev/null || true)"
  ctrs="{\"role\":\"host\",\"rx_packets\":${rx:-0},\"tx_packets\":${tx:-0}}"

  rx="$(ns_rx_packets "$PROXY_NS" "$PROXY_NS_IF" 2>/dev/null || true)"
  tx="$(ns_tx_packets "$PROXY_NS" "$PROXY_NS_IF" 2>/dev/null || true)"
  ctrs="$ctrs,{\"role\":\"proxy-main\",\"rx_packets\":${rx:-0},\"tx_packets\":${tx:-0}}"

  if [[ "$chain_on" == "true" ]]; then
    rx="$(ns_rx_packets "$PROXY_NS" "$PROXY_PEER_IF" 2>/dev/null || true)"
    tx="$(ns_tx_packets "$PROXY_NS" "$PROXY_PEER_IF" 2>/dev/null || true)"
    ctrs="$ctrs,{\"role\":\"proxy-peer\",\"rx_packets\":${rx:-0},\"tx_packets\":${tx:-0}}"

    rx="$(ns_rx_packets "$PEER_NS" "$PEER_NS_IF" 2>/dev/null || true)"
    tx="$(ns_tx_packets "$PEER_NS" "$PEER_NS_IF" 2>/dev/null || true)"
    ctrs="$ctrs,{\"role\":\"peer\",\"rx_packets\":${rx:-0},\"tx_packets\":${tx:-0}}"
  fi

  # --- routes ---
  local rts=""
  local first_rt=1
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    local dst gw dev
    dst="$(echo "$line" | awk '{print $1}')"
    gw="$(echo "$line" | awk '/via/{for(i=1;i<=NF;i++) if($i=="via") print $(i+1)}')"
    dev="$(echo "$line" | awk '/dev/{for(i=1;i<=NF;i++) if($i=="dev") print $(i+1)}')"
    [[ "$first_rt" -eq 0 ]] && rts="$rts,"
    rts="$rts{\"namespace\":\"$(json_escape "$PROXY_NS")\",\"family\":\"inet\",\"destination\":\"$(json_escape "$dst")\",\"gateway\":\"$(json_escape "${gw:-}")\",\"device\":\"$(json_escape "${dev:-}")\"}"
    first_rt=0
  done < <(ip -n "$PROXY_NS" route show 2>/dev/null || true)

  if [[ "$chain_on" == "true" ]]; then
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      local dst gw dev
      dst="$(echo "$line" | awk '{print $1}')"
      gw="$(echo "$line" | awk '/via/{for(i=1;i<=NF;i++) if($i=="via") print $(i+1)}')"
      dev="$(echo "$line" | awk '/dev/{for(i=1;i<=NF;i++) if($i=="dev") print $(i+1)}')"
      [[ "$first_rt" -eq 0 ]] && rts="$rts,"
      rts="$rts{\"namespace\":\"$(json_escape "$PEER_NS")\",\"family\":\"inet\",\"destination\":\"$(json_escape "$dst")\",\"gateway\":\"$(json_escape "${gw:-}")\",\"device\":\"$(json_escape "${dev:-}")\"}"
      first_rt=0
    done < <(ip -n "$PEER_NS" route show 2>/dev/null || true)
  fi

  # --- topology summary ---
  local topo
  if [[ "$chain_on" == "true" ]]; then
    topo="{\"chain\":\"root > $PROXY_HOST_IF <-> $PROXY_NS_IF > $PROXY_PEER_IF <-> $PEER_NS_IF\",\"dummy\":\"$DUMMY_IF ($DUMMY_CIDR)\"}"
  else
    topo="{\"chain\":\"root > $PROXY_HOST_IF <-> $PROXY_NS_IF\",\"dummy\":\"$DUMMY_IF ($DUMMY_CIDR)\"}"
  fi

  # --- assemble ---
  cat <<ENDJSON
{"captured_at":"$ts","peer_chain_enabled":$chain_on,"peer_recv_ready":$pr,"peer_chain_recv_ready":$cr,"topology":$topo,"hops":[$hops],"counters":[$ctrs],"routes":[$rts]}
ENDJSON
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
    collect)
      need_cmd ip
      collect
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
