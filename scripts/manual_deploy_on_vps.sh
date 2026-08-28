#!/usr/bin/env bash
# Run ON THE VPS after SSH login: bash scripts/manual_deploy_on_vps.sh
set -euo pipefail
cd /root/docmaxxing
git fetch origin main
git reset --hard origin/main
source venv/bin/activate
pip install -r requirements.txt
python -c "import playwright"
playwright install chromium
mkdir -p /root/docmaxxing/data/projects /root/docmaxxing/data/project_engine
mkdir -p /root/docmaxxing/data/tmp/format_v2_documents
chmod 700 /root/docmaxxing/data/tmp/format_v2_documents
touch /root/docmaxxing/data/assignment-trace.log
install -m 644 deploy/docmaxxing.service /etc/systemd/system/docmaxxing.service
bash scripts/install_backup_timers.sh
systemctl daemon-reload
systemctl enable docmaxxing
systemctl restart docmaxxing
# Wait until gunicorn actually accepts connections (restart can race).
for i in $(seq 1 30); do
  if curl -sf --max-time 2 http://127.0.0.1:8000/api/version >/dev/null; then
    break
  fi
  sleep 1
done
if ! systemctl is-active --quiet docmaxxing; then
  echo "ERROR: docmaxxing service is not active" >&2
  systemctl status docmaxxing --no-pager || true
  journalctl -u docmaxxing -n 40 --no-pager || true
  exit 1
fi
if ! curl -sf --max-time 5 http://127.0.0.1:8000/api/version; then
  echo
  echo "ERROR: gunicorn not listening on 127.0.0.1:8000" >&2
  systemctl status docmaxxing --no-pager || true
  journalctl -u docmaxxing -n 40 --no-pager || true
  ss -lntp | grep -E ':8000\b' || true
  exit 1
fi
echo
bash scripts/patch_nginx_timeouts.sh || true
echo "OK — running $(git rev-parse --short HEAD)"
# Quick webhook smoke (should return JSON ok/ignored, not hang).
curl -sS --max-time 10 -X POST http://127.0.0.1:8000/api/telegram-webhook \
  -H 'Content-Type: application/json' \
  -d '{"message":{"text":"deploy-ping"}}' || true
echo
