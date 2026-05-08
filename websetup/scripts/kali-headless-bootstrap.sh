#!/usr/bin/env bash
# Kali headless push-through helper.
# Run on a Kali host to align SSH, time, Docker, and SDV bootstrap paths.
set -euo pipefail

STEP="${1:-all}"
TZ_VALUE="${TZ:-America/Chicago}"

log() {
  echo "[bootstrap] $*"
}

ensure_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "Run as root (or via sudo)." >&2
    exit 1
  fi
}

project_root() {
  if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
    getent passwd "$SUDO_USER" | cut -d: -f6
  else
    echo "${SDV_ROOT:-$HOME}"
  fi
}

step_base() {
  log "Installing base runtime packages"
  apt-get update
  apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    iproute2 \
    iptables \
    jq \
    openssh-server \
    python3 \
    python3-pip \
    python3-venv \
    tcpdump
}

step_ssh() {
  log "Enabling SSH service"
  systemctl enable --now ssh
  systemctl --no-pager --full status ssh | sed -n '1,8p' || true
}

step_time() {
  log "Setting timezone and enabling NTP"
  timedatectl set-timezone "$TZ_VALUE"
  timedatectl set-ntp true || true
  timedatectl status | sed -n '1,12p' || true
}

step_docker() {
  log "Installing/enabling Docker"
  apt-get install -y --no-install-recommends docker.io
  systemctl enable --now docker
  ip -brief addr show docker0 || true
}

step_sdv() {
  local root
  root="$(project_root)"
  log "Running SDV apply from $root"
  if [[ ! -d "$root/websetup/sdv" ]]; then
    echo "Missing $root/websetup/sdv. Copy repo first." >&2
    exit 1
  fi
  PYTHONPATH="$root" python3 -m websetup.sdv apply
}

step_semgrep() {
  local root
  root="$(project_root)"
  log "Preparing Semgrep bootstrap from $root"
  if [[ ! -x "$root/scripts/setup-semgrep-plugin.sh" ]]; then
    echo "Missing $root/scripts/setup-semgrep-plugin.sh. Copy repo first." >&2
    exit 1
  fi
  bash "$root/scripts/setup-semgrep-plugin.sh" bootstrap-kali-iso
}

ensure_root

case "$STEP" in
  all)
    step_base
    step_ssh
    step_time
    step_docker
    ;;
  base) step_base ;;
  ssh) step_ssh ;;
  time) step_time ;;
  docker) step_docker ;;
  sdv) step_sdv ;;
  semgrep|setup-semgrep-plugin|bootstrap-kali-iso) step_semgrep ;;
  *)
    echo "Usage: sudo bash kali-headless-bootstrap.sh {all|base|ssh|time|docker|sdv|semgrep}" >&2
    exit 1
    ;;
esac
