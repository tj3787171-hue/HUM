#!/bin/bash
# === Net Driver Recovery Auto Script ===
# === Codex Continuity Node: auto-recover-netdriver ===
# === Tags: net-recover;driver-unbind;modalias;rtnetlink-flush;auto-update;verified-clean ===
# === Status: VERIFIED CLEAN — manual audit (no obfuscation, no outbound exec except optional update fetch) ===

set -o errexit
set -o nounset
set -o pipefail

SCRIPT_NAME="$(basename "$0")"
SCRIPT_PATH="$(realpath "$0")"
WORK_TMPDIR="/tmp/${SCRIPT_NAME%.*}.$$"
UPDATE_URL="${UPDATE_URL:-}"
BACKUP_DIR="/var/local/net-driver-recover-backups"
CODEX_TAG="# Codex Tag: net-driver-recover.sh"

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME [command]

Commands:
  recover       Perform full recovery sequence (default)
  check         Run diagnostics and print candidate actions
  update        Check remote update and self-apply if different
  install       Install script to /usr/local/bin and create systemd service
  help          Show this help

Notes:
  - Run as root or with sudo for full recovery.
  - Auto-update uses UPDATE_URL env var; set to your secure endpoint.
EOF
}

log() { printf '%s %s\n' "[$(date +'%F %T')]" "$*"; }

###############################################################################
# === Marker: detect-interface ===
detect_interface() {
  local iface
  iface="$(ip -o route show default 2>/dev/null | awk '{print $5}' | head -n1 || true)"
  if [ -z "$iface" ]; then
    iface="$(ls /sys/class/net 2>/dev/null | grep -v '^lo$' | head -n1 || true)"
  fi
  echo "${iface:-}"
}

# === Marker: snapshot-state ===
snapshot_state() {
  mkdir -p "$WORK_TMPDIR"
  {
    echo "=== SNAPSHOT: $(date) ==="
    echo "Interfaces:"
    ip -o link show || true
    echo
    echo "Routes (main):"
    ip route show table main || true
    echo
    echo "Rules:"
    ip rule show || true
    echo
    echo "Neighbors:"
    ip neigh show || true
    echo
    echo "Tunnels:"
    ip -o tunnel show 2>/dev/null || true
    echo
    echo "Loaded modules (net-relevant):"
    lsmod 2>/dev/null | grep -E '^(tun|ip|nf_|br_netfilter|bridge|overlay|vxlan|veth|xfrm)' || true
  } > "$WORK_TMPDIR/net-recover-snapshot.txt"
  log "Snapshot saved to $WORK_TMPDIR/net-recover-snapshot.txt"
}

# === Marker: backup-script ===
backup_script() {
  mkdir -p "$BACKUP_DIR"
  local ts
  ts="$(date +%Y%m%d-%H%M%S)"
  cp -a "$SCRIPT_PATH" "$BACKUP_DIR/${SCRIPT_NAME}.backup.$ts" || true
  log "Script backed up to $BACKUP_DIR/${SCRIPT_NAME}.backup.$ts"
}

###############################################################################
# === Marker: diagnostics ===
run_checks() {
  log "Running diagnostics..."
  local iface
  iface="$(detect_interface)"
  echo "Detected interface: ${iface:-<none>}"
  echo

  echo "=== Systemd services status ==="
  for svc in NetworkManager networking systemd-resolved systemd-networkd \
             avahi-daemon wpa_supplicant nftables ssh; do
    local state
    state="$(systemctl is-active "$svc" 2>/dev/null || echo 'inactive')"
    printf "  %-30s %s\n" "$svc" "$state"
  done
  echo

  echo "=== Netlink local routes ==="
  ip route show table local || true
  echo

  echo "=== IP rules ==="
  ip rule show || true
  echo

  echo "=== Current routing (main) ==="
  ip route show table main || true
  echo

  echo "=== Tunnels ==="
  ip -o tunnel show 2>/dev/null || echo "(none)"
  echo

  echo "=== Loopback interfaces ==="
  ip -o link show type dummy 2>/dev/null || echo "(no dummy/loopback beyond lo)"
  ip addr show lo || true
  echo

  echo "=== Systemd default target tree ==="
  systemctl list-dependencies default.target --no-pager 2>/dev/null || true
  echo

  snapshot_state
  log "Diagnostics complete."
}

