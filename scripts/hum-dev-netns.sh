#!/usr/bin/env bash
set -euo pipefail

# Developer naming defaults (override with HUM_* environment variables).
PROXY_NS="${HUM_PROXY_NS:-hum-proxy-ns}"
PROXY_HOST_IF="${HUM_PROXY_HOST_IF:-hum-proxy-host0}"
PROXY_NS_IF="${HUM_PROXY_NS_IF:-hum-proxy-ns0}"
PROXY_HOST_CIDR="${HUM_PROXY_HOST_CIDR:-10.200.0.1/30}"
PROXY_NS_CIDR="${HUM_PROXY_NS_CIDR:-10.200.0.2/30}"
PROXY_DEFAULT_GW="${HUM_PROXY_DEFAULT_GW:-10.200.0.1}"

DUMMY_IF="${HUM_DUMMY_IF:-hum-dummy0}"
DUMMY_CIDR="${HUM_DUMMY_CIDR:-198.18.0.1/24}"

DOCKER_HINT_IF="${HUM_DOCKER_HINT_IF:-docker0}"

usage() {
  cat <<'EOF'
Usage:
  sudo bash scripts/hum-dev-netns.sh up
  sudo bash scripts/hum-dev-netns.sh down
  sudo bash scripts/hum-dev-netns.sh status
  sudo bash scripts/hum-dev-netns.sh status --json

Optional environment overrides:
  HUM_PROXY_NS
  HUM_PROXY_HOST_IF
  HUM_PROXY_NS_IF
  HUM_PROXY_HOST_CIDR
  HUM_PROXY_NS_CIDR
  HUM_PROXY_DEFAULT_GW
  HUM_DUMMY_IF
  HUM_DUMMY_CIDR
  HUM_DOCKER_HINT_IF
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

  ip -n "$PROXY_NS" link set lo up
  ip -n "$PROXY_NS" link set "$PROXY_NS_IF" up
  ip -n "$PROXY_NS" addr replace "$PROXY_NS_CIDR" dev "$PROXY_NS_IF"
  ip -n "$PROXY_NS" route replace default via "$PROXY_DEFAULT_GW" dev "$PROXY_NS_IF"

  if ! root_link_exists "$DUMMY_IF"; then
    ip link add "$DUMMY_IF" type dummy
  fi
  ip link set "$DUMMY_IF" up
  ip addr replace "$DUMMY_CIDR" dev "$DUMMY_IF"

  status
}

down() {
  ip link del "$DUMMY_IF" 2>/dev/null || true
  ip link del "$PROXY_HOST_IF" 2>/dev/null || true
  ip -n "$PROXY_NS" link del "$PROXY_NS_IF" 2>/dev/null || true
  ip netns delete "$PROXY_NS" 2>/dev/null || true
  echo "Removed dev namespace/interface naming setup."
}

status() {
  echo "=== HUM dev naming status ==="
  echo "proxy namespace: $PROXY_NS"
  echo "proxy links: host=$PROXY_HOST_IF ns=$PROXY_NS_IF"
  echo "dummy link: $DUMMY_IF"
  echo

  if netns_exists "$PROXY_NS"; then
    echo "[root] $PROXY_HOST_IF"
    ip -br addr show dev "$PROXY_HOST_IF" 2>/dev/null || true
    echo
    echo "[netns:$PROXY_NS] $PROXY_NS_IF"
    ip -n "$PROXY_NS" -br addr show dev "$PROXY_NS_IF" 2>/dev/null || true
    echo "[netns:$PROXY_NS] default route"
    ip -n "$PROXY_NS" route show default 2>/dev/null || true
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
