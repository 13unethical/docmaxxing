#!/usr/bin/env bash
# Patch nginx site config(s) that proxy to gunicorn so LLM stages do not 504 at 60s.
set -euo pipefail

TIMEOUT_DIRECTIVES=$'        proxy_connect_timeout 300s;\n        proxy_send_timeout 300s;\n        proxy_read_timeout 300s;'

patched=0
for f in /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*.conf; do
  [ -f "$f" ] || continue
  if ! grep -q '127.0.0.1:8000' "$f" 2>/dev/null; then
    continue
  fi
  if grep -q 'proxy_read_timeout' "$f"; then
    echo "nginx already has proxy_read_timeout in $f"
    patched=1
    continue
  fi
  if grep -q 'proxy_pass' "$f"; then
    sed -i '/proxy_pass/i\'"$TIMEOUT_DIRECTIVES" "$f"
    echo "Patched nginx timeouts in $f"
    patched=1
  fi
done

if [ "$patched" -eq 0 ]; then
  echo "WARN: no nginx config proxying to 127.0.0.1:8000 was patched" >&2
  exit 0
fi

nginx -t
systemctl reload nginx
echo "nginx reloaded with 300s proxy timeouts"
