#!/usr/bin/env bash
# recup-setup.sh — TestDisk/PhotoRec recup data import and organization.
#
# Scans recup_dir.* output directories (from PhotoRec) and sorts recovered
# files into /home/troy/TEMPLATES (code, documents, configs) and
# /home/troy/PHOTOS (images), with a manifest for the site to display.
set -euo pipefail

RECUP_HOME="${RECUP_HOME:-/home/troy}"
TEMPLATES_DIR="${RECUP_HOME}/TEMPLATES"
PHOTOS_DIR="${RECUP_HOME}/PHOTOS"
RECUP_INPUT="${RECUP_HOME}/recup_output"
MANIFEST="${RECUP_HOME}/recup_manifest.json"

mkdir -p "$TEMPLATES_DIR"/{code,documents,configs,scripts,data} \
         "$PHOTOS_DIR"/{jpg,png,gif,svg,webp,other} \
         "$RECUP_INPUT"

echo "[recup-setup] Origin server: ${HUM_ORIGIN:-hum.org}"
echo "[recup-setup] RECUP_HOME:    $RECUP_HOME"
echo "[recup-setup] Scanning:      $RECUP_INPUT"

# Image extensions → PHOTOS
IMAGE_EXTS="jpg|jpeg|png|gif|bmp|tiff|tif|svg|webp|ico|heic|heif|raw|cr2|nef|arw"

# Code / template extensions → TEMPLATES/code
CODE_EXTS="py|js|ts|jsx|tsx|php|rb|go|rs|c|cpp|h|hpp|java|cs|sh|bash|zsh|pl|lua|r|swift|kt"

# Config extensions → TEMPLATES/configs
CONFIG_EXTS="json|yaml|yml|toml|ini|cfg|conf|env|xml|properties"

# Document extensions → TEMPLATES/documents
DOC_EXTS="html|htm|xhtml|css|scss|less|md|rst|txt|tex|csv|sql|log"

# Script extensions → TEMPLATES/scripts
SCRIPT_EXTS="sh|bash|zsh|ps1|bat|cmd|makefile|dockerfile"

# Data extensions → TEMPLATES/data
DATA_EXTS="db|sqlite|sqlite3|sql|csv|tsv|parquet|avro|json|jsonl|ndjson|xml"

TOTAL=0
PHOTOS_COUNT=0
TEMPLATES_COUNT=0
SKIPPED=0

