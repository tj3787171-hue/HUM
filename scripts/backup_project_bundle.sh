#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <backup-target-dir>" >&2
  echo "Example: $0 /mnt/chromeos/MyFiles/Backups" >&2
  exit 1
fi

TARGET_ROOT="$1"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="$TARGET_ROOT/hum-backups/hum-backup-$STAMP"

mkdir -p "$OUT_DIR"

echo "[backup] project root: $PROJECT_ROOT"
echo "[backup] output: $OUT_DIR"

tar \
  --exclude=".git" \
  --exclude="*.pyc" \
  --exclude="__pycache__" \
  -czf "$OUT_DIR/repo.tar.gz" \
  -C "$PROJECT_ROOT" .

if [[ -d "$PROJECT_ROOT/data" ]]; then
  cp -a "$PROJECT_ROOT/data" "$OUT_DIR/data"
fi

if command -v sqlite3 >/dev/null 2>&1; then
  for db in "$PROJECT_ROOT/data/project_evidence.db" "$PROJECT_ROOT/data/deepseek_backup.db"; do
    if [[ -f "$db" ]]; then
      sqlite3 "$db" ".backup '$OUT_DIR/$(basename "$db")'"
    fi
  done
fi

cat > "$OUT_DIR/MANIFEST.txt" <<EOF
timestamp_utc=$STAMP
project_root=$PROJECT_ROOT
archive=repo.tar.gz
optional_data_copy=$( [[ -d "$PROJECT_ROOT/data" ]] && echo yes || echo no )
sqlite_backup=$( [[ -f "$PROJECT_ROOT/data/project_evidence.db" || -f "$PROJECT_ROOT/data/deepseek_backup.db" ]] && echo yes || echo no )
sqlite_backup=$( [[ -f "$PROJECT_ROOT/data/project_records.db" ]] && echo yes || echo no )
EOF

echo "[backup] complete"
echo "[backup] files:"
ls -la "$OUT_DIR"
