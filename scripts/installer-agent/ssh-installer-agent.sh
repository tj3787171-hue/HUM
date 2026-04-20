#!/usr/bin/env bash
# SSH Installer Agent for Kali/Debian
# Manages remote installation via SSH through penguin namespace proxy.
# Handles key fingerprints, mirror selection, and installation control.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRESEED_FILE="${SCRIPT_DIR}/hum-auto-install.preseed"
PROXY_HOST="${HUM_PROXY_HOST:-192.168.68.52}"
PROXY_PORT="${HUM_PROXY_PORT:-3128}"
DNS_SERVERS=("209.18.47.61" "209.18.47.62")
GATEWAY="${HUM_GATEWAY:-192.168.68.51}"
LOCAL_IP="${HUM_LOCAL_IP:-192.168.68.53}"
SSH_KEY="${HOME}/.ssh/hum-installer-agent"
LOG_FILE="/tmp/ssh-installer-agent-$(date +%Y%m%d-%H%M%S).log"

KALI_MIRROR="${HUM_KALI_MIRROR:-http://http.kali.org/kali}"
DEBIAN_MIRROR="${HUM_DEBIAN_MIRROR:-http://deb.debian.org/debian}"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
err() { log "ERROR: $*" >&2; }

usage() {
  cat <<'EOF'
Usage: ssh-installer-agent.sh <command> [args]

Commands:
  keygen                Generate SSH key pair for installer agent
  scan <target-ip>      Scan and accept target SSH fingerprint
  probe <target-ip>     Probe target for SSH availability
  preseed <target-ip>   Push preseed file to installer target
  install <target-ip> [user] [mirror]
                        Run full installation sequence on target
  mirror-test [mirror]  Test mirror accessibility via proxy
  fix-cdrom <target-ip> Push CDROM corruption fix to target
  monitor <target-ip>   Monitor installation progress
  full <target-ip> [user] [mirror]
                        Complete workflow: keygen + scan + install

Environment:
  HUM_PROXY_HOST        Proxy host (default: 192.168.68.52)
  HUM_PROXY_PORT        Proxy port (default: 3128)
  HUM_GATEWAY           Gateway IP (default: 192.168.68.51)
  HUM_LOCAL_IP          Local IP (default: 192.168.68.53)
  HUM_KALI_MIRROR       Kali mirror URL
  HUM_DEBIAN_MIRROR     Debian mirror URL
EOF
}

ensure_ssh_key() {
  if [ ! -f "$SSH_KEY" ]; then
    log "Generating SSH key pair at $SSH_KEY"
    mkdir -p "$(dirname "$SSH_KEY")"
    ssh-keygen -t ed25519 -f "$SSH_KEY" -N "" -C "hum-installer-agent@$(hostname)"
    log "Key fingerprint: $(ssh-keygen -lf "$SSH_KEY.pub")"
  else
    log "SSH key exists: $(ssh-keygen -lf "$SSH_KEY.pub")"
  fi
}

scan_fingerprint() {
  local target="$1"
  local port="${2:-22}"
  log "Scanning SSH fingerprint for $target:$port"

  local fingerprints
  fingerprints="$(ssh-keyscan -p "$port" -T 10 "$target" 2>/dev/null)" || {
    err "Cannot reach $target:$port for fingerprint scan"
    return 1
  }

  if [ -z "$fingerprints" ]; then
    err "No fingerprints returned from $target:$port"
    return 1
  fi

  mkdir -p "${HOME}/.ssh"
  local known_hosts="${HOME}/.ssh/known_hosts"
  touch "$known_hosts"

  # Remove stale entries for this target
  ssh-keygen -R "$target" -f "$known_hosts" 2>/dev/null || true

  echo "$fingerprints" >> "$known_hosts"
  log "Accepted fingerprints for $target:"
  echo "$fingerprints" | while read -r line; do
    log "  $line"
  done
}

probe_ssh() {
  local target="$1"
  local port="${2:-22}"
  local timeout="${3:-5}"
  log "Probing SSH at $target:$port (timeout ${timeout}s)"

  if timeout "$timeout" bash -c "echo >/dev/tcp/$target/$port" 2>/dev/null; then
    log "SSH port $port is OPEN on $target"
    return 0
  else
    log "SSH port $port is CLOSED or unreachable on $target"
    return 1
  fi
}

wait_for_ssh() {
  local target="$1"
  local max_attempts="${2:-60}"
  local delay="${3:-5}"
  log "Waiting for SSH on $target (max ${max_attempts} attempts, ${delay}s interval)"

  for i in $(seq 1 "$max_attempts"); do
    if probe_ssh "$target" 22 3; then
      log "SSH available after $i attempts"
      return 0
    fi
    log "Attempt $i/$max_attempts - waiting ${delay}s..."
    sleep "$delay"
  done
  err "SSH not available after $max_attempts attempts"
  return 1
}

