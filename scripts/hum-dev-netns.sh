#!/usr/bin/env bash
set -euo pipefail

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
PEER_ROUTE_CIDR="${HUM_PEER_ROUTE_CIDR:-10.200.1.0/30}"
ENABLE_PEER_CHAIN="${HUM_ENABLE_PEER_CHAIN:-1}"

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
  sudo bash scripts/hum-dev-netns.sh collect
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
  HUM_PEER_NS
  HUM_PROXY_PEER_IF
  HUM_PEER_NS_IF
  HUM_PROXY_PEER_CIDR
  HUM_PEER_NS_CIDR
  HUM_PEER_ROUTE_CIDR
  HUM_PEER_DEFAULT_GW
  HUM_PROXY_PEER_LL6
  HUM_PEER_NS_LL6
  HUM_ENABLE_PEER_CHAIN
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

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "This action requires root. Re-run with sudo." >&2
    exit 1
  fi
}

netns_exists() {
  local ns="$1"
  ip netns list | awk '{print $1}' | grep -qx "$ns"
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
  local mac="$1"
  local b1 b2 b3 b4 b5 b6
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
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

peer_chain_enabled() {
  is_truthy "$ENABLE_PEER_CHAIN"
}

peer_recv_ready() {
  netns_exists "$PROXY_NS" &&
    root_link_exists "$PROXY_HOST_IF" &&
    ns_link_exists "$PROXY_NS" "$PROXY_NS_IF" &&
    link_is_up "$PROXY_HOST_IF" &&
    ns_link_is_up "$PROXY_NS" "$PROXY_NS_IF"
}

peer_chain_recv_ready() {
  peer_chain_enabled &&
    netns_exists "$PROXY_NS" &&
    netns_exists "$PEER_NS" &&
    ns_link_exists "$PROXY_NS" "$PROXY_PEER_IF" &&
    ns_link_exists "$PEER_NS" "$PEER_NS_IF" &&
    ns_link_is_up "$PROXY_NS" "$PROXY_PEER_IF" &&
    ns_link_is_up "$PEER_NS" "$PEER_NS_IF"
}

netns_ip_n_readable() {
  ip -n "$PROXY_NS" link show lo >/dev/null 2>&1
}

update_peer_state() {
  HUM_PEER_HOST_STATE="missing"
  HUM_PEER_NS_STATE="missing"
  HUM_PEER_RECV_READY="no"

  if root_link_exists "$PROXY_HOST_IF"; then
    HUM_PEER_HOST_STATE="$(root_link_state "$PROXY_HOST_IF")"
  fi

  if ! netns_exists "$PROXY_NS"; then
    return
  fi

  if ! netns_ip_n_readable; then
    HUM_PEER_NS_STATE="unknown (sudo required for ip -n)"
    HUM_PEER_RECV_READY="unknown (sudo required for ip -n)"
    return
  fi

  if ns_link_exists "$PROXY_NS" "$PROXY_NS_IF"; then
    HUM_PEER_NS_STATE="$(ns_link_state "$PROXY_NS" "$PROXY_NS_IF")"
  fi

  if peer_recv_ready; then
    HUM_PEER_RECV_READY="yes"
  fi
}

ensure_root_to_ns_pair() {
  local root_if="$1"
  local ns="$2"
  local ns_if="$3"

  if ! root_link_exists "$root_if" || ! ns_link_exists "$ns" "$ns_if"; then
    ip link del "$root_if" 2>/dev/null || true
    ip -n "$ns" link del "$ns_if" 2>/dev/null || true
    ip link add "$root_if" type veth peer name "$ns_if"
    ip link set "$ns_if" netns "$ns"
  fi
}

ensure_ns_to_ns_pair() {
  local ns_a="$1"
  local if_a="$2"
  local ns_b="$3"
  local if_b="$4"

  if ! ns_link_exists "$ns_a" "$if_a" || ! ns_link_exists "$ns_b" "$if_b"; then
    ip -n "$ns_a" link del "$if_a" 2>/dev/null || true
    ip -n "$ns_b" link del "$if_b" 2>/dev/null || true
    ip -n "$ns_a" link add "$if_a" type veth peer name "$if_b"
    ip -n "$ns_a" link set "$if_b" netns "$ns_b"
  fi
}

print_peer_veth_chain() {
  update_peer_state
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
}

up() {
  local proxy_ns_ip
  proxy_ns_ip="${PROXY_NS_CIDR%%/*}"

  if ! netns_exists "$PROXY_NS"; then
    ip netns add "$PROXY_NS"
  fi

  ensure_root_to_ns_pair "$PROXY_HOST_IF" "$PROXY_NS" "$PROXY_NS_IF"

  ip link set "$PROXY_HOST_IF" up
  ip addr replace "$PROXY_HOST_CIDR" dev "$PROXY_HOST_IF"
  ip -6 addr replace "$PROXY_HOST_LL6" dev "$PROXY_HOST_IF"

  ip -n "$PROXY_NS" link set lo up
  ip -n "$PROXY_NS" link set "$PROXY_NS_IF" up
  ip -n "$PROXY_NS" addr replace "$PROXY_NS_CIDR" dev "$PROXY_NS_IF"
  ip -n "$PROXY_NS" -6 addr replace "$PROXY_NS_LL6" dev "$PROXY_NS_IF"
  ip -n "$PROXY_NS" route replace default via "$PROXY_DEFAULT_GW" dev "$PROXY_NS_IF"
  ip -n "$PROXY_NS" -6 route replace default via "${PROXY_HOST_LL6%%/*}" dev "$PROXY_NS_IF"
  ip netns exec "$PROXY_NS" sh -c \
    'echo 1 > /proc/sys/net/ipv4/ip_forward; echo 1 > /proc/sys/net/ipv6/conf/all/forwarding'

  if peer_chain_enabled; then
    if ! netns_exists "$PEER_NS"; then
      ip netns add "$PEER_NS"
    fi

    ensure_ns_to_ns_pair "$PROXY_NS" "$PROXY_PEER_IF" "$PEER_NS" "$PEER_NS_IF"

    ip -n "$PROXY_NS" link set "$PROXY_PEER_IF" up
    ip -n "$PROXY_NS" addr replace "$PROXY_PEER_CIDR" dev "$PROXY_PEER_IF"
    ip -n "$PROXY_NS" -6 addr replace "$PROXY_PEER_LL6" dev "$PROXY_PEER_IF"

    ip -n "$PEER_NS" link set lo up
    ip -n "$PEER_NS" link set "$PEER_NS_IF" up
    ip -n "$PEER_NS" addr replace "$PEER_NS_CIDR" dev "$PEER_NS_IF"
    ip -n "$PEER_NS" -6 addr replace "$PEER_NS_LL6" dev "$PEER_NS_IF"
    ip -n "$PEER_NS" route replace default via "$PEER_DEFAULT_GW" dev "$PEER_NS_IF"
    ip -n "$PEER_NS" -6 route replace default via "${PROXY_PEER_LL6%%/*}" dev "$PEER_NS_IF"

    ip route replace "$PEER_ROUTE_CIDR" via "$proxy_ns_ip" dev "$PROXY_HOST_IF"
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
  ip route del "$PEER_ROUTE_CIDR" 2>/dev/null || true
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
  local host_mac ns_mac peer_mac host_smac64 ns_smac64 peer_smac64 host_rx ns_rx peer_rx

  host_mac="$(iface_mac "$PROXY_HOST_IF" || true)"
  ns_mac="$(ns_iface_mac "$PROXY_NS" "$PROXY_NS_IF" || true)"
  peer_mac="$(ns_iface_mac "$PEER_NS" "$PEER_NS_IF" || true)"
  host_smac64="$(smac64_from_mac "$host_mac")"
  ns_smac64="$(smac64_from_mac "$ns_mac")"
  peer_smac64="$(smac64_from_mac "$peer_mac")"
  host_rx="$(root_rx_packets "$PROXY_HOST_IF" || true)"
  ns_rx="$(ns_rx_packets "$PROXY_NS" "$PROXY_NS_IF" || true)"
  peer_rx="$(ns_rx_packets "$PEER_NS" "$PEER_NS_IF" || true)"

  print_peer_veth_chain
  echo
  echo "=== HUM dev naming status ==="
  echo "proxy namespace: $PROXY_NS"
  echo "peer namespace:  $PEER_NS"
  echo "proxy links: host=$PROXY_HOST_IF ns=$PROXY_NS_IF"
  echo "peer links: proxy=$PROXY_PEER_IF peer=$PEER_NS_IF"
  echo "dummy link: $DUMMY_IF"
  if peer_chain_enabled; then
    if peer_chain_recv_ready; then
      echo "peer chain recv-ready: yes"
    else
      echo "peer chain recv-ready: no"
    fi
  else
    echo "peer chain recv-ready: disabled"
  fi
  echo "trace-smac64 host: $host_smac64"
  echo "trace-smac64 ns:   $ns_smac64"
  echo "trace-smac64 peer: $peer_smac64"
  echo "downstream nested packets (rx): host=${host_rx:-0} ns=${ns_rx:-0} peer=${peer_rx:-0}"
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

  if peer_chain_enabled; then
    echo
    if netns_exists "$PEER_NS"; then
      echo "[netns:$PROXY_NS] $PROXY_PEER_IF"
      ip -n "$PROXY_NS" -br addr show dev "$PROXY_PEER_IF" 2>/dev/null || true
      echo
      echo "[netns:$PEER_NS] $PEER_NS_IF"
      ip -n "$PEER_NS" -br addr show dev "$PEER_NS_IF" 2>/dev/null || true
      echo "[netns:$PEER_NS] default route"
      ip -n "$PEER_NS" route show default 2>/dev/null || true
      echo "[netns:$PEER_NS] default route (IPv6)"
      ip -n "$PEER_NS" -6 route show default 2>/dev/null || true
      echo
      echo "[root] peer chain route"
      ip route show "$PEER_ROUTE_CIDR" 2>/dev/null || true
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

status_json() {
  local ns_present docker_present
  local host_if_addr ns_if_addr dummy_if_addr docker_if_addr ns_default_route host_mac ns_mac

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
  host_mac="$(iface_mac "$PROXY_HOST_IF" || true)"
  ns_mac="$(ns_iface_mac "$PROXY_NS" "$PROXY_NS_IF" || true)"

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

collect() {
  python3 - "$PROXY_NS" "$PROXY_HOST_IF" "$PROXY_NS_IF" "$PROXY_HOST_CIDR" "$PROXY_NS_CIDR" \
    "$PROXY_HOST_LL6" "$PROXY_NS_LL6" "$PEER_NS" "$PROXY_PEER_IF" "$PEER_NS_IF" \
    "$PROXY_PEER_CIDR" "$PEER_NS_CIDR" "$PROXY_PEER_LL6" "$PEER_NS_LL6" \
    "$DUMMY_IF" "$DUMMY_CIDR" "$ENABLE_PEER_CHAIN" <<'PY'
import datetime as dt
import json
import re
import subprocess
import sys

(
    proxy_ns,
    proxy_host_if,
    proxy_ns_if,
    proxy_host_cidr,
    proxy_ns_cidr,
    proxy_host_ll6,
    proxy_ns_ll6,
    peer_ns,
    proxy_peer_if,
    peer_ns_if,
    proxy_peer_cidr,
    peer_ns_cidr,
    proxy_peer_ll6,
    peer_ns_ll6,
    dummy_if,
    dummy_cidr,
    enable_peer_chain,
) = sys.argv[1:]


def run(command: list[str]) -> str:
    try:
        return subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        ).stdout
    except FileNotFoundError:
        return ""


def netns_exists(namespace: str) -> bool:
    return any(line.split()[0] == namespace for line in run(["ip", "netns", "list"]).splitlines() if line.strip())


def link_output(namespace: str, interface: str) -> str:
    if namespace == "root":
        return run(["ip", "-o", "link", "show", "dev", interface])
    return run(["ip", "-n", namespace, "-o", "link", "show", "dev", interface])


def link_brief(namespace: str, interface: str) -> str:
    if namespace == "root":
        return run(["ip", "-br", "link", "show", "dev", interface])
    return run(["ip", "-n", namespace, "-br", "link", "show", "dev", interface])


def link_up(namespace: str, interface: str) -> bool:
    return "UP" in link_brief(namespace, interface).split()


def mac(namespace: str, interface: str) -> str:
    output = link_output(namespace, interface)
    match = re.search(r"link/ether\s+([0-9a-f:]{17})", output, re.IGNORECASE)
    return match.group(1).lower() if match else ""


def smac64_from_mac(value: str) -> str:
    if not re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", value or ""):
        return "unknown"
    parts = value.split(":")
    parts[0] = f"{(int(parts[0], 16) ^ 2):02x}"
    return f"{parts[0]}{parts[1]}{parts[2]}fffe{parts[3]}{parts[4]}{parts[5]}"


def stats(namespace: str, interface: str) -> dict[str, int]:
    if namespace == "root":
        output = run(["ip", "-s", "link", "show", "dev", interface])
    else:
        output = run(["ip", "-n", namespace, "-s", "link", "show", "dev", interface])
    rows = [line.split() for line in output.splitlines()]
    result = {"rx_packets": 0, "tx_packets": 0}
    for index, row in enumerate(rows):
        if row and row[0] == "RX:" and index + 1 < len(rows):
            values = rows[index + 1]
            if len(values) >= 2:
                result["rx_packets"] = int(values[1])
        if row and row[0] == "TX:" and index + 1 < len(rows):
            values = rows[index + 1]
            if len(values) >= 2:
                result["tx_packets"] = int(values[1])
    return result


def route_records(namespace: str) -> list[dict[str, str]]:
    output = run(["ip", "-n", namespace, "route", "show"])
    records = []
    for line in output.splitlines():
        parts = line.split()
        if not parts:
            continue
        records.append(
            {
                "namespace": namespace,
                "family": "inet",
                "destination": parts[0],
                "gateway": parts[parts.index("via") + 1] if "via" in parts and parts.index("via") + 1 < len(parts) else "",
                "device": parts[parts.index("dev") + 1] if "dev" in parts and parts.index("dev") + 1 < len(parts) else "",
            }
        )
    return records


def hop(role: str, namespace: str, interface: str, ipv4_cidr: str, ipv6_cidr: str) -> dict[str, object]:
    value = mac(namespace, interface)
    return {
        "role": role,
        "namespace": namespace,
        "interface": interface,
        "mac": value,
        "smac64": smac64_from_mac(value),
        "ipv4_cidr": ipv4_cidr,
        "ipv6_cidr": ipv6_cidr,
        "link_up": link_up(namespace, interface),
    }


def truthy(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


chain_enabled = truthy(enable_peer_chain)
proxy_ready = netns_exists(proxy_ns) and link_up("root", proxy_host_if) and link_up(proxy_ns, proxy_ns_if)
chain_ready = chain_enabled and netns_exists(peer_ns) and link_up(proxy_ns, proxy_peer_if) and link_up(peer_ns, peer_ns_if)

hops = [
    hop("host", "root", proxy_host_if, proxy_host_cidr, proxy_host_ll6),
    hop("proxy-main", proxy_ns, proxy_ns_if, proxy_ns_cidr, proxy_ns_ll6),
]
counters = [{"role": "host", **stats("root", proxy_host_if)}, {"role": "proxy-main", **stats(proxy_ns, proxy_ns_if)}]
routes = route_records(proxy_ns)

if chain_enabled:
    hops.append(hop("proxy-peer", proxy_ns, proxy_peer_if, proxy_peer_cidr, proxy_peer_ll6))
    hops.append(hop("peer", peer_ns, peer_ns_if, peer_ns_cidr, peer_ns_ll6))
    counters.append({"role": "proxy-peer", **stats(proxy_ns, proxy_peer_if)})
    counters.append({"role": "peer", **stats(peer_ns, peer_ns_if)})
    routes.extend(route_records(peer_ns))

topology = {
    "chain": (
        f"root > {proxy_host_if} <-> {proxy_ns_if} > {proxy_peer_if} <-> {peer_ns_if}"
        if chain_enabled
        else f"root > {proxy_host_if} <-> {proxy_ns_if}"
    ),
    "dummy": f"{dummy_if} ({dummy_cidr})",
}

print(
    json.dumps(
        {
            "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "peer_chain_enabled": chain_enabled,
            "peer_recv_ready": proxy_ready,
            "peer_chain_recv_ready": chain_ready,
            "topology": topology,
            "hops": hops,
            "counters": counters,
            "routes": routes,
        },
        separators=(",", ":"),
    )
)
PY
}

plot() {
  local root_proxy_state="down"
  local proxy_peer_state="down"

  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "=== HUM merger plot ==="
    echo "[root] $PROXY_HOST_IF ($PROXY_HOST_CIDR, $PROXY_HOST_LL6)"
    echo "  | veth [requires root for live state]"
    echo "[netns:$PROXY_NS] $PROXY_NS_IF ($PROXY_NS_CIDR, $PROXY_NS_LL6)"
    echo "[netns:$PROXY_NS] $PROXY_PEER_IF ($PROXY_PEER_CIDR, $PROXY_PEER_LL6)"
    echo "  | veth [requires root for live state]"
    echo "[netns:$PEER_NS] $PEER_NS_IF ($PEER_NS_CIDR, $PEER_NS_LL6)"
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
  echo "[root] $PROXY_HOST_IF ($PROXY_HOST_CIDR, $PROXY_HOST_LL6)"
  echo "  | veth [$root_proxy_state]"
  echo "[netns:$PROXY_NS] $PROXY_NS_IF ($PROXY_NS_CIDR, $PROXY_NS_LL6)"
  echo "[netns:$PROXY_NS] $PROXY_PEER_IF ($PROXY_PEER_CIDR, $PROXY_PEER_LL6)"
  echo "  | veth [$proxy_peer_state]"
  echo "[netns:$PEER_NS] $PEER_NS_IF ($PEER_NS_CIDR, $PEER_NS_LL6)"
}

guide() {
  print_peer_veth_chain
  echo
  echo "=== HUM peer veth chain guide ==="
  echo "1. Create or repair the chain:"
  echo "   sudo bash scripts/hum-dev-netns.sh up"
  echo "2. Inspect current peer state and addressing:"
  echo "   sudo bash scripts/hum-dev-netns.sh status"
  echo "3. Verify connectivity:"
  echo "   sudo ip netns exec $PROXY_NS ping -c 1 $PROXY_DEFAULT_GW"
  echo "4. Inspect counters/routes/capture output:"
  echo "   sudo bash scripts/hum-dev-netns.sh trace"
  echo "5. Remove the chain:"
  echo "   sudo bash scripts/hum-dev-netns.sh down"
}

trace() {
  status
  echo
  echo "=== HUM downstream trace ==="
  if ! netns_exists "$PROXY_NS"; then
    echo "Namespace chain is incomplete; run 'up' first."
    return 1
  fi

  echo "[root] link counters"
  ip -s link show dev "$PROXY_HOST_IF" 2>/dev/null || true
  echo
  echo "[netns:$PROXY_NS] upstream link counters"
  ip -n "$PROXY_NS" -s link show dev "$PROXY_NS_IF" 2>/dev/null || true

  if peer_chain_enabled && netns_exists "$PEER_NS"; then
    echo
    echo "[netns:$PROXY_NS] peer link counters"
    ip -n "$PROXY_NS" -s link show dev "$PROXY_PEER_IF" 2>/dev/null || true
    echo
    echo "[netns:$PEER_NS] peer link counters"
    ip -n "$PEER_NS" -s link show dev "$PEER_NS_IF" 2>/dev/null || true
  fi

  if command -v tcpdump >/dev/null 2>&1 && [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    echo
    echo "[root] live capture on $PROXY_HOST_IF ($TRACE_CAPTURE_SECONDS s, max $TRACE_CAPTURE_COUNT packets)"
    timeout "$TRACE_CAPTURE_SECONDS" tcpdump -n -i "$PROXY_HOST_IF" -c "$TRACE_CAPTURE_COUNT" \
      "ip or ip6" 2>/dev/null || true
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
    plot)
      need_cmd ip
      plot
      ;;
    collect)
      need_cmd ip
      need_cmd python3
      collect
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
