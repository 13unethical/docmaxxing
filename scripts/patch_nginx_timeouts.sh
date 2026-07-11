#!/usr/bin/env bash
# Patch nginx site config(s) that proxy to gunicorn so LLM stages do not 504 at 60s.
set -euo pipefail

TIMEOUT_BLOCK=$'        proxy_connect_timeout 300s;\n        proxy_send_timeout 300s;\n        proxy_read_timeout 300s;'

config_targets_gunicorn() {
  local f="$1"
  grep -qE 'proxy_pass|uwsgi_pass' "$f" || return 1
  grep -qE '(:8000|127\.0\.0\.1|localhost)' "$f" || return 1
  return 0
}

patch_file() {
  local f="$1"
  if grep -q 'proxy_read_timeout' "$f"; then
    echo "nginx already has proxy_read_timeout in $f"
    return 0
  fi
  if grep -q 'proxy_pass' "$f"; then
    sed -i '/proxy_pass/i\'"$TIMEOUT_BLOCK" "$f"
    echo "Patched proxy timeouts in $f"
    return 0
  fi
  if grep -q 'uwsgi_pass' "$f"; then
    sed -i '/uwsgi_pass/i\'"$TIMEOUT_BLOCK" "$f"
    echo "Patched uwsgi timeouts in $f"
    return 0
  fi
  return 1
}

patched=0
for f in /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*.conf; do
  [ -f "$f" ] || continue
  if config_targets_gunicorn "$f"; then
    if patch_file "$f"; then
      patched=1
    fi
  fi
done

if [ "$patched" -eq 0 ]; then
  echo "WARN: no nginx config for gunicorn :8000 was patched" >&2
  echo "Check manually: grep -r proxy_pass /etc/nginx/" >&2
  exit 0
fi

nginx -t
systemctl reload nginx
echo "nginx reloaded with 300s proxy timeouts"
