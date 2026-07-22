#!/usr/bin/env bash
# Full Playwright diagnosis + fix for the docmaxxing systemd service.
# Run ON THE VPS (or via scripts/run_vps_playwright_fix.sh from your Mac).
#
#   bash scripts/fix_playwright_and_verify_browser.sh
set -euo pipefail

API_BASE="${DOCMAXXING_API:-http://127.0.0.1:8000}"
SERVICE_NAME="${DOCMAXXING_SERVICE:-docmaxxing}"

# Report flags
OK_SERVICE_PYTHON=false
OK_PLAYWRIGHT=false
OK_CHROMIUM=false
OK_BROWSER_STARTS=false
OK_BROWSER_SERVICE=false
OK_STEALTHWRITER_PROVIDER=false
OK_SESSION_RESTORED=false
OK_HUMANIZER_ACCESSIBLE=false
OK_HUMANIZATION_COMPLETED=false
OK_OUTPUT_RECEIVED=false
OK_STEALTHWRITER_OPERATIONAL=false
OK_PRODUCTION_READY=false

SERVICE_PYTHON=""
SERVICE_PIP=""
SERVICE_PW=""
WORK_DIR=""
FAIL_REASON=""

red() { printf '\033[0;31m%s\033[0m\n' "$*"; }
green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[0;33m%s\033[0m\n' "$*"; }
info() { printf '→ %s\n' "$*"; }

abort() {
  FAIL_REASON="$1"
  red "STOPPED: $FAIL_REASON"
  print_report
  exit 1
}

print_report() {
  echo ""
  echo "================================================================"
  echo "FINAL REPORT"
  echo "================================================================"
  if [[ "$OK_SERVICE_PYTHON" == true ]]; then green "✓ Service Python: $SERVICE_PYTHON"; else red "✗ Service Python"; fi
  if [[ "$OK_PLAYWRIGHT" == true ]]; then green "✓ Playwright installed"; else red "✗ Playwright installed"; fi
  if [[ "$OK_CHROMIUM" == true ]]; then green "✓ Chromium installed"; else red "✗ Chromium installed"; fi
  if [[ "$OK_BROWSER_STARTS" == true ]]; then green "✓ Browser starts"; else red "✗ Browser starts"; fi
  if [[ "$OK_BROWSER_SERVICE" == true ]]; then green "✓ BrowserService initialized"; else red "✗ BrowserService initialized"; fi
  if [[ "$OK_STEALTHWRITER_PROVIDER" == true ]]; then green "✓ StealthWriter provider loaded"; else red "✗ StealthWriter provider loaded"; fi
  if [[ "$OK_SESSION_RESTORED" == true ]]; then green "✓ StealthWriter session restored"; else red "✗ StealthWriter session restored"; fi
  if [[ "$OK_HUMANIZER_ACCESSIBLE" == true ]]; then green "✓ Humanizer page accessible"; else red "✗ Humanizer page accessible"; fi
  if [[ "$OK_HUMANIZATION_COMPLETED" == true ]]; then green "✓ Humanization request completed"; else red "✗ Humanization request completed"; fi
  if [[ "$OK_OUTPUT_RECEIVED" == true ]]; then green "✓ Output received"; else red "✗ Output received"; fi
  if [[ "$OK_STEALTHWRITER_OPERATIONAL" == true ]]; then green "✓ StealthWriter fully operational"; else red "✗ StealthWriter fully operational"; fi
  if [[ "$OK_PRODUCTION_READY" == true ]]; then green "✓ Ready for production"; else red "✗ Ready for production"; fi
  if [[ -n "$FAIL_REASON" ]]; then
    echo ""
    red "Failure reason: $FAIL_REASON"
  fi
}

resolve_service_python() {
  info "Detecting Python interpreter from systemd ($SERVICE_NAME)…"
  if ! systemctl cat "$SERVICE_NAME" >/dev/null 2>&1; then
    abort "systemd unit '$SERVICE_NAME' not found"
  fi

  local exec_start work_dir gunicorn_bin
  exec_start="$(systemctl show "$SERVICE_NAME" -p ExecStart --value 2>/dev/null || true)"
  work_dir="$(systemctl show "$SERVICE_NAME" -p WorkingDirectory --value 2>/dev/null || true)"
  WORK_DIR="${work_dir:-/root/docmaxxing}"

  gunicorn_bin=""
  if [[ "$exec_start" =~ argv\[\]=([^ ;]+) ]]; then
    gunicorn_bin="${BASH_REMATCH[1]}"
  elif [[ "$exec_start" =~ path=([^ ;]+) ]]; then
    gunicorn_bin="${BASH_REMATCH[1]}"
  fi
  if [[ -z "$gunicorn_bin" || ! -x "$gunicorn_bin" ]]; then
    gunicorn_bin="$WORK_DIR/venv/bin/gunicorn"
  fi
  if [[ ! -x "$gunicorn_bin" ]]; then
    abort "Could not resolve gunicorn from ExecStart (tried $gunicorn_bin)"
  fi

  SERVICE_PYTHON="$(dirname "$gunicorn_bin")/python"
  if [[ ! -x "$SERVICE_PYTHON" ]]; then
    SERVICE_PYTHON="$(dirname "$gunicorn_bin")/python3"
  fi
  if [[ ! -x "$SERVICE_PYTHON" ]]; then
    abort "Service virtualenv Python not found next to $gunicorn_bin"
  fi

  SERVICE_PIP="$(dirname "$SERVICE_PYTHON")/pip"
  SERVICE_PW="$(dirname "$SERVICE_PYTHON")/playwright"
  OK_SERVICE_PYTHON=true
  info "Service Python: $SERVICE_PYTHON"
  info "WorkingDirectory: $WORK_DIR"
}

playwright_import_ok() {
  "$SERVICE_PYTHON" -c "import playwright" >/dev/null 2>&1
}

ensure_playwright() {
  info "Checking Playwright in service virtualenv…"
  if playwright_import_ok; then
    OK_PLAYWRIGHT=true
    info "Playwright already importable"
    return
  fi

  info "Playwright missing — installing into $SERVICE_PYTHON …"
  if [[ -x "$SERVICE_PIP" ]]; then
    "$SERVICE_PIP" install "playwright>=1.49.0"
  else
    "$SERVICE_PYTHON" -m pip install "playwright>=1.49.0"
  fi

  if ! playwright_import_ok; then
    abort "Playwright install completed but 'import playwright' still fails in $SERVICE_PYTHON"
  fi
  OK_PLAYWRIGHT=true
  info "Playwright import verified"
}

chromium_launch_ok() {
  "$SERVICE_PYTHON" -c "
from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
try:
    browser = pw.chromium.launch(headless=True)
    browser.close()
finally:
    pw.stop()
" >/dev/null 2>&1
}

ensure_chromium() {
  info "Checking Chromium for service Playwright…"
  if chromium_launch_ok; then
    OK_CHROMIUM=true
    info "Chromium launch OK"
    return
  fi

  info "Chromium missing or broken — running playwright install chromium…"
  if [[ -x "$SERVICE_PW" ]]; then
    "$SERVICE_PW" install chromium
  else
    "$SERVICE_PYTHON" -m playwright install chromium
  fi

  if ! chromium_launch_ok; then
    abort "Chromium install finished but headless launch still fails in $SERVICE_PYTHON"
  fi
  OK_CHROMIUM=true
  info "Chromium launch verified"
}

restart_service() {
  info "Restarting $SERVICE_NAME …"
  systemctl restart "$SERVICE_NAME"
  sleep 4
  if ! systemctl is-active --quiet "$SERVICE_NAME"; then
    local status
    status="$(systemctl status "$SERVICE_NAME" --no-pager -l 2>&1 | tail -20 || true)"
    abort "Service failed to start after restart:\n$status"
  fi
  info "Service is active"
}

api_check() {
  local url="$1"
  local timeout="${2:-120}"
  "$SERVICE_PYTHON" - "$url" "$timeout" <<'PY'
import json, sys, urllib.error, urllib.request
url, timeout = sys.argv[1], float(sys.argv[2])
try:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
except urllib.error.HTTPError as exc:
    body = exc.read().decode("utf-8", errors="replace")
    try:
        data = json.loads(body) if body.strip() else {}
    except json.JSONDecodeError:
        data = {"error": body[:1000], "http_status": exc.code}
    print(json.dumps(data))
    sys.exit(1)
except Exception as exc:
    print(json.dumps({"error": str(exc)}))
    sys.exit(1)
try:
    data = json.loads(body) if body.strip() else {}
except json.JSONDecodeError as exc:
    print(json.dumps({"error": f"Non-JSON response: {body[:500]}", "parse_error": str(exc)}))
    sys.exit(1)
print(json.dumps(data))
PY
}

json_field() {
  local json="$1"
  local expr="$2"
  echo "$json" | "$SERVICE_PYTHON" -c "import json,sys; d=json.load(sys.stdin); print($expr)"
}

verify_browser_stack() {
  info "Step 1/3 — Starting BrowserService via $API_BASE/api/browser/connect …"
  local connect_json
  if ! connect_json="$(api_check "$API_BASE/api/browser/connect" 120)"; then
    abort "BrowserService connect failed: $connect_json"
  fi

  local success connected
  success="$(json_field "$connect_json" "'true' if d.get('success') else 'false'")"
  connected="$(json_field "$connect_json" "'true' if d.get('connected') else 'false'")"

  if [[ "$success" != "true" || "$connected" != "true" ]]; then
    abort "BrowserService connect returned unexpected payload: $connect_json"
  fi
  OK_BROWSER_STARTS=true
  OK_BROWSER_SERVICE=true
  info "BrowserService connected"

  info "Verifying browser health snapshot…"
  local health_json
  if ! health_json="$(api_check "$API_BASE/api/browser/health" 30)"; then
    abort "Browser health check failed: $health_json"
  fi
  local browser_running
  browser_running="$(json_field "$health_json" "'true' if d.get('browser_running') or d.get('connected') else 'false'")"
  if [[ "$browser_running" != "true" ]]; then
    abort "Browser health indicates browser not running: $health_json"
  fi
  info "Browser health OK"
}

verify_stealthwriter_provider() {
  info "Step 2/3 — Loading StealthWriter provider via $API_BASE/api/browser/providers/stealthwriter/health …"
  local sw_json
  if ! sw_json="$(api_check "$API_BASE/api/browser/providers/stealthwriter/health" 120)"; then
    abort "StealthWriter provider health failed: $sw_json"
  fi

  local success err
  success="$(json_field "$sw_json" "'true' if d.get('success') else 'false'")"
  err="$(json_field "$sw_json" "d.get('error') or d.get('message') or ''")"

  if [[ "$success" != "true" ]]; then
    if echo "$sw_json" | grep -qi "No module named 'playwright'"; then
      abort "StealthWriter failed due to missing Playwright in the running worker: $sw_json"
    fi
    abort "StealthWriter provider did not load (success=false): ${err:-$sw_json}"
  fi

  OK_STEALTHWRITER_PROVIDER=true
  info "StealthWriter provider loaded"
}

verify_stealthwriter_production() {
  info "Step 3/3 — Real Humanize end-to-end via $API_BASE/api/browser/providers/stealthwriter/verify-production …"
  info "(submits sample text, clicks Humanize, waits for output — may take up to 2 minutes)"
  local verify_json
  if ! verify_json="$(api_check "$API_BASE/api/browser/providers/stealthwriter/verify-production" 200)"; then
    abort "StealthWriter production verify request failed: $verify_json"
  fi

  local current_url logged_in username session_present error_code success message
  local input_length output_length processing_time_ms
  current_url="$(json_field "$verify_json" "d.get('current_url') or ''")"
  logged_in="$(json_field "$verify_json" "'true' if d.get('logged_in') else 'false'")"
  username="$(json_field "$verify_json" "d.get('username') or ''")"
  session_present="$(json_field "$verify_json" "'true' if d.get('session_file_present') else 'false'")"
  error_code="$(json_field "$verify_json" "d.get('error') or ''")"
  success="$(json_field "$verify_json" "'true' if d.get('success') else 'false'")"
  message="$(json_field "$verify_json" "d.get('message') or ''")"
  input_length="$(json_field "$verify_json" "d.get('input_length') or 0")"
  output_length="$(json_field "$verify_json" "d.get('output_length') or 0")"
  processing_time_ms="$(json_field "$verify_json" "d.get('processing_time_ms') or 0")"

  echo ""
  yellow "StealthWriter session probe:"
  echo "  session_file_present: $session_present"
  echo "  current_url:          $current_url"
  echo "  logged_in:            $logged_in"
  if [[ -n "$username" ]]; then
    echo "  username:             $username"
  else
    echo "  username:             (not available)"
  fi

  if [[ "$error_code" == "LOGIN_REQUIRED" ]] || [[ "$logged_in" != "true" ]] || echo "$current_url" | grep -qi "sign-in"; then
    abort "LOGIN_REQUIRED — StealthWriter session is not restored. Upload browser_profiles/sessions/stealthwriter.json to the VPS."
  fi

  OK_SESSION_RESTORED=true

  echo ""
  yellow "Humanization probe:"
  echo "  input_length:         $input_length"
  echo "  output_length:        $output_length"
  echo "  processing_time_ms:   $processing_time_ms"
  echo "  success:              $success"

  if [[ "$success" != "true" ]]; then
    if [[ -n "$message" ]]; then
      echo "  message:              $message"
    fi
    abort "Humanization failed (${error_code:-HUMANIZE_FAILED}) — StealthWriter is not production-ready."
  fi

  if [[ "$output_length" -le 0 ]]; then
    abort "Humanization reported success but output_length is zero."
  fi

  if [[ "$input_length" -gt 0 && "$output_length" -eq "$input_length" ]]; then
    abort "Humanization output length equals input length — output may be unchanged."
  fi

  OK_HUMANIZER_ACCESSIBLE=true
  OK_HUMANIZATION_COMPLETED=true
  OK_OUTPUT_RECEIVED=true
  OK_STEALTHWRITER_OPERATIONAL=true
  OK_PRODUCTION_READY=true
  info "Real Humanize request completed successfully"
}

main() {
  echo "DocMaxxing Playwright fix + StealthWriter production verification"
  echo "================================================================"

  resolve_service_python
  ensure_playwright
  ensure_chromium
  restart_service
  verify_browser_stack
  verify_stealthwriter_provider
  verify_stealthwriter_production

  print_report
  green "StealthWriter passed a real Humanize request end-to-end."
}

main "$@"
