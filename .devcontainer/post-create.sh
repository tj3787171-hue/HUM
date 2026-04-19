#!/usr/bin/env bash
set -euo pipefail

export HUM_ORIGIN="${HUM_ORIGIN:-hum.org}"
export RECUP_HOME="${RECUP_HOME:-/home/troy}"

echo "============================================"
echo "  HUM.org Dev Container Ready"
echo "  Origin:  $HUM_ORIGIN"
echo "============================================"
echo ""

echo "Network summary:"
ip -brief addr || true
echo
echo "Default route:"
ip route show default || true
echo

echo "--- Recup Data Import ---"
if command -v recup-setup &>/dev/null; then
    recup-setup
elif [ -f .devcontainer/recup-setup.sh ]; then
    bash .devcontainer/recup-setup.sh
else
    echo "  recup-setup not found; creating workspace directories."
    mkdir -p "$RECUP_HOME"/{TEMPLATES/{code,documents,configs,scripts,data},PHOTOS/{jpg,png,gif,svg,webp,other},recup_output}
fi

echo ""
echo "--- Net Driver Recovery (check mode) ---"
if command -v net-driver-recover-auto.sh &>/dev/null; then
    net-driver-recover-auto.sh check 2>&1 | head -40 || true
elif [ -f .devcontainer/net-driver-recover-auto.sh ]; then
    bash .devcontainer/net-driver-recover-auto.sh check 2>&1 | head -40 || true
else
    echo "  net-driver-recover-auto.sh not found; skipping."
fi

echo ""
echo "--- Workspace Layout ---"
echo "  TEMPLATES: $RECUP_HOME/TEMPLATES/"
ls -1d "$RECUP_HOME/TEMPLATES"/*/ 2>/dev/null | sed 's/^/    /' || echo "    (empty)"
echo "  PHOTOS:    $RECUP_HOME/PHOTOS/"
ls -1d "$RECUP_HOME/PHOTOS"/*/ 2>/dev/null | sed 's/^/    /' || echo "    (empty)"
echo ""
echo "Dev container setup complete."
