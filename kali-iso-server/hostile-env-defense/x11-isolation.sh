#!/bin/sh
# X11/Xorg Isolation
# Disables hostile X11 components that disrupt installation.
# Isolates haveged, ICE authority, and Xserver interference.
set -e

LOG="/tmp/x11-isolation.log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

log "X11 ISOLATION - Preventing Interference"

# Phase 1: Stop interfering X11 services
stop_x11_services() {
  log "Phase 1: Stopping X11/display services"

  for svc in gdm3 gdm lightdm sddm xdm slim display-manager; do
    if systemctl is-active "$svc" >/dev/null 2>&1; then
      systemctl stop "$svc" 2>/dev/null || true
      systemctl disable "$svc" 2>/dev/null || true
      log "  Stopped: $svc"
    fi
  done

  # Stop Xorg directly
  if pidof Xorg >/dev/null 2>&1; then
    log "  Stopping Xorg processes..."
    killall Xorg 2>/dev/null || true
  fi
  if pidof X >/dev/null 2>&1; then
    killall X 2>/dev/null || true
  fi
}

# Phase 2: Neutralize Xauthority files
neutralize_xauthority() {
  log "Phase 2: Neutralizing Xauthority"

  # Find and quarantine Xauthority files
  local quarantine="/tmp/x11-quarantine"
  mkdir -p "$quarantine"

  find / -maxdepth 4 -name '.Xauthority' -type f 2>/dev/null | while read -r xauth; do
    local safe_name
    safe_name="$(echo "$xauth" | tr '/' '_')"
    cp "$xauth" "$quarantine/$safe_name" 2>/dev/null || true
    : > "$xauth"
    chattr +i "$xauth" 2>/dev/null || true
    log "  Neutralized: $xauth"
  done

  # Block new Xauthority creation
  for home_dir in /root /home/*; do
    if [ -d "$home_dir" ]; then
      touch "$home_dir/.Xauthority"
      : > "$home_dir/.Xauthority"
      chattr +i "$home_dir/.Xauthority" 2>/dev/null || true
    fi
  done

  # Unset DISPLAY and XAUTHORITY
  unset DISPLAY XAUTHORITY 2>/dev/null || true
  log "  DISPLAY and XAUTHORITY unset"
}

# Phase 3: Isolate ICE authority
isolate_ice() {
  log "Phase 3: Isolating ICE authority"

  # Find and neutralize ICE authority files
  find / -maxdepth 4 -name '.ICEauthority' -type f 2>/dev/null | while read -r ice; do
    : > "$ice"
    chattr +i "$ice" 2>/dev/null || true
    log "  Neutralized: $ice"
  done

  # Block ICE protocol connections
  for home_dir in /root /home/*; do
    if [ -d "$home_dir" ]; then
      touch "$home_dir/.ICEauthority"
      : > "$home_dir/.ICEauthority"
      chattr +i "$home_dir/.ICEauthority" 2>/dev/null || true
    fi
  done

  log "  ICE authority isolated"
}

# Phase 4: Manage haveged
manage_haveged() {
  log "Phase 4: Managing haveged"

  if systemctl is-active haveged >/dev/null 2>&1; then
    log "  haveged is running - checking entropy pool"
    local entropy
    entropy="$(cat /proc/sys/kernel/random/entropy_avail 2>/dev/null || echo 0)"
    log "  Current entropy: $entropy"

    if [ "$entropy" -gt 256 ]; then
      log "  Entropy sufficient, stopping haveged to reduce interference"
      systemctl stop haveged 2>/dev/null || true
    else
      log "  Entropy low, keeping haveged but limiting CPU"
      # Limit haveged CPU usage
      if command -v cpulimit >/dev/null 2>&1; then
        local hpid
        hpid="$(pidof haveged 2>/dev/null || true)"
        if [ -n "$hpid" ]; then
          cpulimit -p "$hpid" -l 10 -b 2>/dev/null || true
          log "  haveged CPU limited to 10%"
        fi
      fi
    fi
  else
    log "  haveged not running"
  fi
}

# Phase 5: Block X11 socket creation
block_x11_sockets() {
  log "Phase 5: Blocking X11 sockets"

  # Block /tmp/.X11-unix socket directory
  if [ -d /tmp/.X11-unix ]; then
    rm -rf /tmp/.X11-unix/*
    log "  Cleared /tmp/.X11-unix"
  fi
  mkdir -p /tmp/.X11-unix
  chmod 000 /tmp/.X11-unix
  chattr +i /tmp/.X11-unix 2>/dev/null || true

  # Block X11 TCP port (6000-6063)
  if command -v iptables >/dev/null 2>&1; then
    iptables -A INPUT -p tcp --dport 6000:6063 -j DROP 2>/dev/null || true
    iptables -A OUTPUT -p tcp --dport 6000:6063 -j DROP 2>/dev/null || true
    log "  X11 TCP ports blocked (6000-6063)"
  fi

  log "  X11 sockets blocked"
}

# Phase 6: Protect /etc/X11 from takeover
protect_etc_x11() {
  log "Phase 6: Protecting /etc/X11"

  if [ -d /etc/X11 ]; then
    # Backup current config
    tar cf /tmp/x11-quarantine/etc-X11-backup.tar /etc/X11/ 2>/dev/null || true

    # Make xorg.conf read-only
    if [ -f /etc/X11/xorg.conf ]; then
      chattr +i /etc/X11/xorg.conf 2>/dev/null || true
      log "  xorg.conf made immutable"
    fi
  fi
}

main() {
  local cmd="${1:-all}"
  case "$cmd" in
    all)
      stop_x11_services
      neutralize_xauthority
      isolate_ice
      manage_haveged
      block_x11_sockets
      protect_etc_x11
      log ""
      log "X11 isolation complete."
      log "X11, ICE, and haveged interference neutralized."
      ;;
    services) stop_x11_services ;;
    xauthority) neutralize_xauthority ;;
    ice) isolate_ice ;;
    haveged) manage_haveged ;;
    sockets) block_x11_sockets ;;
    protect) protect_etc_x11 ;;
    *)
      echo "Usage: $0 {all|services|xauthority|ice|haveged|sockets|protect}"
      exit 1
      ;;
  esac
}

main "$@"