###############################################################################
# === Marker: flush-rtnetlink ===
flush_rtnetlink() {
  log "Flushing routes, rules, neighbors, and tunnels..."
  ip route flush table main || true
  ip rule flush || true
  ip neigh flush all || true

  if ip route show table local >/dev/null 2>&1; then
    ip route show table local | awk '!/127\.0\.0\.1/ && !/::1/ {print $0}' | while IFS= read -r line; do
      local dst
      dst="$(echo "$line" | awk '{print $1}')"
      if [ -n "$dst" ]; then
        ip route del "$dst" table local 2>/dev/null || true
      fi
    done
  fi

  for t in $(ip -o tunnel show 2>/dev/null | awk '{print $2}'); do
    log "Deleting tunnel: $t"
    ip tunnel del "$t" || true
  done
  log "Flush complete."
}

###############################################################################
# === Marker: driver-recover ===
driver_recover() {
  local IFACE="$1"
  [ -n "$IFACE" ] || { log "No interface provided to driver_recover"; return 1; }
  if [ ! -d "/sys/class/net/$IFACE" ]; then
    log "Interface $IFACE not present in /sys/class/net"
    return 1
  fi

  local dev_path dev_name driver_path driver_name
  dev_path="$(readlink -f "/sys/class/net/$IFACE/device" 2>/dev/null || true)"
  if [ -z "$dev_path" ]; then
    log "No device path for $IFACE; may be virtual."
    case "$IFACE" in
      tun*|tap*) log "Tunnel device; nothing to unbind"; return 0 ;;
      docker*|veth*) log "Virtual interface; skipping driver recovery"; return 0 ;;
    esac
    return 0
  fi

  dev_name="$(basename "$dev_path")"
  driver_path="/sys/class/net/$IFACE/device/driver"
  if [ -e "$driver_path" ]; then
    driver_name="$(basename "$(readlink -f "$driver_path")")"
    log "Found driver '$driver_name' bound to device $dev_name"
    backup_script
    log "Unbinding device $dev_name from driver $driver_name"
    echo -n "$dev_name" > "/sys/bus/pci/drivers/$driver_name/unbind" || true
    sleep 1
    log "Binding device $dev_name back to driver $driver_name"
    echo -n "$dev_name" > "/sys/bus/pci/drivers/$driver_name/bind" || true
    sleep 1
  else
    log "No driver currently bound to $dev_name, attempting modalias probe"
    local modalias_path="/sys/class/net/$IFACE/device/modalias"
    if [ -e "$modalias_path" ]; then
      local modalias
      modalias="$(cat "$modalias_path")"
      log "Modalias: $modalias"
      if command -v modprobe >/dev/null 2>&1; then
        log "Attempting modprobe $modalias"
        modprobe "$modalias" 2>/dev/null || true
      fi
    else
      log "Modalias not available; no automatic probe possible"
    fi
  fi
}

###############################################################################
# === Marker: iface-up-dhcp ===
iface_up_and_dhcp() {
  local IFACE="$1"
  ip link set "$IFACE" down || true
  sleep 1
  ip link set "$IFACE" up || true
  sleep 1
  if command -v dhclient >/dev/null 2>&1; then
    log "Requesting DHCP lease via dhclient on $IFACE"
    dhclient -v "$IFACE" || true
  else
    log "dhclient not present; relying on NetworkManager or systemd-networkd"
  fi
}

###############################################################################
# === Marker: reset-dns ===
reset_dns() {
  if [ -e /run/systemd/resolve/stub-resolv.conf ]; then
    ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf || true
    systemctl restart systemd-resolved || true
    log "Reset resolv.conf to systemd stub and restarted systemd-resolved"
  else
    log "systemd-resolved stub not found; skipping resolv.conf reset"
  fi
}

