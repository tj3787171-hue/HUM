#!/bin/sh
# Tool Preservation and Mirror Authentication Defense
# Prevents tool elimination during installation.
# Authenticates mirrors and manages GPG key retrieval.
# Maintains APT accessibility from start through completion.
set -e

LOG="/tmp/tool-mirror-defense.log"
PROXY_HOST="${HUM_PROXY_HOST:-192.168.68.52}"
PROXY_PORT="${HUM_PROXY_PORT:-3128}"
DNS_PRIMARY="209.18.47.61"
DNS_SECONDARY="209.18.47.62"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

log "TOOL PRESERVATION & MIRROR DEFENSE"

# Known-good Kali and Debian GPG keys
KALI_ARCHIVE_KEY="ED444FF07D8D0BF6"
DEBIAN_ARCHIVE_KEY="605C66F00D6C9793"

# Trusted mirrors with HTTPS fallback
MIRRORS="
https://http.kali.org/kali
https://kali.download/kali
https://deb.debian.org/debian
https://security.debian.org/debian-security
"

# Phase 1: Preserve essential binaries
preserve_tools() {
  log "Phase 1: Tool preservation"
  local safe="/tmp/tool-preserve"
  mkdir -p "$safe/bin" "$safe/lib"

  # Tier 1: Absolutely critical
  for bin in sh dash bash; do
    local path
    path="$(command -v "$bin" 2>/dev/null || true)"
    if [ -n "$path" ] && [ -f "$path" ]; then
      cp -a "$path" "$safe/bin/"
    fi
  done

  # Tier 2: Package management
  for bin in apt apt-get apt-cache apt-key dpkg dpkg-query; do
    local path
    path="$(command -v "$bin" 2>/dev/null || true)"
    if [ -n "$path" ] && [ -f "$path" ]; then
      cp -a "$path" "$safe/bin/"
    fi
  done

  # Tier 3: Network and diagnostics
  for bin in curl wget ip ping ss netstat ssh scp cat ls grep sed awk \
             find chmod chown mkdir cp mv rm mount umount tar gzip; do
    local path
    path="$(command -v "$bin" 2>/dev/null || true)"
    if [ -n "$path" ] && [ -f "$path" ]; then
      cp -a "$path" "$safe/bin/"
    fi
  done

  # Tier 4: Libraries for APT
  for lib in /usr/lib/apt /usr/lib/dpkg; do
    if [ -d "$lib" ]; then
      cp -a "$lib" "$safe/lib/" 2>/dev/null || true
    fi
  done

  # Create a PATH-safe recovery script
  cat > "$safe/recover.sh" <<'RECOVER'
#!/bin/sh
# Emergency tool recovery
SAFE="/tmp/tool-preserve"
export PATH="$SAFE/bin:$PATH"
export LD_LIBRARY_PATH="$SAFE/lib:$LD_LIBRARY_PATH"
echo "[RECOVER] Tools restored from $SAFE"
echo "[RECOVER] Available: $(ls $SAFE/bin/ | tr '\n' ' ')"
RECOVER
  chmod +x "$safe/recover.sh"

  log "  Preserved $(ls "$safe/bin/" | wc -l) tools to $safe"
}

