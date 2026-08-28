#!/usr/bin/env bash
# Daily / weekly encrypted backups of DocMaxxing data.
#
# Produces two archives per run:
#   docmaxxing-{daily|weekly}-db-{date}.tar.gz.gpg   — SQLite only (safe for offsite)
#   docmaxxing-{daily|weekly}-full-{date}.tar.gz.gpg — secrets + files (local only)
#
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

encrypt_archive() {
  local stage_root="$1"
  local archive="$2"
  local tar_path="$3"
  log "creating tar for $(basename "$archive")"
  tar -C "$(dirname "$stage_root")" -czf "$tar_path" "$(basename "$stage_root")"
  log "encrypting with gpg --symmetric"
  printf '%s' "$BACKUP_PASSPHRASE" | gpg --batch --yes --passphrase-fd 0 \
    --pinentry-mode loopback --symmetric --cipher-algo AES256 \
    -o "$archive" "$tar_path"
  chmod 600 "$archive"
  log "wrote $archive ($(wc -c < "$archive") bytes)"
}

# Only db-only archives may leave the VPS.
upload_offsite() {
  local archive="$1"
  local base
  base="$(basename "$archive")"
  if [[ "$base" != *"-db-"* ]]; then
    log "offsite upload skipped (not a db-only archive): $base"
    return 0
  fi
  # Example when configured:
  #   rclone copy "$archive" remote:docmaxxing-backups/
  log "offsite upload skipped (not configured) archive=$archive"
}

stage_db_files() {
  local stage="$1"
  mkdir -p "$stage/data/turnitin"
  sqlite_backup "$APP_ROOT/data/economy.db" "$stage/data/economy.db"
  sqlite_backup "$APP_ROOT/data/turnitin/submissions.db" "$stage/data/turnitin/submissions.db"
}

stage_full_files() {
  local stage="$1"
  mkdir -p "$stage/browser_profiles/sessions"
  if [[ -d "$APP_ROOT/browser_profiles/sessions" ]]; then
    find "$APP_ROOT/browser_profiles/sessions" -maxdepth 1 -type f -name '*.json' -exec cp -a {} "$stage/browser_profiles/sessions/" \;
    log "copied browser_profiles/sessions/*.json"
  else
    log "skip missing browser_profiles/sessions"
  fi
  copy_if_exists "$APP_ROOT/.env" "$stage/.env"

  if [[ "$MODE" == "weekly" ]]; then
    copy_if_exists "$APP_ROOT/data/projects" "$stage/data/projects"
    copy_if_exists "$APP_ROOT/data/project_engine" "$stage/data/project_engine"
    copy_if_exists "$APP_ROOT/data/turnitin/uploads" "$stage/data/turnitin/uploads"
    copy_if_exists "$APP_ROOT/data/turnitin/reports" "$stage/data/turnitin/reports"
    copy_if_exists "$APP_ROOT/static/uploads/avatars" "$stage/static/uploads/avatars"
  fi
}

[[ "$MODE" == "daily" || "$MODE" == "weekly" ]] || die "usage: $0 daily|weekly"

load_passphrase
command -v gpg >/dev/null || die "gpg is not installed"
command -v tar >/dev/null || die "tar is not installed"

mkdir -p "$BACKUP_ROOT"
chmod 700 "$BACKUP_ROOT"
umask 077

STAMP="$(date -u +'%Y-%m-%d')"
WORKDIR="$(mktemp -d "${BACKUP_ROOT}/.work.${MODE}.XXXXXX")"
DB_ARCHIVE="$BACKUP_ROOT/docmaxxing-${MODE}-db-${STAMP}.tar.gz.gpg"
FULL_ARCHIVE="$BACKUP_ROOT/docmaxxing-${MODE}-full-${STAMP}.tar.gz.gpg"

cleanup() {
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

log "backup start mode=$MODE app=$APP_ROOT dest=$BACKUP_ROOT"

DB_STAGE="$WORKDIR/docmaxxing-db"
FULL_STAGE="$WORKDIR/docmaxxing-full"
stage_db_files "$DB_STAGE"
encrypt_archive "$DB_STAGE" "$DB_ARCHIVE" "$WORKDIR/db-bundle.tar.gz"
upload_offsite "$DB_ARCHIVE"

stage_full_files "$FULL_STAGE"
encrypt_archive "$FULL_STAGE" "$FULL_ARCHIVE" "$WORKDIR/full-bundle.tar.gz"

if [[ "$MODE" == "daily" ]]; then
  prune_old "docmaxxing-daily-db-*.tar.gz.gpg" 14
  prune_old "docmaxxing-daily-full-*.tar.gz.gpg" 14
else
  prune_old "docmaxxing-weekly-db-*.tar.gz.gpg" 56
  prune_old "docmaxxing-weekly-full-*.tar.gz.gpg" 56
fi

log "backup done mode=$MODE db=$DB_ARCHIVE full=$FULL_ARCHIVE"
