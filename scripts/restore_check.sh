#!/usr/bin/env bash
# Verify the newest db-only encrypted backup. Does not restore production data.
# Usage: restore_check.sh [path-to-db-archive.gpg]
set -euo pipefail

APP_ROOT="${APP_ROOT:-/root/docmaxxing}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/docmaxxing}"
LOG_FILE="${RESTORE_CHECK_LOG:-$BACKUP_ROOT/restore-check.log}"
WALLET_STATE_FILE="$BACKUP_ROOT/.last_wallet_count"
LOG_MAX_LINES=1000

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

trim_log() {
  [[ -f "$LOG_FILE" ]] || return 0
  local lines
  lines="$(wc -l <"$LOG_FILE" | tr -d '[:space:]')"
  if [[ "${lines:-0}" -gt "$LOG_MAX_LINES" ]]; then
    tail -n "$LOG_MAX_LINES" "$LOG_FILE" >"${LOG_FILE}.tmp"
    mv "${LOG_FILE}.tmp" "$LOG_FILE"
  fi
}

# Fallback when systemd EnvironmentFile did not set BACKUP_PASSPHRASE.
read_dotenv_value() {
  local key="$1"
  local file="$2"
  [[ -f "$file" ]] || return 1

  local line raw
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%$'\r'}"
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    [[ "$line" =~ ^[[:space:]]*${key}[[:space:]]*= ]] || continue

    raw="${line#*=}"
    raw="${raw#"${raw%%[![:space:]]*}"}"

    if [[ "$raw" == \"*\" && "$raw" == *\" ]]; then
      raw="${raw:1:${#raw}-2}"
      printf '%s' "$raw"
      return 0
    fi
    if [[ "$raw" == \'*\' && "$raw" == *\' ]]; then
      raw="${raw:1:${#raw}-2}"
      printf '%s' "$raw"
      return 0
    fi

    if [[ "$raw" =~ ^([^#]*[^[:space:]#])([[:space:]]+#.*)?$ ]]; then
      raw="${BASH_REMATCH[1]}"
    else
      raw="${raw%%#*}"
      raw="${raw%"${raw##*[![:space:]]}"}"
    fi
    printf '%s' "$raw"
    return 0
  done <"$file"
  return 1
}

load_passphrase() {
  if [[ -n "${BACKUP_PASSPHRASE:-}" ]]; then
    return 0
  fi
  local env_file="$APP_ROOT/.env"
  local from_file=""
  if from_file="$(read_dotenv_value BACKUP_PASSPHRASE "$env_file" 2>/dev/null)"; then
    BACKUP_PASSPHRASE="$from_file"
  fi
  [[ -n "${BACKUP_PASSPHRASE:-}" ]] || die "BACKUP_PASSPHRASE is not set (systemd EnvironmentFile or $env_file)"
}

pick_latest_db_archive() {
  ls -1t "$BACKUP_ROOT"/docmaxxing-*-db-*.tar.gz.gpg 2>/dev/null | head -n 1 || true
}

read_wallet_baseline() {
  local last=""
  if [[ -f "$WALLET_STATE_FILE" ]]; then
    last="$(tr -d '[:space:]' <"$WALLET_STATE_FILE")"
    [[ "$last" =~ ^[0-9]+$ ]] || last=""
  fi
  printf '%s' "$last"
}

save_wallet_baseline() {
  printf '%s\n' "$1" >"$WALLET_STATE_FILE"
}

check_wallet_rows() {
  local wallet_rows="$1"
  local last
  last="$(read_wallet_baseline)"

  if [[ "$wallet_rows" -eq 0 ]]; then
    if [[ -z "$last" || "$last" -eq 0 ]]; then
      log "WARN: wallets empty and no prior non-zero baseline; wallet count check skipped"
      save_wallet_baseline 0
      return 0
    fi
    die "wallets dropped from $last to 0"
  fi

  if [[ -n "$last" && "$last" -gt 0 ]]; then
    local min_ok=$((last * 80 / 100))
    if [[ "$wallet_rows" -lt "$min_ok" ]]; then
      die "wallet rows dropped from $last to $wallet_rows (more than 20% decrease)"
    fi
  fi

  save_wallet_baseline "$wallet_rows"
}

ARCHIVE="${1:-}"
if [[ -z "$ARCHIVE" ]]; then
  ARCHIVE="$(pick_latest_db_archive)"
fi
[[ -n "$ARCHIVE" && -f "$ARCHIVE" ]] || die "no db-only backup archive found in $BACKUP_ROOT"

trim_log
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
check_wallet_rows "${wallet_rows:-0}"

users="$(sqlite3 "$ECO" 'SELECT COUNT(*) FROM users;')"
credits="$(sqlite3 "$ECO" 'SELECT COALESCE(SUM(balance), 0) FROM wallets;')"
log "users=$users wallets=$wallet_rows credits_sum=$credits"
log "restore_check passed (nothing was restored to $APP_ROOT)"
