#!/usr/bin/env bash
# Run ON THE VPS after SSH login: bash scripts/manual_deploy_on_vps.sh
set -euo pipefail
cd /root/docmaxxing
git fetch origin main
git reset --hard origin/main
source venv/bin/activate
pip install -r requirements.txt
UNIT=/etc/systemd/system/docmaxxing.service
if [ -f "$UNIT" ] && grep -q 'gunicorn ' "$UNIT" && ! grep -q 'gunicorn.conf.py' "$UNIT"; then
  sed -i 's|gunicorn |gunicorn --config /root/docmaxxing/gunicorn.conf.py |' "$UNIT"
  systemctl daemon-reload
fi
systemctl restart docmaxxing
systemctl is-active --quiet docmaxxing
echo "OK — running $(git rev-parse --short HEAD)"
curl -sS http://127.0.0.1:5001/api/version || true
