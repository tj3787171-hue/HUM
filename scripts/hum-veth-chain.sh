#!/usr/bin/env bash
set -euo pipefail

# Peer veth chain: N namespaces connected in series by veth pairs.
#
#   [root] --veth-- [ns-1] --veth-- [ns-2] --veth-- ... --veth-- [ns-N]
#
# Each hop is a /30 IPv4 subnet plus link-local IPv6.  Traffic entering
# one end of the chain can be forwarded hop-by-hop to the other end,
# modelling a multi-hop proxy/merger topology.

CHAIN_PREFIX="${HUM_CHAIN_PREFIX:-hum-chain}"
CHAIN_LENGTH="${HUM_CHAIN_LENGTH:-3}"
CHAIN_BASE_NET="${HUM_CHAIN_BASE_NET:-10.201}"

usage() {
  cat <<'EOF'
Usage:
  sudo bash scripts/hum-veth-chain.sh up   [--length N]
  sudo bash scripts/hum-veth-chain.sh down  [--length N]
  sudo bash scripts/hum-veth-chain.sh status [--length N]
  sudo bash scripts/hum-veth-chain.sh plot   [--length N]

Actions:
  up      Create the peer veth chain (default 3 hops).
  down    Tear down the chain.
  status  Print addressing and peer-readiness for every hop.
  plot    Print an ASCII merger-plot diagram of the chain.

Options:
  --length N   Number of namespaces in the chain (default 3, max 16).

Environment overrides:
  HUM_CHAIN_PREFIX      Namespace/interface name prefix (default: hum-chain)
  HUM_CHAIN_LENGTH      Number of chain hops            (default: 3)
  HUM_CHAIN_BASE_NET    First two octets of IPv4 space  (default: 10.201)
EOF
}

# ── helpers ──────────────────────────────────────────────────────────

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

netns_exists() {
  local ns name
  ns="$1"
  while read -r name _; do
    [[ "$name" == "$ns" ]] && return 0
  done < <(ip netns list 2>/dev/null)
  return 1
}

root_link_exists() { ip link show "$1" >/dev/null 2>&1; }
ns_link_exists()   { ip -n "$1" link show "$2" >/dev/null 2>&1; }
link_is_up()       { ip -br link show dev "$1" 2>/dev/null | awk '{print $2}' | grep -q "UP"; }
ns_link_is_up()    { ip -n "$1" -br link show dev "$2" 2>/dev/null | awk '{print $2}' | grep -q "UP"; }

root_rx_packets() {
  ip -s link show dev "$1" 2>/dev/null | awk '/RX:/{getline; print $2; exit}'
}

ns_rx_packets() {
  ip -n "$1" -s link show dev "$2" 2>/dev/null | awk '/RX:/{getline; print $2; exit}'
}

# ── naming helpers ───────────────────────────────────────────────────

ns_name()   { echo "${CHAIN_PREFIX}-ns${1}"; }

# Veth endpoints for hop H (connecting ns-H to ns-H+1, or root to ns-1).
# Left  = upstream side, right = downstream side.
veth_left()  { echo "${CHAIN_PREFIX}-h${1}L"; }
veth_right() { echo "${CHAIN_PREFIX}-h${1}R"; }

# IPv4 /30 per hop:  BASE_NET.H.1/30  <->  BASE_NET.H.2/30
hop_left_cidr()  { echo "${CHAIN_BASE_NET}.${1}.1/30"; }
hop_right_cidr() { echo "${CHAIN_BASE_NET}.${1}.2/30"; }
hop_left_addr()  { echo "${CHAIN_BASE_NET}.${1}.1"; }

# IPv6 link-local per hop
hop_left_ll6()  { printf "fe80::%x:1/64" "$1"; }
hop_right_ll6() { printf "fe80::%x:2/64" "$1"; }

# ── up ───────────────────────────────────────────────────────────────

