#!/usr/bin/env bash
# Run ON THE VPS after uploading chrome_profile.tgz from Mac.
set -euo pipefail
cd "$(dirname "$0")/.."
PROFILE="${1:-browser_profiles/chrome_user_data}"

if [[ ! -d "$PROFILE" ]]; then
  echo "ERROR: Profile not found: $PROFILE"
  echo "Run: cd ~/docmaxxing && tar xzf chrome_profile.tgz"
  exit 1
fi

echo "Removing Chrome lock files copied from macOS…"
find "$PROFILE" -maxdepth 1 \( -name 'SingletonLock' -o -name 'SingletonSocket' -o -name 'SingletonCookie' \) -delete 2>/dev/null || true
find "$PROFILE" -name '.com.google.Chrome.*' -delete 2>/dev/null || true

echo "Restarting docmaxxing…"
systemctl restart docmaxxing
sleep 8

echo "Checking StealthWriter status (may take up to 90s on first start)…"
curl -sS --max-time 120 http://127.0.0.1:8000/api/browser/providers/stealthwriter/status || true
echo ""
