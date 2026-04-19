#!/usr/bin/env bash
# SSH Key Manager for HUM Installer Agent
# Handles key generation, distribution, and fingerprint management.
set -euo pipefail

SSH_DIR="${HOME}/.ssh"
KEY_NAME="hum-installer-agent"
KNOWN_HOSTS="${SSH_DIR}/known_hosts"
AUTHORIZED_KEYS="${SSH_DIR}/authorized_keys"
LOG="/tmp/ssh-key-manager.log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }
err() { log "ERROR: $*" >&2; }

usage() {
  cat <<'EOF'
Usage: ssh-key-manager.sh <command> [args]

Commands:
  init                  Generate key pair and prepare SSH directory
  fingerprint           Show current key fingerprint
  accept <host> [port]  Accept and store host fingerprint
  distribute <host>     Copy public key to target host
  revoke <host>         Remove host from known_hosts
  list                  List known hosts
  audit                 Audit SSH configuration for security
  cleanup               Remove stale entries from known_hosts
EOF
}

cmd_init() {
  log "Initializing SSH key infrastructure"
  mkdir -p "$SSH_DIR"
  chmod 700 "$SSH_DIR"
  touch "$KNOWN_HOSTS" "$AUTHORIZED_KEYS"
  chmod 644 "$KNOWN_HOSTS"
  chmod 600 "$AUTHORIZED_KEYS"

  local key_path="${SSH_DIR}/${KEY_NAME}"
  if [ -f "$key_path" ]; then
    log "Key already exists: $key_path"
    log "Fingerprint: $(ssh-keygen -lf "${key_path}.pub")"
    return 0
  fi

  ssh-keygen -t ed25519 -f "$key_path" -N "" -C "${KEY_NAME}@$(hostname)-$(date +%Y%m%d)"
  chmod 600 "$key_path"
  chmod 644 "${key_path}.pub"
  log "Generated key: $key_path"
  log "Fingerprint: $(ssh-keygen -lf "${key_path}.pub")"
  log "Public key:"
  cat "${key_path}.pub" | tee -a "$LOG"
}

cmd_fingerprint() {
  local key_path="${SSH_DIR}/${KEY_NAME}"
  if [ ! -f "${key_path}.pub" ]; then
    err "No key found. Run: $0 init"
    return 1
  fi
  echo "=== Key Fingerprints ==="
  echo "ED25519:"
  ssh-keygen -lf "${key_path}.pub"
  echo ""
  echo "Visual:"
  ssh-keygen -lvf "${key_path}.pub"
}

cmd_accept() {
  local host="$1"
  local port="${2:-22}"
  log "Accepting fingerprint from $host:$port"

  ssh-keygen -R "$host" -f "$KNOWN_HOSTS" 2>/dev/null || true

  local keys
  keys="$(ssh-keyscan -p "$port" -T 10 "$host" 2>/dev/null)" || {
    err "Failed to scan $host:$port"
    return 1
  }

  if [ -z "$keys" ]; then
    err "No keys returned from $host:$port"
    return 1
  fi

  echo "$keys" >> "$KNOWN_HOSTS"
  log "Accepted $(echo "$keys" | wc -l) key(s) from $host"
  echo "$keys" | while read -r line; do
    log "  $line"
  done
}

cmd_distribute() {
  local host="$1"
  local user="${2:-root}"
  local key_path="${SSH_DIR}/${KEY_NAME}"

  if [ ! -f "${key_path}.pub" ]; then
    err "No key found. Run: $0 init"
    return 1
  fi

  log "Distributing public key to ${user}@${host}"
  ssh-copy-id -i "${key_path}.pub" -o StrictHostKeyChecking=accept-new "${user}@${host}" || {
    log "ssh-copy-id failed, trying manual method..."
    local pubkey
    pubkey="$(cat "${key_path}.pub")"
    ssh -o StrictHostKeyChecking=accept-new "${user}@${host}" \
      "mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '$pubkey' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
  }
  log "Key distributed to ${user}@${host}"
}

cmd_revoke() {
  local host="$1"
  log "Revoking fingerprint for $host"
  ssh-keygen -R "$host" -f "$KNOWN_HOSTS" 2>/dev/null || true
  log "Removed $host from known_hosts"
}

cmd_list() {
  echo "=== Known Hosts ==="
  if [ -f "$KNOWN_HOSTS" ]; then
    awk '{print NR": "$1" "$2}' "$KNOWN_HOSTS"
  else
    echo "(none)"
  fi
  echo ""
  echo "=== Installer Key ==="
  local key_path="${SSH_DIR}/${KEY_NAME}"
  if [ -f "${key_path}.pub" ]; then
    ssh-keygen -lf "${key_path}.pub"
  else
    echo "(not generated)"
  fi
}

cmd_audit() {
  echo "=== SSH Security Audit ==="
  echo ""

  echo "Key files:"
  local key_path="${SSH_DIR}/${KEY_NAME}"
  if [ -f "$key_path" ]; then
    local perms
    perms="$(stat -c '%a' "$key_path" 2>/dev/null || stat -f '%A' "$key_path" 2>/dev/null)"
    if [ "$perms" = "600" ]; then
      echo "  [OK] Private key permissions: $perms"
    else
      echo "  [WARN] Private key permissions: $perms (should be 600)"
    fi
  else
    echo "  [INFO] No private key found"
  fi

  echo ""
  echo "SSH directory:"
  local dir_perms
  dir_perms="$(stat -c '%a' "$SSH_DIR" 2>/dev/null || stat -f '%A' "$SSH_DIR" 2>/dev/null)"
  if [ "$dir_perms" = "700" ]; then
    echo "  [OK] .ssh permissions: $dir_perms"
  else
    echo "  [WARN] .ssh permissions: $dir_perms (should be 700)"
  fi

  echo ""
  echo "Known hosts:"
  if [ -f "$KNOWN_HOSTS" ]; then
    echo "  Entries: $(wc -l < "$KNOWN_HOSTS")"
    echo "  Unique hosts: $(awk '{print $1}' "$KNOWN_HOSTS" | sort -u | wc -l)"
  else
    echo "  (none)"
  fi
}

cmd_cleanup() {
  log "Cleaning up known_hosts"
  if [ ! -f "$KNOWN_HOSTS" ]; then
    log "No known_hosts file"
    return 0
  fi

  local before after
  before="$(wc -l < "$KNOWN_HOSTS")"
  sort -u "$KNOWN_HOSTS" -o "$KNOWN_HOSTS"
  after="$(wc -l < "$KNOWN_HOSTS")"
  log "Cleaned: $before entries -> $after unique entries"
}

main() {
  local cmd="${1:-help}"
  shift || true

  case "$cmd" in
    init)        cmd_init ;;
    fingerprint) cmd_fingerprint ;;
    accept)
      [ $# -ge 1 ] || { err "Usage: $0 accept <host> [port]"; exit 1; }
      cmd_accept "$1" "${2:-22}"
      ;;
    distribute)
      [ $# -ge 1 ] || { err "Usage: $0 distribute <host> [user]"; exit 1; }
      cmd_distribute "$1" "${2:-root}"
      ;;
    revoke)
      [ $# -ge 1 ] || { err "Usage: $0 revoke <host>"; exit 1; }
      cmd_revoke "$1"
      ;;
    list)    cmd_list ;;
    audit)   cmd_audit ;;
    cleanup) cmd_cleanup ;;
    -h|--help|help) usage ;;
    *)
      err "Unknown command: $cmd"
      usage
      exit 1
      ;;
  esac
}

main "$@"
