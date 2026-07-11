#!/usr/bin/env bash
# Run ON THE VPS after SSH login: bash scripts/manual_deploy_on_vps.sh
set -euo pipefail
cd /root/docmaxxing
git fetch origin main
git reset --hard origin/main
source venv/bin/activate
pip install -r requirements.txt
mkdir -p /root/docmaxxing/data/projects /root/docmaxxing/data/project_engine
touch /root/docmaxxing/data/assignment-trace.log
install -m 644 deploy/docmaxxing.service /etc/systemd/system/docmaxxing.service
systemctl daemon-reload
systemctl enable docmaxxing
systemctl restart docmaxxing
systemctl is-active --quiet docmaxxing
echo "OK — running $(git rev-parse --short HEAD)"
curl -sS http://127.0.0.1:8000/api/version || true
