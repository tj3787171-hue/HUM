#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

LAB_DOWNLOAD_DIR="${LAB_DOWNLOAD_DIR:-$REPO_ROOT/docs}"
LAB_DOWNLOAD_FILE="${LAB_DOWNLOAD_FILE:-download.html}"
LAB_BIND_HOST="${LAB_BIND_HOST:-0.0.0.0}"
LAB_PORT="${LAB_PORT:-8080}"

STRIPE_URL="${STRIPE_URL:-https://api.stripe.com/v1/charges}"
MAGMA_CHECK_URL="${MAGMA_CHECK_URL:-$STRIPE_URL}"
KALI_CHECK_URL="${KALI_CHECK_URL:-$STRIPE_URL}"
STRIPE_EXPECT_TEXT="${STRIPE_EXPECT_TEXT:-}"
CURL_TIMEOUT_SECONDS="${CURL_TIMEOUT_SECONDS:-8}"
HTTP_OK_PATTERN='^(2|3|4)[0-9][0-9]$'

log() {
  echo "[$(date '+%H:%M:%S')] $*"
}

usage() {
  cat <<'EOF'
Chromebook lab download-site helper + Stripe visibility checks.

Usage:
  bash scripts/chromebook-lab-download-site.sh <command>

Commands:
  all           Run Stripe visibility checks, then start download site server
  serve         Start static HTTP server for docs/download.html
  check-stripe  Validate Stripe reachability for MAGMA + KALI startup probes
  help          Show this help

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

  # Check startup visibility for custom endpoints
  MAGMA_CHECK_URL="http://10.0.0.10:9999/stripe" \
  KALI_CHECK_URL="http://10.0.0.11:9999/stripe" \
  bash scripts/chromebook-lab-download-site.sh check-stripe

  # Run checks first, then host the download page
  bash scripts/chromebook-lab-download-site.sh all
EOF
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
}

check_path_exists() {
  local path="$1"
  local label="$2"
  if [ ! -e "$path" ]; then
    echo "Missing ${label}: $path" >&2
    exit 1
  fi
}

extract_host() {
  local url="$1"
  # shellcheck disable=SC2001
  echo "$url" | sed -E 's#^[a-zA-Z]+://##' | cut -d'/' -f1 | cut -d':' -f1
}

dns_check() {
  local host="$1"
  [ -z "$host" ] && return 1
  if command -v getent >/dev/null 2>&1; then
    getent ahosts "$host" >/dev/null 2>&1
    return $?
  fi
  if command -v nslookup >/dev/null 2>&1; then
    nslookup "$host" >/dev/null 2>&1
    return $?
  fi
  if command -v host >/dev/null 2>&1; then
    host "$host" >/dev/null 2>&1
    return $?
  fi
  return 2
}

run_probe() {
  local label="$1"
  local url="$2"
  local tmp_body
  local http_code
  local host

  tmp_body="$(mktemp)"
  host="$(extract_host "$url")"

  log "[$label] URL: $url"
  if dns_check "$host"; then
    log "[$label] DNS: PASS ($host)"
  else
    log "[$label] DNS: WARN ($host unresolved with available tools)"
  fi

  http_code="$(curl \
    --silent \
    --show-error \
    --location \
    --connect-timeout "$CURL_TIMEOUT_SECONDS" \
    --max-time "$CURL_TIMEOUT_SECONDS" \
    --output "$tmp_body" \
    --write-out '%{http_code}' \
    "$url" 2>/dev/null || true)"

  if echo "$http_code" | grep -Eq "$HTTP_OK_PATTERN"; then
    log "[$label] HTTP: PASS (status $http_code)"
  else
    log "[$label] HTTP: FAIL (status ${http_code:-000})"
    rm -f "$tmp_body"
    return 1
  fi

  if [ -n "$STRIPE_EXPECT_TEXT" ]; then
    if grep -Fq "$STRIPE_EXPECT_TEXT" "$tmp_body"; then
      log "[$label] CONTENT: PASS (found expected text)"
    else
      log "[$label] CONTENT: FAIL (missing expected text)"
      rm -f "$tmp_body"
      return 1
    fi
  fi

  rm -f "$tmp_body"
}

check_stripe_visibility() {
  require_cmd curl
  local failed=0

  log "Starting Stripe visibility checks for startup paths"
  log "Canonical Stripe URL: $STRIPE_URL"

  run_probe "MAGMA startup" "$MAGMA_CHECK_URL" || failed=1
  run_probe "KALI startup" "$KALI_CHECK_URL" || failed=1

  if [ "$failed" -ne 0 ]; then
    log "Stripe visibility checks: FAIL"
    return 1
  fi
  log "Stripe visibility checks: PASS"
}

serve_download_site() {
  require_cmd python3
  check_path_exists "$LAB_DOWNLOAD_DIR" "download directory"
  check_path_exists "$LAB_DOWNLOAD_DIR/$LAB_DOWNLOAD_FILE" "download landing page"

  log "Serving download site from: $LAB_DOWNLOAD_DIR"
  log "Landing page: http://${LAB_BIND_HOST}:${LAB_PORT}/${LAB_DOWNLOAD_FILE}"
  log "Press Ctrl+C to stop"
  python3 -m http.server "$LAB_PORT" --bind "$LAB_BIND_HOST" --directory "$LAB_DOWNLOAD_DIR"
}

main() {
  local cmd="${1:-all}"
  case "$cmd" in
    all)
      check_stripe_visibility
      serve_download_site
      ;;
    serve)
      serve_download_site
      ;;
    check-stripe)
      check_stripe_visibility
      ;;
    help|-h|--help)
      usage
      ;;
    *)
      echo "Unknown command: $cmd" >&2
      usage >&2
      exit 1
      ;;
  esac
}

main "$@"
