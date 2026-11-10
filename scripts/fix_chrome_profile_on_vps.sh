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
# Admin-only POST: sign in with `python3 scripts/admin_api.py login --jar <jar>` and set DOCMAXXING_ADMIN_COOKIE_JAR.
if [[ -n "${DOCMAXXING_ADMIN_COOKIE_JAR:-}" ]]; then
  python3 scripts/admin_api.py call POST /api/browser/providers/stealthwriter/status \
    --jar "$DOCMAXXING_ADMIN_COOKIE_JAR" --timeout 120 || true
else
  echo "Skipped: set DOCMAXXING_ADMIN_COOKIE_JAR to an admin session cookie jar to check status."
fi
echo ""
