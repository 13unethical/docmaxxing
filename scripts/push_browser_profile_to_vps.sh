#!/usr/bin/env bash
# Run ON YOUR MAC (not on the VPS). Copies Chrome cookies/profile after StealthWriter login.
#
#   1. python3 scripts/bootstrap_stealthwriter_login.py   # log in once in Chrome
#   2. bash scripts/push_browser_profile_to_vps.sh root@YOUR_VPS_IP
#
set -euo pipefail

if [[ "$(uname -s)" == "Linux" ]] && [[ -d /root/docmaxxing ]] && [[ "$(pwd)" == /root/docmaxxing* ]]; then
  echo "ERROR: You are on the VPS. Open Terminal ON YOUR MAC and run this script there."
  echo "  cd ~/Desktop/academic-doc-formatter"
  echo "  bash scripts/push_browser_profile_to_vps.sh root@YOUR_VPS_IP"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="$ROOT/browser_profiles/chrome_user_data"
DEST="${1:-}"

if [[ -z "$DEST" ]]; then
  echo "Usage: bash scripts/push_browser_profile_to_vps.sh root@YOUR_VPS_IP"
  echo "Example: bash scripts/push_browser_profile_to_vps.sh root@123.45.67.89"
  exit 1
fi

if [[ ! -d "$PROFILE" ]]; then
  echo "ERROR: Profile not found: $PROFILE"
  echo "Run first: python3 scripts/bootstrap_stealthwriter_login.py"
  exit 1
fi

echo "Uploading Chrome profile from Mac → $DEST:~/docmaxxing/browser_profiles/chrome_user_data/"
rsync -avz --delete "$PROFILE/" "$DEST:~/docmaxxing/browser_profiles/chrome_user_data/"

echo ""
echo "Done. Now SSH to VPS and run:"
echo "  sudo systemctl restart docmaxxing"
echo "  sleep 3"
echo "  curl -sS http://127.0.0.1:8000/api/browser/providers/stealthwriter/status"
