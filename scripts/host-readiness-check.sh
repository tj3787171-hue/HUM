#!/usr/bin/env bash
set -euo pipefail

STRICT_MODE=0
REPORT_DIR="diagnostics"
JSON_OUTPUT=""
MIN_BACKUP_BYTES=1500000000000

for arg in "$@"; do
  case "$arg" in
    --strict)
      STRICT_MODE=1
      ;;
    --json=*)
      JSON_OUTPUT="${arg#*=}"
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: $0 [--strict] [--json=/path/to/report.json]" >&2
      exit 2
      ;;
  esac
done

mkdir -p "$REPORT_DIR"

CHECKS_TOTAL=0
CHECKS_FAILED=0
BACKUP_MATCHES=0
MAC_COUNT=0
TS_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
HOSTNAME_VALUE="$(hostname)"

connectivity_hosts=(
  "github.com"
  "api.github.com"
  "raw.githubusercontent.com"
  "objects.githubusercontent.com"
)

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

report_check() {
  local label="$1"
  local passed="$2"
  CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
  if [[ "$passed" -eq 1 ]]; then
    printf "[PASS] %s\n" "$label"
  else
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
    printf "[FAIL] %s\n" "$label"
  fi
}

echo "Host readiness check (${TS_UTC})"
echo "Hostname: ${HOSTNAME_VALUE}"
echo

echo "=== Backup media discovery (>=1.5 TB, mounted removable/USB/MMC) ==="
if command_exists lsblk; then
  while IFS= read -r row; do
    [[ -z "$row" ]] && continue
    unset NAME SIZE TYPE MOUNTPOINT RM TRAN MODEL
    # lsblk --pairs output is machine-generated and safe to parse.
    eval "$row"
    dev_size="${SIZE:-0}"
    dev_mount="${MOUNTPOINT:-}"
    dev_rm="${RM:-0}"
    dev_tran="${TRAN:-}"

    if [[ "$dev_size" -ge "$MIN_BACKUP_BYTES" ]] \
      && [[ -n "$dev_mount" ]] \
      && [[ "$dev_rm" == "1" || "$dev_tran" == "usb" || "$dev_tran" == "mmc" ]]; then
      BACKUP_MATCHES=$((BACKUP_MATCHES + 1))
      dev_name="${NAME:-unknown}"
      dev_type="${TYPE:-unknown}"
      dev_model="${MODEL:-}"
      echo "Candidate backup device: /dev/${dev_name}"
      echo "  Size bytes: ${dev_size}"
      echo "  Type: ${dev_type}, RM: ${dev_rm}, Transport: ${dev_tran:-n/a}"
      echo "  Mount: ${dev_mount}"
      [[ -n "${dev_model}" ]] && echo "  Model: ${dev_model}"
    fi
  done < <(lsblk -P -b -o NAME,SIZE,TYPE,MOUNTPOINT,RM,TRAN,MODEL)
else
  echo "lsblk command not found; backup media discovery skipped."
  report_check "lsblk command available" 0
fi

if [[ "$BACKUP_MATCHES" -eq 0 ]]; then
  echo "No mounted removable/USB/MMC volume >= 1.5 TB found."
fi

if [[ "$BACKUP_MATCHES" -gt 0 ]]; then
  report_check "Backup media present" 1
else
  report_check "Backup media present" 0
fi
echo

echo "=== Connectivity checks (GitHub and related endpoints) ==="
has_dns_command=0
if command_exists getent || command_exists nslookup || command_exists host; then
  has_dns_command=1
fi

has_curl=0
if command_exists curl; then
  has_curl=1
fi