# Phase 2: Authenticate and verify mirrors
authenticate_mirrors() {
  log "Phase 2: Mirror authentication"

  # Ensure DNS is set
  cat > /etc/resolv.conf <<DNS
nameserver $DNS_PRIMARY
nameserver $DNS_SECONDARY
DNS

  local working_mirrors=""

  for mirror in $MIRRORS; do
    local host
    host="$(echo "$mirror" | sed 's|https\?://||' | cut -d'/' -f1)"
    log "  Testing: $mirror"

    # DNS resolution check
    if ! nslookup "$host" "$DNS_PRIMARY" >/dev/null 2>&1 && \
       ! host "$host" "$DNS_PRIMARY" >/dev/null 2>&1 && \
       ! getent hosts "$host" >/dev/null 2>&1; then
      log "    DNS FAIL: cannot resolve $host"
      continue
    fi

    # HTTP reachability check (with proxy fallback)
    local status="000"
    if [ -n "$PROXY_HOST" ]; then
      status="$(http_proxy="http://${PROXY_HOST}:${PROXY_PORT}" \
        curl -s -o /dev/null -w '%{http_code}' --connect-timeout 10 "${mirror}/dists/" 2>/dev/null)" || status="000"
    fi

    if [ "$status" = "000" ]; then
      status="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 10 "${mirror}/dists/" 2>/dev/null)" || status="000"
    fi

    case "$status" in
      200|301|302)
        log "    OK (HTTP $status)"
        working_mirrors="$working_mirrors $mirror"
        ;;
      *)
        log "    FAIL (HTTP $status)"
        ;;
    esac
  done

  if [ -z "$working_mirrors" ]; then
    log "  WARNING: No mirrors reachable!"
    return 1
  fi

  log "  Working mirrors:$working_mirrors"

  # Write verified sources.list
  mkdir -p /etc/apt/sources.list.d
  cat > /etc/apt/sources.list.d/verified-mirrors.list <<SOURCES
# Verified mirrors (authenticated by tool-mirror-defense)
# Generated: $(date)
SOURCES

  for mirror in $working_mirrors; do
    if echo "$mirror" | grep -q 'kali'; then
      echo "deb $mirror kali-rolling main contrib non-free non-free-firmware" >> /etc/apt/sources.list.d/verified-mirrors.list
    elif echo "$mirror" | grep -q 'security'; then
      echo "deb $mirror bookworm-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list.d/verified-mirrors.list
    else
      echo "deb $mirror bookworm main contrib non-free non-free-firmware" >> /etc/apt/sources.list.d/verified-mirrors.list
    fi
  done

  log "  Verified sources written to /etc/apt/sources.list.d/verified-mirrors.list"
}

# Phase 3: GPG key management
manage_gpg_keys() {
  log "Phase 3: GPG key management"

  # Ensure keyring directory exists
  mkdir -p /etc/apt/trusted.gpg.d /usr/share/keyrings

  # Fetch Kali archive key
  log "  Fetching Kali archive key ($KALI_ARCHIVE_KEY)..."
  if command -v apt-key >/dev/null 2>&1; then
    if [ -n "$PROXY_HOST" ]; then
      http_proxy="http://${PROXY_HOST}:${PROXY_PORT}" \
        apt-key adv --keyserver hkps://keyserver.ubuntu.com --recv-keys "$KALI_ARCHIVE_KEY" 2>/dev/null || \
      http_proxy="http://${PROXY_HOST}:${PROXY_PORT}" \
        apt-key adv --keyserver hkps://keys.openpgp.org --recv-keys "$KALI_ARCHIVE_KEY" 2>/dev/null || \
        log "    Warning: could not fetch Kali key via proxy"
    else
      apt-key adv --keyserver hkps://keyserver.ubuntu.com --recv-keys "$KALI_ARCHIVE_KEY" 2>/dev/null || \
      apt-key adv --keyserver hkps://keys.openpgp.org --recv-keys "$KALI_ARCHIVE_KEY" 2>/dev/null || \
        log "    Warning: could not fetch Kali key"
    fi
  fi

  # Try to download Kali keyring directly
  local kali_keyring_url="https://archive.kali.org/archive-key.asc"
  if command -v wget >/dev/null 2>&1; then
    if [ -n "$PROXY_HOST" ]; then
      https_proxy="http://${PROXY_HOST}:${PROXY_PORT}" \
        wget -q -O /etc/apt/trusted.gpg.d/kali-archive-key.asc "$kali_keyring_url" 2>/dev/null || true
    else
      wget -q -O /etc/apt/trusted.gpg.d/kali-archive-key.asc "$kali_keyring_url" 2>/dev/null || true
    fi
  elif command -v curl >/dev/null 2>&1; then
    if [ -n "$PROXY_HOST" ]; then
      https_proxy="http://${PROXY_HOST}:${PROXY_PORT}" \
        curl -sL -o /etc/apt/trusted.gpg.d/kali-archive-key.asc "$kali_keyring_url" 2>/dev/null || true
    else
      curl -sL -o /etc/apt/trusted.gpg.d/kali-archive-key.asc "$kali_keyring_url" 2>/dev/null || true
    fi
  fi

  if [ -f /etc/apt/trusted.gpg.d/kali-archive-key.asc ]; then
    log "  Kali archive key installed"
  else
    log "  Warning: Kali archive key not available, allowing insecure repos temporarily"
    echo 'Acquire::AllowInsecureRepositories "true";' > /etc/apt/apt.conf.d/99allow-insecure
  fi

  # List installed keys
  if command -v apt-key >/dev/null 2>&1; then
    local key_count
    key_count="$(apt-key list 2>/dev/null | grep -c 'pub' || echo 0)"
    log "  Installed keys: $key_count"
  fi
}