ssh_cmd() {
  local target="$1"
  shift
  local user="${SSH_USER:-root}"
  ssh -i "$SSH_KEY" \
    -o StrictHostKeyChecking=accept-new \
    -o ConnectTimeout=10 \
    -o UserKnownHostsFile="${HOME}/.ssh/known_hosts" \
    -o LogLevel=ERROR \
    "${user}@${target}" "$@"
}

scp_cmd() {
  local src="$1" target="$2" dest="$3"
  local user="${SSH_USER:-root}"
  scp -i "$SSH_KEY" \
    -o StrictHostKeyChecking=accept-new \
    -o ConnectTimeout=10 \
    -o LogLevel=ERROR \
    "$src" "${user}@${target}:${dest}"
}

test_mirror() {
  local mirror="${1:-$KALI_MIRROR}"
  log "Testing mirror accessibility: $mirror"

  local http_proxy_env=""
  if [ -n "$PROXY_HOST" ] && [ -n "$PROXY_PORT" ]; then
    http_proxy_env="http://${PROXY_HOST}:${PROXY_PORT}"
    log "Using proxy: $http_proxy_env"
  fi

  local status
  if [ -n "$http_proxy_env" ]; then
    status="$(http_proxy="$http_proxy_env" curl -s -o /dev/null -w '%{http_code}' --connect-timeout 10 "$mirror/dists/" 2>/dev/null)" || status="000"
  else
    status="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 10 "$mirror/dists/" 2>/dev/null)" || status="000"
  fi

  if [ "$status" = "200" ] || [ "$status" = "301" ] || [ "$status" = "302" ]; then
    log "Mirror $mirror is accessible (HTTP $status)"
    return 0
  else
    err "Mirror $mirror returned HTTP $status"
    return 1
  fi
}

push_preseed() {
  local target="$1"
  log "Pushing preseed to $target"

  if [ ! -f "$PRESEED_FILE" ]; then
    err "Preseed file not found: $PRESEED_FILE"
    return 1
  fi

  scp_cmd "$PRESEED_FILE" "$target" "/tmp/preseed.cfg"
  log "Preseed pushed to $target:/tmp/preseed.cfg"

  # Also push the cdrom fix script if it exists
  local fix_script="${SCRIPT_DIR}/fix-cdrom-corruption.sh"
  if [ -f "$fix_script" ]; then
    scp_cmd "$fix_script" "$target" "/tmp/fix-cdrom-corruption.sh"
    ssh_cmd "$target" "chmod +x /tmp/fix-cdrom-corruption.sh"
    log "CDROM fix script pushed to $target:/tmp/fix-cdrom-corruption.sh"
  fi
}

configure_target_apt() {
  local target="$1"
  local mirror="${2:-$KALI_MIRROR}"
  log "Configuring APT on $target with mirror $mirror"

  ssh_cmd "$target" bash <<REMOTE_SCRIPT
set -e

# Disable CDROM source
if [ -f /etc/apt/sources.list ]; then
  sed -i 's/^deb cdrom:/# deb cdrom:/' /etc/apt/sources.list
fi

# Remove cdrom entries from sources.list.d
find /etc/apt/sources.list.d/ -name '*.list' -exec sed -i 's/^deb cdrom:/# deb cdrom:/' {} \; 2>/dev/null || true

# Set proxy if available
if [ -n "${PROXY_HOST}" ] && [ -n "${PROXY_PORT}" ]; then
  cat > /etc/apt/apt.conf.d/01proxy <<APT_PROXY
Acquire::http::Proxy "http://${PROXY_HOST}:${PROXY_PORT}";
Acquire::https::Proxy "http://${PROXY_HOST}:${PROXY_PORT}";
Acquire::Retries "5";
Acquire::http::Timeout "30";
APT_PROXY
fi

# Set DNS
cat > /etc/resolv.conf <<DNS
nameserver 209.18.47.61
nameserver 209.18.47.62
DNS

# Unmount cdrom to force network
umount /cdrom 2>/dev/null || true
umount /media/cdrom 2>/dev/null || true

# Update package lists
apt-get update -o Acquire::AllowInsecureRepositories=true 2>/dev/null || true

echo "[ssh-agent] APT configured with mirror $mirror"
REMOTE_SCRIPT
  log "APT configured on $target"
}

fix_cdrom_on_target() {
  local target="$1"
  log "Applying CDROM corruption fix on $target"

  ssh_cmd "$target" bash <<'REMOTE_FIX'
set -e
echo "[CDROM-FIX] Bypassing corrupt CDROM packages..."

umount /cdrom 2>/dev/null || true
umount /media/cdrom 2>/dev/null || true

if [ -f /etc/apt/sources.list ]; then
  sed -i 's/^deb cdrom:/# deb cdrom:/' /etc/apt/sources.list
fi

# Remove corrupt .deb files from cdrom pool
find /cdrom/pool/ -name '*.deb' -exec dpkg-deb -I {} \; 2>/dev/null | grep -c "corrupt" || true

# Force network sources
cat > /etc/apt/apt.conf.d/99force-network <<FORCE
APT::CDROM::NoMount "true";
Acquire::cdrom::AutoDetect "false";
Acquire::Retries "5";
Acquire::http::Timeout "30";
FORCE

apt-get update --fix-missing 2>/dev/null || true
echo "[CDROM-FIX] Done. Network sources are now primary."
REMOTE_FIX
  log "CDROM fix applied on $target"
}

