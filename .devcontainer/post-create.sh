#!/usr/bin/env bash
set -euo pipefail

echo "Dev container ready (LAN profile)."
echo "Network interfaces:"
ip -brief addr || true
echo
echo "Default route:"
ip route show default || true
echo
echo "Listening ports (if any):"
ss -lntup || true