up() {
  local i ns left right

  for (( i = 1; i <= CHAIN_LENGTH; i++ )); do
    ns="$(ns_name "$i")"
    if ! netns_exists "$ns"; then
      ip netns add "$ns"
    fi
    ip -n "$ns" link set lo up 2>/dev/null || true
  done

  for (( i = 1; i <= CHAIN_LENGTH; i++ )); do
    left="$(veth_left "$i")"
    right="$(veth_right "$i")"

    local left_ns right_ns
    if (( i == 1 )); then
      left_ns=""
    else
      left_ns="$(ns_name $((i - 1)))"
    fi
    right_ns="$(ns_name "$i")"

    local left_exists=false right_exists=false
    if [[ -z "$left_ns" ]]; then
      root_link_exists "$left" && left_exists=true
    else
      ns_link_exists "$left_ns" "$left" && left_exists=true
    fi
    ns_link_exists "$right_ns" "$right" && right_exists=true

    if ! $left_exists || ! $right_exists; then
      # Clean up any stale half.
      if [[ -z "$left_ns" ]]; then
        ip link del "$left" 2>/dev/null || true
      else
        ip -n "$left_ns" link del "$left" 2>/dev/null || true
      fi
      ip -n "$right_ns" link del "$right" 2>/dev/null || true

      if [[ -z "$left_ns" ]]; then
        ip link add "$left" type veth peer name "$right"
      else
        ip -n "$left_ns" link add "$left" type veth peer name "$right"
      fi
      ip link set "$right" netns "$right_ns" 2>/dev/null || \
        ip -n "$left_ns" link set "$right" netns "$right_ns" 2>/dev/null || true
    fi

    # Bring up + address the left side.
    if [[ -z "$left_ns" ]]; then
      ip link set "$left" up
      ip addr replace "$(hop_left_cidr "$i")" dev "$left"
      ip -6 addr replace "$(hop_left_ll6 "$i")" dev "$left"
    else
      ip -n "$left_ns" link set "$left" up
      ip -n "$left_ns" addr replace "$(hop_left_cidr "$i")" dev "$left"
      ip -n "$left_ns" -6 addr replace "$(hop_left_ll6 "$i")" dev "$left"
    fi

    # Bring up + address the right side.
    ip -n "$right_ns" link set "$right" up
    ip -n "$right_ns" addr replace "$(hop_right_cidr "$i")" dev "$right"
    ip -n "$right_ns" -6 addr replace "$(hop_right_ll6 "$i")" dev "$right"
  done

  # Default routes: each namespace forwards toward the upstream hop.
  for (( i = 1; i <= CHAIN_LENGTH; i++ )); do
    local ns gw_addr gw_dev
    ns="$(ns_name "$i")"
    gw_addr="$(hop_left_addr "$i")"
    gw_dev="$(veth_right "$i")"
    ip -n "$ns" route replace default via "$gw_addr" dev "$gw_dev" 2>/dev/null || true
  done

  # Enable forwarding inside intermediate namespaces so traffic can
  # traverse the full chain.
  for (( i = 1; i < CHAIN_LENGTH; i++ )); do
    local ns
    ns="$(ns_name "$i")"
    ip netns exec "$ns" sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || true
    ip netns exec "$ns" sysctl -w net.ipv6.conf.all.forwarding=1 >/dev/null 2>&1 || true
  done

  # Root-side return routes to downstream subnets.
  for (( i = 2; i <= CHAIN_LENGTH; i++ )); do
    local dst via_addr
    dst="${CHAIN_BASE_NET}.${i}.0/30"
    via_addr="$(hop_right_cidr 1)"
    via_addr="${via_addr%%/*}"
    ip route replace "$dst" via "$via_addr" 2>/dev/null || true
  done

  # Intermediate namespace routes toward deeper hops.
  for (( i = 1; i < CHAIN_LENGTH; i++ )); do
    local ns
    ns="$(ns_name "$i")"
    for (( j = i + 2; j <= CHAIN_LENGTH; j++ )); do
      local dst via_addr
      dst="${CHAIN_BASE_NET}.${j}.0/30"
      via_addr="$(hop_right_cidr $((i + 1)))"
      via_addr="${via_addr%%/*}"
      ip -n "$ns" route replace "$dst" via "$via_addr" dev "$(veth_left $((i + 1)))" 2>/dev/null || true
    done
  done

  echo "Peer veth chain is up (${CHAIN_LENGTH} hops)."
  status
}

# ── down ─────────────────────────────────────────────────────────────

down() {
  local i left ns

  for (( i = CHAIN_LENGTH; i >= 1; i-- )); do
    ns="$(ns_name "$i")"
    left="$(veth_left "$i")"

    if (( i == 1 )); then
      ip link del "$left" 2>/dev/null || true
    else
      ip -n "$(ns_name $((i - 1)))" link del "$left" 2>/dev/null || true
    fi
    ip netns delete "$ns" 2>/dev/null || true
  done

  # Clean up root-side return routes.
  for (( i = 2; i <= CHAIN_LENGTH; i++ )); do
    ip route del "${CHAIN_BASE_NET}.${i}.0/30" 2>/dev/null || true
  done

  echo "Peer veth chain removed (${CHAIN_LENGTH} hops)."
}

# ── status ───────────────────────────────────────────────────────────

hop_ready() {
  local left right left_ns right_ns
  left="$1"; right="$2"; left_ns="$3"; right_ns="$4"

  local left_up=false right_up=false
  if [[ -z "$left_ns" ]]; then
    root_link_exists "$left" && link_is_up "$left" && left_up=true
  else
    ns_link_exists "$left_ns" "$left" && ns_link_is_up "$left_ns" "$left" && left_up=true
  fi
  ns_link_exists "$right_ns" "$right" && ns_link_is_up "$right_ns" "$right" && right_up=true

  $left_up && $right_up
}

