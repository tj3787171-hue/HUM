#!/usr/bin/env bash
# Discover Docker-identity access and exact Chromebook boot-crash units.
# Designed for Penguin, laptop, and BELL recovery-cursor-agent.service.
# This script never talks to institute-hikvision-probe.service.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNITS_FILE="${HUM_RECOVERY_UNITS_FILE:-${SCRIPT_DIR}/hum-recovery-access.units}"
RECOVERY_UNIT="${HUM_RECOVERY_UNIT:-recovery-cursor-agent.service}"
PLYMOUTH_UNIT="plymouth-quit-wait.service"
SKIP_UNIT="institute-hikvision-probe.service"
DOCKER_HINT_IF="${HUM_DOCKER_HINT_IF:-docker0}"
UBUNTU_START_HOST="${HUM_UBUNTU_START_HOST:-10.10.2.2}"
UBUNTU_START_PORT="${HUM_UBUNTU_START_PORT:-8443}"
UBUNTU_START_URL="${HUM_UBUNTU_START_URL:-https://${UBUNTU_START_HOST}:${UBUNTU_START_PORT}}"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/hum-recovery-access.sh discover
  bash scripts/hum-recovery-access.sh boot-units
  bash scripts/hum-recovery-access.sh binfmt-status
  bash scripts/hum-recovery-access.sh kaudit-report
  bash scripts/hum-recovery-access.sh plymouth-status
  sudo bash scripts/hum-recovery-access.sh plymouth-start
  sudo bash scripts/hum-recovery-access.sh plymouth-stop
  bash scripts/hum-recovery-access.sh ssh-hint
  bash scripts/hum-recovery-access.sh start-hint
  sudo bash scripts/hum-recovery-access.sh mask-fwupd --i-am-on-chromebook-penguin