for host in "${connectivity_hosts[@]}"; do
  dns_ok=0
  https_ok=0

  if [[ "$has_dns_command" -eq 1 ]]; then
    if command_exists getent && getent ahosts "$host" >/dev/null 2>&1; then
      dns_ok=1
    elif command_exists nslookup && nslookup "$host" >/dev/null 2>&1; then
      dns_ok=1
    elif command_exists host && host "$host" >/dev/null 2>&1; then
      dns_ok=1
    fi
  else
    echo "No DNS lookup utility found (getent/nslookup/host)."
  fi
  report_check "DNS resolve ${host}" "$dns_ok"

  if [[ "$has_curl" -eq 1 ]]; then
    if curl -sS -o /dev/null --connect-timeout 5 --max-time 10 "https://${host}"; then
      https_ok=1
    fi
  else
    echo "curl command not found; HTTPS checks cannot run."
  fi
  report_check "HTTPS reach ${host}" "$https_ok"
done

git_remote_ok=0
if command_exists git; then
  if git ls-remote --heads "https://github.com/tj3787171-hue/HUM.git" >/dev/null 2>&1; then
    git_remote_ok=1
  fi
else
  echo "git command not found; git remote reachability skipped."
fi
report_check "Git remote reachability (GitHub)" "$git_remote_ok"
echo

echo "=== Network interfaces and MAC addresses ==="
interface_source="ip"
if ! command_exists ip; then
  interface_source="sysfs"
fi

while IFS= read -r iface; do
  [[ -z "$iface" ]] && continue
  mac_addr="unknown"
  oper_state="unknown"
  ip_addrs=""

  if [[ -f "/sys/class/net/${iface}/address" ]]; then
    mac_addr="$(<"/sys/class/net/${iface}/address")"
  fi
  if [[ -f "/sys/class/net/${iface}/operstate" ]]; then
    oper_state="$(<"/sys/class/net/${iface}/operstate")"
  fi
  if command_exists ip; then
    ip_addrs="$(ip -o -4 addr show dev "$iface" 2>/dev/null | awk '{print $4}' | paste -sd ',' -)"
  fi

  MAC_COUNT=$((MAC_COUNT + 1))
  printf "%-12s MAC=%-17s state=%-8s IPv4=%s\n" "$iface" "$mac_addr" "$oper_state" "${ip_addrs:-none}"
done < <(
  if [[ "$interface_source" == "ip" ]]; then
    ip -o link show | awk -F': ' '{print $2}' | cut -d'@' -f1
  else
    ls -1 /sys/class/net
  fi
)
echo

CHECKS_PASSED=$((CHECKS_TOTAL - CHECKS_FAILED))
echo "=== Summary ==="
echo "Checks passed: ${CHECKS_PASSED}/${CHECKS_TOTAL}"
echo "Checks failed: ${CHECKS_FAILED}"
echo "Backup candidates found: ${BACKUP_MATCHES}"
echo "Interfaces enumerated: ${MAC_COUNT}"

INDEX_CSV="${REPORT_DIR}/connectivity-index.csv"
if [[ ! -f "$INDEX_CSV" ]]; then
  echo "timestamp_utc,hostname,checks_total,checks_passed,checks_failed,backup_candidates,interfaces_enumerated" > "$INDEX_CSV"
fi
echo "${TS_UTC},${HOSTNAME_VALUE},${CHECKS_TOTAL},${CHECKS_PASSED},${CHECKS_FAILED},${BACKUP_MATCHES},${MAC_COUNT}" >> "$INDEX_CSV"
echo "Index activity entry appended to ${INDEX_CSV}"

if [[ -n "$JSON_OUTPUT" ]]; then
  mkdir -p "$(dirname "$JSON_OUTPUT")"
  cat > "$JSON_OUTPUT" <<EOF
{
  "timestamp_utc": "${TS_UTC}",
  "hostname": "${HOSTNAME_VALUE}",
  "checks_total": ${CHECKS_TOTAL},
  "checks_passed": ${CHECKS_PASSED},
  "checks_failed": ${CHECKS_FAILED},
  "backup_candidates": ${BACKUP_MATCHES},
  "interfaces_enumerated": ${MAC_COUNT},
  "strict_mode": ${STRICT_MODE}
}
EOF
  echo "JSON report written: ${JSON_OUTPUT}"
fi

if [[ "$STRICT_MODE" -eq 1 && "$CHECKS_FAILED" -gt 0 ]]; then
  exit 1
fi