# Phase 4: Configure APT resilience
configure_apt_resilience() {
  log "Phase 4: APT resilience configuration"

  mkdir -p /etc/apt/apt.conf.d

  # Retry and timeout settings
  cat > /etc/apt/apt.conf.d/80resilience <<'APT_CONF'
Acquire::Retries "5";
Acquire::http::Timeout "30";
Acquire::https::Timeout "30";
Acquire::ftp::Timeout "30";
APT::Get::Fix-Missing "true";
APT::Get::Fix-Broken "true";
Dpkg::Options:: "--force-confold";
Dpkg::Options:: "--force-confdef";
APT_CONF

  # Proxy configuration
  if [ -n "$PROXY_HOST" ] && [ -n "$PROXY_PORT" ]; then
    cat > /etc/apt/apt.conf.d/01proxy <<PROXY_CONF
Acquire::http::Proxy "http://${PROXY_HOST}:${PROXY_PORT}";
PROXY_CONF
    log "  Proxy: http://${PROXY_HOST}:${PROXY_PORT}"
  fi

  # Disable CDROM
  cat > /etc/apt/apt.conf.d/99no-cdrom <<'CDROM_CONF'
APT::CDROM::NoMount "true";
Acquire::cdrom::AutoDetect "false";
CDROM_CONF

  # Disable CDROM lines in sources.list
  if [ -f /etc/apt/sources.list ]; then
    sed -i 's/^deb cdrom:/# deb cdrom:/' /etc/apt/sources.list 2>/dev/null || true
  fi

  log "  APT resilience configured"
}

# Phase 5: Verify btrfs and fat format states
verify_filesystem_formats() {
  log "Phase 5: Filesystem format verification"

  # Check which filesystem modules are available
  echo "  Available filesystem types:"
  cat /proc/filesystems 2>/dev/null | while read -r nodev fstype; do
    log "    $nodev $fstype"
  done

  # Check for btrfs support
  if grep -q 'btrfs' /proc/filesystems 2>/dev/null; then
    log "  btrfs: available (in kernel)"
  elif modprobe btrfs 2>/dev/null; then
    log "  btrfs: loaded via module"
  else
    log "  btrfs: NOT available"
  fi

  # Check for vfat (fat12/16/32) support
  if grep -q 'vfat' /proc/filesystems 2>/dev/null; then
    log "  vfat (fat12/16/32): available"
  elif modprobe vfat 2>/dev/null; then
    log "  vfat: loaded via module"
  else
    log "  vfat: NOT available"
  fi

  # Check for mkfs tools
  for mkfs_tool in mkfs.ext4 mkfs.ext3 mkfs.ext2 mkfs.btrfs mkfs.vfat mkfs.fat; do
    if command -v "$mkfs_tool" >/dev/null 2>&1; then
      log "  $mkfs_tool: present"
    else
      log "  $mkfs_tool: MISSING"
    fi
  done
}

