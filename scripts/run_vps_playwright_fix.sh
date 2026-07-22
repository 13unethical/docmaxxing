#!/usr/bin/env bash
# Run the full Playwright fix on the VPS over SSH (one command from your Mac).
#
#   bash scripts/run_vps_playwright_fix.sh root@76.13.248.62
set -euo pipefail

DEST="${1:-}"
if [[ -z "$DEST" ]]; then
  echo "Usage: bash scripts/run_vps_playwright_fix.sh root@YOUR_VPS_IP"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE_DIR="docmaxxing"

echo "Connecting to $DEST …"
echo "Uploading fix script and running full diagnosis on the VPS."
echo ""

# Copy script first so it works even before git pull on VPS.
scp "$ROOT/scripts/fix_playwright_and_verify_browser.sh" \
  "$DEST:~/$REMOTE_DIR/scripts/fix_playwright_and_verify_browser.sh"

ssh -t "$DEST" "bash -lc '
  set -euo pipefail
  cd ~/$REMOTE_DIR
  chmod +x scripts/fix_playwright_and_verify_browser.sh
  git fetch origin main 2>/dev/null || true
  git pull --ff-only 2>/dev/null || true
  bash scripts/fix_playwright_and_verify_browser.sh
'"
