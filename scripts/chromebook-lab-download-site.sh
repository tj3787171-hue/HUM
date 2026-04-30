#!/usr/bin/env bash
set -euo pipefail

LAB_DOWNLOAD_DIR="${LAB_DOWNLOAD_DIR:-./docs}"
LAB_DOWNLOAD_FILE="${LAB_DOWNLOAD_FILE:-download.html}"
LAB_BIND_HOST="${LAB_BIND_HOST:-0.0.0.0}"
LAB_PORT="${LAB_PORT:-8080}"

STRIPE_URL="${STRIPE_URL:-https://api.stripe.com/v1/charges}"
MAGMA_CHECK_URL="${MAGMA_CHECK_URL:-$STRIPE_URL}"
KALI_CHECK_URL="${KALI_CHECK_URL:-$STRIPE_URL}"
STRIPE_EXPECT_TEXT="${STRIPE_EXPECT_TEXT:-}"
CURL_TIMEOUT_SECONDS="${CURL_TIMEOUT_SECONDS:-8}"

usage() {
  cat <<'EOF'
Chromebook lab download-site helper + Stripe visibility checks.

Usage:
  bash scripts/chromebook-lab-download-site.sh <command>

Commands:
  all            Run Stripe visibility checks, then start download site server
  serve          Start static HTTP server for docs/download.html
  check-stripe   Validate Stripe reachability for MAGMA + KALI startup probes
  help           Show this help

Environment overrides:
  LAB_DOWNLOAD_DIR      Static site directory (default: ./docs)
  LAB_DOWNLOAD_FILE     Landing file to verify exists (default: download.html)
  LAB_BIND_HOST         Server bind host (default: 0.0.0.0)
  LAB_PORT              Server port (default: 8080)

  STRIPE_URL            Canonical Stripe endpoint (default: https://api.stripe.com/v1/charges)
  MAGMA_CHECK_URL       MAGMA startup Stripe probe URL (default: STRIPE_URL)
  KALI_CHECK_URL        KALI startup Stripe probe URL (default: STRIPE_URL)
  STRIPE_EXPECT_TEXT    Optional body text that must be present in each response
  CURL_TIMEOUT_SECONDS  curl connect/max timeout seconds (default: 8)

Examples:
  # Start lab download page on port 8088
  LAB_PORT=8088 bash scripts/chromebook-lab-download-site.sh serve

  # Check local lab startup probes instead of live Stripe
  STRIPE_EXPECT_TEXT="HUM Toolkit" \
  MAGMA_CHECK_URL="http://127.0.0.1:8088/download.html" \
  KALI_CHECK_URL="http://127.0.0.1:8088/download.html" \
  bash scripts/chromebook-lab-download-site.sh check-stripe
EOF
}

log() {
  printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

url_host() {
  python3 - "$1" <<'PY'
import sys
from urllib.parse import urlparse

parsed = urlparse(sys.argv[1])
print(parsed.hostname or "")
PY
}

dns_check() {
  local host="$1"
  [[ -n "$host" ]] || return 1
  if getent ahosts "$host" >/dev/null 2>&1; then
    return 0
  fi
  if command -v nslookup >/dev/null 2>&1 && nslookup "$host" >/dev/null 2>&1; then
    return 0
  fi
  if command -v host >/dev/null 2>&1 && host "$host" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

check_endpoint() {
  local label="$1"
  local url="$2"
  local host status body

  host="$(url_host "$url")"
  log "[$label] URL: $url"

  if dns_check "$host"; then
    log "[$label] DNS: PASS ($host)"
  else
    log "[$label] DNS: FAIL ($host)"
    return 1
  fi

  body="$(mktemp)"
  status="$(
    curl -sS -L \
      --connect-timeout "$CURL_TIMEOUT_SECONDS" \
      --max-time "$CURL_TIMEOUT_SECONDS" \
      -o "$body" \
      -w '%{http_code}' \
      "$url" || true
  )"

  case "$status" in
    2*|3*|401|403)
      log "[$label] HTTP: PASS (status $status)"
      ;;
    *)
      log "[$label] HTTP: FAIL (status ${status:-000})"
      rm -f "$body"
      return 1
      ;;
  esac

  if [[ -n "$STRIPE_EXPECT_TEXT" ]]; then
    if grep -Fq "$STRIPE_EXPECT_TEXT" "$body"; then
      log "[$label] CONTENT: PASS (found expected text)"
    else
      log "[$label] CONTENT: FAIL (missing expected text)"
      rm -f "$body"
      return 1
    fi
  fi

  rm -f "$body"
}

check_stripe() {
  need_cmd curl
  need_cmd python3

  log "Starting Stripe visibility checks for startup paths"
  log "Canonical Stripe URL: $STRIPE_URL"

  local failed=0
  check_endpoint "MAGMA startup" "$MAGMA_CHECK_URL" || failed=1
  check_endpoint "KALI startup" "$KALI_CHECK_URL" || failed=1

  if [[ "$failed" -eq 0 ]]; then
    log "Stripe visibility checks: PASS"
    return 0
  fi
  log "Stripe visibility checks: FAIL"
  return 1
}

serve_site() {
  need_cmd python3

  local site_dir landing
  site_dir="$(cd "$LAB_DOWNLOAD_DIR" && pwd)"
  landing="$site_dir/$LAB_DOWNLOAD_FILE"
  if [[ ! -f "$landing" ]]; then
    echo "Download landing file not found: $landing" >&2
    exit 1
  fi

  log "Serving Chromebook lab download site"
  log "Directory: $site_dir"
  log "Landing:   $LAB_DOWNLOAD_FILE"
  log "URL:       http://$LAB_BIND_HOST:$LAB_PORT/$LAB_DOWNLOAD_FILE"
  python3 -m http.server "$LAB_PORT" --bind "$LAB_BIND_HOST" --directory "$site_dir"
}

main() {
  case "${1:-help}" in
    all)
      check_stripe
      serve_site
      ;;
    serve)
      serve_site
      ;;
    check-stripe)
      check_stripe
      ;;
    help|-h|--help)
      usage
      ;;
    *)
      echo "Unknown command: ${1:-}" >&2
      usage
      exit 2
      ;;
  esac
}

main "$@"