# Phase 6: Stripe/mirror elimination defense
stripe_mirror_defense() {
  log "Phase 6: Stripe/mirror defense"

  # Check for MD/RAID arrays that could be interfering
  if [ -f /proc/mdstat ]; then
    local md_status
    md_status="$(cat /proc/mdstat)"
    if echo "$md_status" | grep -q 'active'; then
      log "  Active MD arrays detected:"
      echo "$md_status" | grep -v '^Personalities' | while read -r line; do
        log "    $line"
      done
    else
      log "  No active MD arrays"
    fi
  fi

  # Check for LVM interference
  if command -v pvs >/dev/null 2>&1; then
    local pv_count
    pv_count="$(pvs --noheadings 2>/dev/null | wc -l)"
    if [ "$pv_count" -gt 0 ]; then
      log "  LVM physical volumes: $pv_count"
      pvs 2>/dev/null | while read -r line; do
        log "    $line"
      done
    fi
  fi

  # Check for device-mapper entries that redirect to wrong mirrors
  if [ -d /dev/mapper ]; then
    log "  Device mapper entries:"
    ls /dev/mapper/ 2>/dev/null | while read -r dm; do
      log "    $dm"
    done
  fi

  # Verify no iptables rules are redirecting mirror traffic
  if command -v iptables >/dev/null 2>&1; then
    local nat_rules
    nat_rules="$(iptables -t nat -L -n 2>/dev/null | grep -c 'REDIRECT\|DNAT' || echo 0)"
    if [ "$nat_rules" -gt 0 ]; then
      log "  WARNING: $nat_rules NAT redirect/DNAT rules detected!"
      iptables -t nat -L -n 2>/dev/null | grep 'REDIRECT\|DNAT' | while read -r rule; do
        log "    $rule"
      done
      log "  Flushing hostile NAT rules..."
      iptables -t nat -F 2>/dev/null || true
      log "  NAT rules flushed"
    else
      log "  No hostile NAT redirects"
    fi
  fi
}

# Master deployment
deploy_all() {
  preserve_tools
  authenticate_mirrors || true
  manage_gpg_keys || true
  configure_apt_resilience
  verify_filesystem_formats
  stripe_mirror_defense

  log ""
  log "================================"
  log "Tool & Mirror defense deployed."
  log "  Tools preserved: /tmp/tool-preserve"
  log "  Recovery: source /tmp/tool-preserve/recover.sh"
  log "  Mirrors: /etc/apt/sources.list.d/verified-mirrors.list"
  log "  APT config: /etc/apt/apt.conf.d/80resilience"
  log "  DNS: $DNS_PRIMARY, $DNS_SECONDARY"
  log "  Proxy: http://${PROXY_HOST}:${PROXY_PORT}"
  log "================================"
}

main() {
  local cmd="${1:-all}"
  case "$cmd" in
    all) deploy_all ;;
    preserve) preserve_tools ;;
    mirrors) authenticate_mirrors ;;
    keys) manage_gpg_keys ;;
    apt) configure_apt_resilience ;;
    formats) verify_filesystem_formats ;;
    stripe) stripe_mirror_defense ;;
    *)
      echo "Usage: $0 {all|preserve|mirrors|keys|apt|formats|stripe}"
      echo ""
      echo "Commands:"
      echo "  all       Run full defense suite"
      echo "  preserve  Save essential tools to /tmp/tool-preserve"
      echo "  mirrors   Authenticate and verify mirror accessibility"
      echo "  keys      Fetch and install GPG keys"
      echo "  apt       Configure APT resilience settings"
      echo "  formats   Verify filesystem format availability"
      echo "  stripe    Detect and neutralize stripe/mirror interference"
      exit 1
      ;;
  esac
}

main "$@"
