#!/usr/bin/env bash
# Deprecated wrapper — runs the full automated fix.
exec "$(dirname "$0")/fix_playwright_and_verify_browser.sh" "$@"
