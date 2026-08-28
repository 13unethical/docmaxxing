#!/usr/bin/env bash
# Verify the newest db-only encrypted backup. Does not restore production data.
# Usage: restore_check.sh [path-to-db-archive.gpg]
set -euo pipefail

APP_ROOT="${APP_ROOT:-/root/docmaxxing}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/docmaxxing}"
LOG_FILE="${RESTORE_CHECK_LOG:-$BACKUP_ROOT/restore-check.log}"

log() {
  local line
  line="$(date -u +'%Y-%m-%dT%H:%M:%SZ') $*"
  echo "$line"
  if [[ -n "$LOG_FILE" ]]; then
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "$line" >>"$LOG_FILE"
  fi
}

die() {
  log "ERROR: $*"
  exit 1
}

load_passphrase() {
  if [[ -n "${BACKUP_PASSPHRASE:-}" ]]; then
    return 0
  fi
  local env_file="$APP_ROOT/.env"
  if [[ -f "$env_file" ]]; then
    BACKUP_PASSPHRASE="$(
      grep -E '^BACKUP_PASSPHRASE=' "$env_file" | tail -n 1 | cut -d= -f2- | sed -e 's/^["'\'']//' -e 's/["'\'']$//'
    )"
  fi
  [[ -n "${BACKUP_PASSPHRASE:-}" ]] || die "BACKUP_PASSPHRASE is not set"
}

pick_latest_db_archive() {
  ls -1t "$BACKUP_ROOT"/docmaxxing-*-db-*.tar.gz.gpg 2>/dev/null | head -n 1 || true
}

ARCHIVE="${1:-}"
if [[ -z "$ARCHIVE" ]]; then
  ARCHIVE="$(pick_latest_db_archive)"
fi
[[ -n "$ARCHIVE" && -f "$ARCHIVE" ]] || die "no db-only backup archive found in $BACKUP_ROOT"

load_passphrase
command -v gpg >/dev/null || die "gpg is not installed"
command -v sqlite3 >/dev/null || die "sqlite3 is not installed"

WORKDIR="$(mktemp -d "${BACKUP_ROOT}/.restore-check.XXXXXX")"
cleanup() {
  rm -rf "$WORKDIR"
}
trap cleanup EXIT
umask 077

log "restore_check start archive=$ARCHIVE"

printf '%s' "$BACKUP_PASSPHRASE" | gpg --batch --yes --passphrase-fd 0 \
  --pinentry-mode loopback -o "$WORKDIR/bundle.tar.gz" -d "$ARCHIVE"

tar -C "$WORKDIR" -xzf "$WORKDIR/bundle.tar.gz"

ROOT="$WORKDIR/docmaxxing-db"
if [[ ! -d "$ROOT" ]]; then
  ROOT="$WORKDIR/docmaxxing"
fi

ECO="$ROOT/data/economy.db"
TT="$ROOT/data/turnitin/submissions.db"
[[ -f "$ECO" ]] || die "economy.db missing in archive"
[[ -f "$TT" ]] || die "turnitin/submissions.db missing in archive"

eco_check="$(sqlite3 "$ECO" 'PRAGMA integrity_check;')"
tt_check="$(sqlite3 "$TT" 'PRAGMA integrity_check;')"
[[ "$eco_check" == "ok" ]] || die "economy.db integrity_check: $eco_check"
[[ "$tt_check" == "ok" ]] || die "submissions.db integrity_check: $tt_check"
log "integrity_check ok (economy + turnitin)"

wallet_rows="$(sqlite3 "$ECO" 'SELECT COUNT(*) FROM wallets;')"
[[ "${wallet_rows:-0}" -gt 0 ]] || die "wallets table is empty in backup"

users="$(sqlite3 "$ECO" 'SELECT COUNT(*) FROM users;')"
credits="$(sqlite3 "$ECO" 'SELECT COALESCE(SUM(balance), 0) FROM wallets;')"
log "users=$users wallets=$wallet_rows credits_sum=$credits"
log "restore_check passed (nothing was restored to $APP_ROOT)"