classify_file() {
    local file="$1"
    local basename
    basename="$(basename "$file")"
    local ext="${basename##*.}"
    ext="$(echo "$ext" | tr '[:upper:]' '[:lower:]')"

    if [[ "$basename" == "$ext" ]]; then
        ext=""
    fi

    local mime
    mime="$(file --brief --mime-type "$file" 2>/dev/null || echo "application/octet-stream")"

    # --- Images ---
    if [[ "$mime" == image/* ]] || echo "$ext" | grep -qiE "^($IMAGE_EXTS)$"; then
        local photo_subdir="other"
        case "$ext" in
            jpg|jpeg) photo_subdir="jpg" ;;
            png)      photo_subdir="png" ;;
            gif)      photo_subdir="gif" ;;
            svg)      photo_subdir="svg" ;;
            webp)     photo_subdir="webp" ;;
        esac
        cp -n "$file" "$PHOTOS_DIR/$photo_subdir/" 2>/dev/null && echo "PHOTO" && return
        echo "SKIP"
        return
    fi

    # --- Code ---
    if echo "$ext" | grep -qiE "^($CODE_EXTS)$"; then
        cp -n "$file" "$TEMPLATES_DIR/code/" 2>/dev/null && echo "CODE" && return
        echo "SKIP"
        return
    fi

    # --- Configs ---
    if echo "$ext" | grep -qiE "^($CONFIG_EXTS)$"; then
        cp -n "$file" "$TEMPLATES_DIR/configs/" 2>/dev/null && echo "CONFIG" && return
        echo "SKIP"
        return
    fi

    # --- Documents ---
    if echo "$ext" | grep -qiE "^($DOC_EXTS)$"; then
        cp -n "$file" "$TEMPLATES_DIR/documents/" 2>/dev/null && echo "DOC" && return
        echo "SKIP"
        return
    fi

    # --- Scripts (overlap with code, but Makefile/Dockerfile without ext) ---
    local lower_base
    lower_base="$(echo "$basename" | tr '[:upper:]' '[:lower:]')"
    if echo "$ext" | grep -qiE "^($SCRIPT_EXTS)$" || \
       [[ "$lower_base" == "makefile" || "$lower_base" == "dockerfile" || "$lower_base" == "vagrantfile" ]]; then
        cp -n "$file" "$TEMPLATES_DIR/scripts/" 2>/dev/null && echo "SCRIPT" && return
        echo "SKIP"
        return
    fi

    # --- Data files ---
    if echo "$ext" | grep -qiE "^($DATA_EXTS)$"; then
        cp -n "$file" "$TEMPLATES_DIR/data/" 2>/dev/null && echo "DATA" && return
        echo "SKIP"
        return
    fi

    # --- Text-like by mime → documents ---
    if [[ "$mime" == text/* ]]; then
        cp -n "$file" "$TEMPLATES_DIR/documents/" 2>/dev/null && echo "DOC" && return
        echo "SKIP"
        return
    fi

    echo "UNCLASSIFIED"
}

# Build the manifest as a JSON array
echo "[" > "$MANIFEST"
FIRST=true

# Walk all entries in RECUP_INPUT (recup_dir.* dirs and loose files)
shopt -s nullglob
SEEN_ENTRIES=()
for entry in "$RECUP_INPUT"/recup_dir.* "$RECUP_INPUT"/*; do
    # Deduplicate overlapping globs
    real_entry="$(realpath "$entry")"
    skip=false
    for seen in "${SEEN_ENTRIES[@]+"${SEEN_ENTRIES[@]}"}"; do
        if [[ "$seen" == "$real_entry" ]]; then skip=true; break; fi
    done
    if $skip; then continue; fi
    SEEN_ENTRIES+=("$real_entry")
    if [[ -d "$entry" ]]; then
        for file in "$entry"/*; do
            [[ -f "$file" ]] || continue
            TOTAL=$((TOTAL + 1))
            result="$(classify_file "$file")"
            case "$result" in
                PHOTO)          PHOTOS_COUNT=$((PHOTOS_COUNT + 1)) ;;
                CODE|CONFIG|DOC|SCRIPT|DATA) TEMPLATES_COUNT=$((TEMPLATES_COUNT + 1)) ;;
                SKIP)           SKIPPED=$((SKIPPED + 1)) ;;
                UNCLASSIFIED)   SKIPPED=$((SKIPPED + 1)) ;;
            esac
            bname="$(basename "$file")"
            src_dir="$(basename "$(dirname "$file")")"
            if [ "$FIRST" = true ]; then FIRST=false; else echo "," >> "$MANIFEST"; fi
            printf '  {"file":"%s","source":"%s","class":"%s"}' \
                "$bname" "$src_dir" "$result" >> "$MANIFEST"
        done
    elif [[ -f "$entry" ]]; then
        TOTAL=$((TOTAL + 1))
        result="$(classify_file "$entry")"
        case "$result" in
            PHOTO)          PHOTOS_COUNT=$((PHOTOS_COUNT + 1)) ;;
            CODE|CONFIG|DOC|SCRIPT|DATA) TEMPLATES_COUNT=$((TEMPLATES_COUNT + 1)) ;;
            SKIP)           SKIPPED=$((SKIPPED + 1)) ;;
            UNCLASSIFIED)   SKIPPED=$((SKIPPED + 1)) ;;
        esac
        bname="$(basename "$entry")"
        if [ "$FIRST" = true ]; then FIRST=false; else echo "," >> "$MANIFEST"; fi
        printf '  {"file":"%s","source":"root","class":"%s"}' \
            "$bname" "$result" >> "$MANIFEST"
    fi
done

echo "" >> "$MANIFEST"
echo "]" >> "$MANIFEST"

echo ""
echo "[recup-setup] Complete."
echo "  Total scanned:  $TOTAL"
echo "  → PHOTOS:       $PHOTOS_COUNT"
echo "  → TEMPLATES:    $TEMPLATES_COUNT"
echo "  → Skipped:      $SKIPPED"
echo "  Manifest:       $MANIFEST"

# Summary file for the site to read
cat > "${RECUP_HOME}/recup_summary.json" <<EOF
{
  "origin": "${HUM_ORIGIN:-hum.org}",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "recup_home": "$RECUP_HOME",
  "total_scanned": $TOTAL,
  "photos_imported": $PHOTOS_COUNT,
  "templates_imported": $TEMPLATES_COUNT,
  "skipped": $SKIPPED,
  "directories": {
    "templates": "$TEMPLATES_DIR",
    "photos": "$PHOTOS_DIR",
    "recup_input": "$RECUP_INPUT"
  }
}
EOF

echo "  Summary:        ${RECUP_HOME}/recup_summary.json"