discover       Read-only: recovery unit, Docker, docker0. No LAN sweep.
boot-units     Exact status of cataloged crash units (fwupd, binfmt, plymouth).
binfmt-status  List /proc/sys/fs/binfmt_misc entries (report only).
kaudit-report  Count recent kauditd_printk lines (report only).
plymouth-*     Status/start/stop plymouth-quit-wait.service only.
ssh-hint       Print SSH targets from Docker published ports / container IPs.
start-hint     Print the known Ubuntu-start URL (default https://10.10.2.2:8443).
mask-fwupd     Mask fwupd* only. Requires --i-am-on-chromebook-penguin.

Never touches institute-hikvision-probe.service.
Does not copy personal-use files.
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_units_file() {
  [[ -f "$UNITS_FILE" ]] || die "units catalog missing: $UNITS_FILE"
}

is_skip_unit() {
  local name="$1"
  [[ "$name" == "$SKIP_UNIT" ]]
}

foreach_catalog() {
  local kind_filter="${1:-}"
  require_units_file
  while IFS=$'\t' read -r kind unit role; do
    [[ -z "${kind:-}" || "$kind" == \#* ]] && continue
    if [[ -n "$kind_filter" && "$kind" != "$kind_filter" ]]; then
      continue
    fi
    printf '%s\t%s\t%s\n' "$kind" "$unit" "$role"
  done < "$UNITS_FILE"
}

unit_state() {
  local unit="$1"
  if is_skip_unit "$unit"; then
    printf 'skipped\tskipped\tskipped\n'
    return 0
  fi
  if ! command -v systemctl >/dev/null 2>&1; then
    printf 'no-systemctl\tno-systemctl\tno-systemctl\n'
    return 0
  fi
  local load active sub
  load="$(systemctl show -p LoadState --value "$unit" 2>/dev/null || echo unknown)"
  active="$(systemctl show -p ActiveState --value "$unit" 2>/dev/null || echo unknown)"
  sub="$(systemctl show -p SubState --value "$unit" 2>/dev/null || echo unknown)"
  printf '%s\t%s\t%s\n' "$load" "$active" "$sub"
}

cmd_discover() {
  echo "=== recovery unit ==="
  echo "unit: $RECOVERY_UNIT"
  if is_skip_unit "$RECOVERY_UNIT"; then
    die "recovery unit is the skip unit; refusing"
  fi
  if command -v systemctl >/dev/null 2>&1; then
    systemctl is-enabled "$RECOVERY_UNIT" 2>/dev/null || echo "enabled: unknown"
    systemctl is-active "$RECOVERY_UNIT" 2>/dev/null || echo "active: unknown"
    systemctl show -p Id,FragmentPath,ActiveState,SubState,Description --no-pager "$RECOVERY_UNIT" 2>/dev/null || true
  else
    echo "systemctl: missing"
  fi

  echo
  echo "=== docker ==="
  if command -v docker >/dev/null 2>&1; then
    docker ps -a --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || echo "docker ps failed"
    echo
    echo "networks:"
    docker network ls 2>/dev/null || true
  else
    echo "docker: missing"
  fi

  echo
  echo "=== ${DOCKER_HINT_IF} ==="
  if command -v ip >/dev/null 2>&1; then
    ip -brief addr show dev "$DOCKER_HINT_IF" 2>/dev/null || echo "${DOCKER_HINT_IF}: not present"
  else
    echo "ip: missing (install iproute2 on this host)"
  fi

  echo
  cmd_start_hint
}

cmd_boot_units() {
  printf 'kind\tunit\trole\tload\tactive\tsub\n'
  while IFS=$'\t' read -r kind unit role; do
    if is_skip_unit "$unit"; then
      printf '%s\t%s\t%s\tnever-touch\tnever-touch\tnever-touch\n' "$kind" "$unit" "$role"
      continue
    fi
    local state
    state="$(unit_state "$unit")"
    printf '%s\t%s\t%s\t%s\n' "$kind" "$unit" "$role" "$state"
  done < <(foreach_catalog)
}

cmd_binfmt_status() {
  local root="/proc/sys/fs/binfmt_misc"
  echo "=== binfmt_misc ==="
  if [[ ! -d "$root" ]]; then
    echo "path: missing ($root)"
    return 0
  fi
  echo "path: $root"
  if [[ -f "${root}/status" ]]; then
    echo "status: $(cat "${root}/status" 2>/dev/null || echo unknown)"
  fi
  local entry base
  shopt -s nullglob
  for entry in "$root"/*; do
    base="$(basename "$entry")"
    case "$base" in
      status|register) continue ;;
    esac
    echo "--- $base ---"
    cat "$entry" 2>/dev/null || echo "(unreadable)"
  done
  shopt -u nullglob
}

cmd_kaudit_report() {
  echo "=== kauditd_printk ==="
  local count=0
  if command -v journalctl >/dev/null 2>&1; then
    count="$(journalctl -k -b --no-pager 2>/dev/null | grep -c 'kauditd_printk' || true)"
    echo "journalctl -k -b matches: $count"
    journalctl -k -b --no-pager 2>/dev/null | grep 'kauditd_printk' | tail -n 5 || true
  elif command -v dmesg >/dev/null 2>&1; then
    count="$(dmesg 2>/dev/null | grep -c 'kauditd_printk' || true)"
    echo "dmesg matches: $count"
    dmesg 2>/dev/null | grep 'kauditd_printk' | tail -n 5 || true
  else
    echo "journalctl/dmesg: missing"
  fi
}

assert_not_skip() {
  local unit="$1"
  if is_skip_unit "$unit"; then
    die "refusing to operate on $SKIP_UNIT"
  fi
}

cmd_plymouth() {
  local action="$1"
  assert_not_skip "$PLYMOUTH_UNIT"
  command -v systemctl >/dev/null 2>&1 || die "systemctl missing"
  case "$action" in
    status)
      systemctl --no-pager --full status "$PLYMOUTH_UNIT" || true
      ;;
    start|stop)
      [[ "${EUID:-$(id -u)}" -eq 0 ]] || die "plymouth-${action} requires root"
      systemctl "$action" "$PLYMOUTH_UNIT"
      systemctl is-active "$PLYMOUTH_UNIT" || true
      ;;
    *)
      die "unknown plymouth action: $action"
      ;;
  esac
}

cmd_start_hint() {
  echo "=== ubuntu start endpoint ==="
  echo "host: $UBUNTU_START_HOST"
  echo "port: $UBUNTU_START_PORT"
  echo "url:  $UBUNTU_START_URL"
  echo "role: known-working HTTPS start for the Ubuntu server"
  echo "This is the current start path; BELL LAN IP remains unknown."
}

cmd_ssh_hint() {
  echo "=== ssh hint (Docker identity, no connect) ==="
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker missing; cannot derive published ports"
    echo "After discover on BELL, SSH to a container IP or published host port."
    return 0
  fi
  docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | while read -r name ports; do
    [[ -z "${name:-}" ]] && continue
    echo "container: $name"
    echo "  ports: ${ports:-none}"
    if echo "${ports:-}" | grep -q '22/tcp'; then
      echo "  hint: ssh -p <published-22> <docker-host>"
    fi
  done
  docker ps -q 2>/dev/null | while read -r id; do
    ip="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' "$id" 2>/dev/null || true)"
    name="$(docker inspect -f '{{.Name}}' "$id" 2>/dev/null || true)"
    echo "container ${name:-$id} ip: ${ip:-none}"
    if [[ -n "${ip:-}" ]]; then
      echo "  hint: ssh root@${ip%% *}"
    fi
  done
}

looks_like_crostini() {
  [[ -d /opt/google/cros-containers ]] && return 0
  [[ -f /dev/.cros_milestone ]] && return 0
  [[ "$(hostname 2>/dev/null || true)" == *penguin* ]] && return 0
  return 1
}

cmd_mask_fwupd() {
  local confirmed=0
  for arg in "$@"; do
    if [[ "$arg" == "--i-am-on-chromebook-penguin" ]]; then
      confirmed=1
    fi
  done
  [[ "$confirmed" -eq 1 ]] || die "refusing mask-fwupd without --i-am-on-chromebook-penguin"
  looks_like_crostini || die "this host does not look like Crostini/penguin"
  [[ "${EUID:-$(id -u)}" -eq 0 ]] || die "mask-fwupd requires root"
  command -v systemctl >/dev/null 2>&1 || die "systemctl missing"

  while IFS=$'\t' read -r kind unit role; do
    is_skip_unit "$unit" && continue
    [[ "$role" == "firmware-update" ]] || continue
    echo "masking $unit"
    systemctl stop "$unit" 2>/dev/null || true
    systemctl mask "$unit"
  done < <(foreach_catalog crash)
  echo "fwupd units masked. binfmt and hikvision were not changed."
}

main() {
  local cmd="${1:-help}"
  shift || true
  case "$cmd" in
    discover) cmd_discover ;;
    boot-units) cmd_boot_units ;;
    binfmt-status) cmd_binfmt_status ;;
    kaudit-report) cmd_kaudit_report ;;
    plymouth-status) cmd_plymouth status ;;
    plymouth-start) cmd_plymouth start ;;
    plymouth-stop) cmd_plymouth stop ;;
    ssh-hint) cmd_ssh_hint ;;
    start-hint) cmd_start_hint ;;
    mask-fwupd) cmd_mask_fwupd "$@" ;;
    -h|--help|help) usage ;;
    *)
      usage
      exit 2
      ;;
  esac
}

main "$@"