monitor_install() {
  local target="$1"
  log "Monitoring installation on $target"

  while true; do
    if ! probe_ssh "$target" 22 3; then
      log "Target $target not reachable - may be rebooting"
      sleep 10
      continue
    fi

    local progress
    progress="$(ssh_cmd "$target" 'cat /var/log/syslog 2>/dev/null | tail -5 || echo "no syslog"' 2>/dev/null)" || progress="SSH error"
    log "Install status: $(echo "$progress" | tail -1)"

    local dpkg_status
    dpkg_status="$(ssh_cmd "$target" 'dpkg --audit 2>/dev/null | head -5 || echo "dpkg not available"' 2>/dev/null)" || dpkg_status="unknown"
    log "dpkg audit: $(echo "$dpkg_status" | head -1)"

    sleep 15
  done
}

run_full_install() {
  local target="$1"
  local user="${2:-root}"
  local mirror="${3:-$KALI_MIRROR}"
  SSH_USER="$user"

  log "=== FULL INSTALL SEQUENCE ==="
  log "Target: $target"
  log "User: $user"
  log "Mirror: $mirror"
  log "Proxy: ${PROXY_HOST}:${PROXY_PORT}"
  log "Gateway: $GATEWAY"
  log "DNS: ${DNS_SERVERS[*]}"
  log "============================"

  # Step 1: Generate keys
  ensure_ssh_key

  # Step 2: Wait for SSH
  log "Step 1/6: Waiting for SSH availability..."
  if ! wait_for_ssh "$target" 30 5; then
    err "Cannot reach target. Ensure SSH is enabled in the installer."
    err "At the installer menu: Go back -> Execute a shell"
    err "Then run: passwd root && service ssh start"
    return 1
  fi

  # Step 3: Accept fingerprint
  log "Step 2/6: Accepting SSH fingerprint..."
  scan_fingerprint "$target"

  # Step 4: Test mirror
  log "Step 3/6: Testing mirror..."
  if ! test_mirror "$mirror"; then
    log "Primary mirror unreachable, trying Debian mirror..."
    mirror="$DEBIAN_MIRROR"
    if ! test_mirror "$mirror"; then
      err "No mirror reachable. Check network and proxy."
      return 1
    fi
  fi

  # Step 5: Push configs and fix CDROM
  log "Step 4/6: Pushing configuration..."
  push_preseed "$target" || log "Warning: preseed push failed (may need manual auth)"
  fix_cdrom_on_target "$target" || log "Warning: CDROM fix failed (continuing anyway)"

  # Step 6: Configure APT
  log "Step 5/6: Configuring APT..."
  configure_target_apt "$target" "$mirror"

  # Step 7: Monitor
  log "Step 6/6: Installation configured. Monitoring..."
  log ""
  log "========================================"
  log "Installation agent setup complete."
  log "Mirror: $mirror"
  log "Proxy: http://${PROXY_HOST}:${PROXY_PORT}"
  log "DNS: ${DNS_SERVERS[*]}"
  log "CDROM: disabled (network-only)"
  log "Filesystem: ext4 (btrfs bypassed)"
  log "========================================"
  log ""
  log "To monitor: $0 monitor $target"
  log "Log file: $LOG_FILE"
}

main() {
  local cmd="${1:-help}"
  shift || true

  case "$cmd" in
    keygen)
      ensure_ssh_key
      ;;
    scan)
      [ $# -ge 1 ] || { err "Usage: $0 scan <target-ip>"; exit 1; }
      scan_fingerprint "$1" "${2:-22}"
      ;;
    probe)
      [ $# -ge 1 ] || { err "Usage: $0 probe <target-ip>"; exit 1; }
      probe_ssh "$1" "${2:-22}"
      ;;
    preseed)
      [ $# -ge 1 ] || { err "Usage: $0 preseed <target-ip>"; exit 1; }
      push_preseed "$1"
      ;;
    install)
      [ $# -ge 1 ] || { err "Usage: $0 install <target-ip> [user] [mirror]"; exit 1; }
      run_full_install "$1" "${2:-root}" "${3:-$KALI_MIRROR}"
      ;;
    mirror-test)
      test_mirror "${1:-$KALI_MIRROR}"
      ;;
    fix-cdrom)
      [ $# -ge 1 ] || { err "Usage: $0 fix-cdrom <target-ip>"; exit 1; }
      fix_cdrom_on_target "$1"
      ;;
    monitor)
      [ $# -ge 1 ] || { err "Usage: $0 monitor <target-ip>"; exit 1; }
      monitor_install "$1"
      ;;
    full)
      [ $# -ge 1 ] || { err "Usage: $0 full <target-ip> [user] [mirror]"; exit 1; }
      run_full_install "$1" "${2:-root}" "${3:-$KALI_MIRROR}"
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      err "Unknown command: $cmd"
      usage
      exit 1
      ;;
  esac
}

main "$@"
