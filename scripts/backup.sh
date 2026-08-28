#!/usr/bin/env bash
# Daily / weekly encrypted backups of DocMaxxing data.
# Usage: backup.sh daily|weekly
set -euo pipefail

APP_ROOT="${APP_ROOT:-/root/docmaxxing}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/docmaxxing}"
MODE="${1:-}"

log() {
  echo "$(date -u +'%Y-%m-%dT%H:%M:%SZ') $*"
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
  [[ -n "${BACKUP_PASSPHRASE:-}" ]] || die "BACKUP_PASSPHRASE is not set (put it in $APP_ROOT/.env)"
}

sqlite_backup() {
  local src="$1"
  local dest="$2"
  [[ -f "$src" ]] || die "SQLite file missing: $src"
  command -v sqlite3 >/dev/null || die "sqlite3 is not installed"
  mkdir -p "$(dirname "$dest")"
  log "sqlite backup $src -> $dest"
  sqlite3 "$src" ".backup '$dest'"
  local check
  check="$(sqlite3 "$dest" 'PRAGMA integrity_check;')"
  if [[ "$check" != "ok" ]]; then
    die "integrity_check failed for $dest: $check"
  fi
  log "integrity_check ok: $dest"
}

copy_if_exists() {
  local src="$1"
  local dest="$2"
  if [[ -e "$src" ]]; then
    mkdir -p "$(dirname "$dest")"
    cp -a "$src" "$dest"
    log "copied $src"
  else
    log "skip missing $src"
  fi
}

prune_old() {
  local glob="$1"
  local keep_days="$2"
  log "pruning $glob older than ${keep_days}d in $BACKUP_ROOT"
  find "$BACKUP_ROOT" -maxdepth 1 -type f -name "$glob" -mtime "+$keep_days" -print -delete || true
}

# --- remote upload hook (not configured yet) --------------------------------
# TODO: send "$ARCHIVE" off-box once destination is decided.
# Example:
#   rclone copy "$ARCHIVE" remote:docmaxxing-backups/
upload_offsite() {
  local archive="$1"
  log "offsite upload skipped (not configured) archive=$archive"
}

[[ "$MODE" == "daily" || "$MODE" == "weekly" ]] || die "usage: $0 daily|weekly"

load_passphrase
command -v gpg >/dev/null || die "gpg is not installed"
command -v tar >/dev/null || die "tar is not installed"

mkdir -p "$BACKUP_ROOT"
chmod 700 "$BACKUP_ROOT"
umask 077

STAMP="$(date -u +'%Y-%m-%d')"
ARCHIVE_NAME="docmaxxing-${MODE}-${STAMP}.tar.gz.gpg"
WORKDIR="$(mktemp -d "${BACKUP_ROOT}/.work.${MODE}.XXXXXX")"
STAGE="$WORKDIR/docmaxxing"
ARCHIVE="$BACKUP_ROOT/$ARCHIVE_NAME"
TAR="$WORKDIR/bundle.tar.gz"

cleanup() {
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

mkdir -p "$STAGE"

log "backup start mode=$MODE app=$APP_ROOT dest=$BACKUP_ROOT"

# Daily (always)
sqlite_backup "$APP_ROOT/data/economy.db" "$STAGE/data/economy.db"
sqlite_backup "$APP_ROOT/data/turnitin/submissions.db" "$STAGE/data/turnitin/submissions.db"
mkdir -p "$STAGE/browser_profiles/sessions"
if [[ -d "$APP_ROOT/browser_profiles/sessions" ]]; then
  find "$APP_ROOT/browser_profiles/sessions" -maxdepth 1 -type f -name '*.json' -exec cp -a {} "$STAGE/browser_profiles/sessions/" \;
  log "copied browser_profiles/sessions/*.json"
else
  log "skip missing browser_profiles/sessions"
fi
copy_if_exists "$APP_ROOT/.env" "$STAGE/.env"

if [[ "$MODE" == "weekly" ]]; then
  copy_if_exists "$APP_ROOT/data/projects" "$STAGE/data/projects"
  copy_if_exists "$APP_ROOT/data/project_engine" "$STAGE/data/project_engine"
  copy_if_exists "$APP_ROOT/data/turnitin/uploads" "$STAGE/data/turnitin/uploads"
  copy_if_exists "$APP_ROOT/data/turnitin/reports" "$STAGE/data/turnitin/reports"
  copy_if_exists "$APP_ROOT/static/uploads/avatars" "$STAGE/static/uploads/avatars"
fi

log "creating tar"
tar -C "$WORKDIR" -czf "$TAR" docmaxxing

log "encrypting with gpg --symmetric"
printf '%s' "$BACKUP_PASSPHRASE" | gpg --batch --yes --passphrase-fd 0 \
  --pinentry-mode loopback --symmetric --cipher-algo AES256 \
  -o "$ARCHIVE" "$TAR"
chmod 600 "$ARCHIVE"
log "wrote $ARCHIVE ($(wc -c < "$ARCHIVE") bytes)"

if [[ "$MODE" == "daily" ]]; then
  prune_old "docmaxxing-daily-*.tar.gz.gpg" 14
else
  prune_old "docmaxxing-weekly-*.tar.gz.gpg" 56
fi

upload_offsite "$ARCHIVE"
log "backup done mode=$MODE"