status() {
  local i left right left_ns right_ns

  echo "=== HUM peer veth chain status (${CHAIN_LENGTH} hops) ==="
  echo

  for (( i = 1; i <= CHAIN_LENGTH; i++ )); do
    left="$(veth_left "$i")"
    right="$(veth_right "$i")"

    if (( i == 1 )); then
      left_ns=""
      echo "  hop $i: [root] $left  <-->  [$(ns_name "$i")] $right"
    else
      left_ns="$(ns_name $((i - 1)))"
      echo "  hop $i: [$(ns_name $((i - 1)))] $left  <-->  [$(ns_name "$i")] $right"
    fi

    right_ns="$(ns_name "$i")"

    if hop_ready "$left" "$right" "$left_ns" "$right_ns"; then
      echo "         peer recv-ready: yes"
    else
      echo "         peer recv-ready: no"
    fi

    # RX counters
    local left_rx right_rx
    if [[ -z "$left_ns" ]]; then
      left_rx="$(root_rx_packets "$left" || true)"
    else
      left_rx="$(ns_rx_packets "$left_ns" "$left" || true)"
    fi
    right_rx="$(ns_rx_packets "$right_ns" "$right" || true)"
    echo "         rx packets: left=${left_rx:-0}  right=${right_rx:-0}"

    # Addresses
    if [[ -z "$left_ns" ]]; then
      echo "         left  addr: $(hop_left_cidr "$i")  $(hop_left_ll6 "$i")"
    else
      echo "         left  addr: $(hop_left_cidr "$i")  $(hop_left_ll6 "$i")"
    fi
    echo "         right addr: $(hop_right_cidr "$i")  $(hop_right_ll6 "$i")"
    echo
  done

  echo "Namespace summary:"
  for (( i = 1; i <= CHAIN_LENGTH; i++ )); do
    local ns ready
    ns="$(ns_name "$i")"
    if netns_exists "$ns"; then
      ready="exists"
    else
      ready="missing"
    fi
    echo "  $ns: $ready"
  done
}

# ── plot (ASCII merger-plot diagram) ─────────────────────────────────

plot() {
  local i

  echo "=== HUM merger plot – peer veth chain (${CHAIN_LENGTH} hops) ==="
  echo
  echo "Traffic flows left-to-right through the chain.  Each namespace"
  echo "acts as a forwarding peer.  The merger point is the final namespace"
  echo "where all hops converge before egress or processing."
  echo

  # Top border
  local top_line="  ┌──────────┐"
  for (( i = 1; i <= CHAIN_LENGTH; i++ )); do
    top_line+="          ┌──────────┐"
  done
  echo "$top_line"

  # Middle row with labels
  local mid_line="  │  [root]  │"
  for (( i = 1; i <= CHAIN_LENGTH; i++ )); do
    local label ns
    ns="$(ns_name "$i")"
    if (( i == CHAIN_LENGTH )); then
      label="[merge:${i}]"
    else
      label="[peer:${i}] "
    fi
    mid_line+="──veth:h${i}──│ ${label}│"
  done
  echo "$mid_line"

  # Bottom border
  local bot_line="  └──────────┘"
  for (( i = 1; i <= CHAIN_LENGTH; i++ )); do
    bot_line+="          └──────────┘"
  done
  echo "$bot_line"

  # Addressing detail
  echo
  echo "Hop addressing:"
  for (( i = 1; i <= CHAIN_LENGTH; i++ )); do
    local src_label
    if (( i == 1 )); then
      src_label="root"
    else
      src_label="$(ns_name $((i - 1)))"
    fi
    echo "  hop $i: ${src_label} $(hop_left_cidr "$i") ←→ $(ns_name "$i") $(hop_right_cidr "$i")"
  done

  echo
  echo "Merger guidance:"
  echo "  • The chain is designed so each peer namespace forwards traffic"
  echo "    to the next hop.  ip_forward is enabled on intermediate peers."
  echo "  • The final namespace ($(ns_name "$CHAIN_LENGTH")) is the merger point."
  echo "    Configure services, filters, or captures here to observe"
  echo "    traffic that has traversed the entire chain."
  echo "  • To verify end-to-end reachability:"
  echo "    sudo ip netns exec $(ns_name "$CHAIN_LENGTH") ping -c1 ${CHAIN_BASE_NET}.1.1"
  echo "  • To inject traffic from the tail:"
  echo "    sudo ip netns exec $(ns_name "$CHAIN_LENGTH") curl http://${CHAIN_BASE_NET}.1.1:<port>"
  echo "  • Add iptables/nftables rules in any peer namespace to shape,"
  echo "    mark, or redirect traffic as it passes through the chain."
}

# ── argument parsing ─────────────────────────────────────────────────

main() {
  local action=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      up|down|status|plot)
        action="$1"; shift ;;
      --length)
        CHAIN_LENGTH="$2"; shift 2 ;;
      -h|--help|help)
        usage; exit 0 ;;
      *)
        usage; exit 1 ;;
    esac
  done

  if (( CHAIN_LENGTH < 1 || CHAIN_LENGTH > 16 )); then
    echo "Chain length must be 1–16." >&2
    exit 1
  fi

  action="${action:-status}"

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
    plot)
      plot
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