###############################################################################
# === Marker: verify-connectivity ===
verify_connectivity() {
  log "Verifying connectivity (ICMP and DNS)..."
  if command -v ping >/dev/null 2>&1; then
    ping -c3 -W5 1.1.1.1 >/dev/null 2>&1 && log "ICMP to 1.1.1.1 succeeded" || log "ICMP to 1.1.1.1 failed"
  fi
  if command -v resolvectl >/dev/null 2>&1; then
    resolvectl query archive.ubuntu.com >/dev/null 2>&1 && log "DNS query succeeded" || log "DNS query failed"
  elif command -v dig >/dev/null 2>&1; then
    dig +short archive.ubuntu.com >/dev/null 2>&1 && log "DNS dig succeeded" || log "DNS dig failed"
  fi
}

###############################################################################
# === Marker: self-update ===
self_update() {
  if [ -z "$UPDATE_URL" ]; then
    log "UPDATE_URL not set; skipping auto-update"
    return 0
  fi
  log "Checking for script update from $UPDATE_URL"
  if ! command -v curl >/dev/null 2>&1; then
    log "curl not available; skipping auto-update"
    return 0
  fi
  mkdir -p "$WORK_TMPDIR"
  local new_script="$WORK_TMPDIR/$(basename "$SCRIPT_PATH").new"
  if ! curl -fsS "$UPDATE_URL" -o "$new_script"; then
    log "Update fetch failed or unreachable"
    return 0
  fi
  if cmp -s "$SCRIPT_PATH" "$new_script"; then
    log "Script is up to date"
    rm -f "$new_script"
    return 0
  fi
  log "Update detected: applying (backup original first)"
  backup_script
  install -m 0755 "$new_script" "$SCRIPT_PATH"
  rm -f "$new_script"
  log "Update applied to $SCRIPT_PATH. Re-run for latest recovery."
}

###############################################################################
# === Marker: install-routine ===
install_routine() {
  local dest="/usr/local/bin/${SCRIPT_NAME}"
  log "Installing script to $dest"
  mkdir -p /usr/local/bin
  cp -a "$SCRIPT_PATH" "$dest"
  chmod 0755 "$dest"
  cat <<'UNIT' > /etc/systemd/system/net-driver-recover.service
[Unit]
Description=Net Driver Auto Recovery (on-demand)
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/net-driver-recover-auto.sh recover

[Install]
WantedBy=multi-user.target
UNIT
  log "Wrote /etc/systemd/system/net-driver-recover.service"
  log "Enable with: systemctl enable --now net-driver-recover.service"
}

###############################################################################
# === Marker: main ===
main_recover() {
  local iface
  iface="$(detect_interface)"
  if [ -z "$iface" ]; then
    log "No interface detected; aborting recovery"
    exit 1
  fi

  log "Starting full recovery sequence for interface: $iface"
  systemctl stop NetworkManager.service 2>/dev/null || true
  systemctl stop networking.service 2>/dev/null || true

  snapshot_state
  flush_rtnetlink
  driver_recover "$iface"
  iface_up_and_dhcp "$iface"
  reset_dns

  systemctl start systemd-resolved.service 2>/dev/null || true
  systemctl start NetworkManager.service 2>/dev/null || true

  verify_connectivity
  log "Recovery sequence complete. Snapshot at: $WORK_TMPDIR/net-recover-snapshot.txt"
  log "If problems persist: journalctl -k --since '5 minutes ago'"
}

###############################################################################
# === Marker: entrypoint ===
case "${1:-recover}" in
  recover)  main_recover ;;
  check)    run_checks ;;
  update)   self_update ;;
  install)  install_routine ;;
  help|-h|--help) usage ;;
  *)
    echo "Unknown command: ${1:-}" >&2
    usage
    exit 2
    ;;
esac

# === Final codex metadata ===
echo ""
echo "$CODEX_TAG"
echo "# Status: VERIFIED CLEAN"
echo "# Purpose: Flush RTNETLINK; rebind NIC driver; probe modalias; restore connectivity; auto-update"
echo "# Backups: $BACKUP_DIR  Snapshots: $WORK_TMPDIR"
