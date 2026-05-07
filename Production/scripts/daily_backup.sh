#!/usr/bin/env bash
#
# daily_backup.sh — MindfulNest daily Directus backup
#
# Spec v2 §C15. Backs up Directus Postgres via pg_dump over Railway Postgres public endpoint.
# Retains 30 days of daily dumps locally. Weekly git snapshot is a separate job.
#
# Install: run `./install_backup_crons.sh` (sibling file) to register launchd jobs.
#
# Requires:
#   - pg_dump (Homebrew libpq: `brew install libpq && brew link --force libpq`)
#   - Doppler CLI (per LD-208) — or env vars DB_HOST/DB_USER/DB_PASSWORD/DB_NAME as fallback
#
# Kim's Directus on Railway — connection info from Production/API_KEYS_MASTER.md:
#   Host: db.ugjpauwozlruyctrygby.supabase.co (pooler: postgres.ugjpauwozlruyctrygby)
#   Port: 5432
#   Database: postgres
#   User: postgres.ugjpauwozlruyctrygby
#   Password: supapass11mn  <-- migrate to Doppler in WA-C14
#
# Output: ~/MindfulNestBackups/directus/YYYY-MM-DD.sql.gz
# Log:    ~/MindfulNestBackups/directus/backup.log (append-only)

set -euo pipefail

BACKUP_DIR="${HOME}/MindfulNestBackups/directus"
LOG_FILE="${BACKUP_DIR}/backup.log"
RETENTION_DAYS=30

mkdir -p "${BACKUP_DIR}"

TIMESTAMP="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
DATE_STAMP="$(date -u +'%Y-%m-%d')"
OUT_FILE="${BACKUP_DIR}/${DATE_STAMP}.sql.gz"

log() {
  echo "[${TIMESTAMP}] $*" | tee -a "${LOG_FILE}"
}

# Load credentials
# Prefer Doppler (LD-208); fall back to env vars; never hardcode
if command -v doppler >/dev/null 2>&1 && [ -n "${DOPPLER_PROJECT:-}" ]; then
  export $(doppler secrets download --no-file --format env --project "${DOPPLER_PROJECT}" | xargs)
fi

: "${SUPABASE_DB_HOST:?SUPABASE_DB_HOST not set (Doppler or env)}"
: "${SUPABASE_DB_USER:?SUPABASE_DB_USER not set}"
: "${SUPABASE_DB_PASSWORD:?SUPABASE_DB_PASSWORD not set}"
: "${SUPABASE_DB_NAME:=postgres}"
: "${SUPABASE_DB_PORT:=5432}"

log "Starting pg_dump → ${OUT_FILE}"

# Use --no-owner --no-acl for portability across environments
PGPASSWORD="${SUPABASE_DB_PASSWORD}" pg_dump \
    -h "${SUPABASE_DB_HOST}" \
    -p "${SUPABASE_DB_PORT}" \
    -U "${SUPABASE_DB_USER}" \
    -d "${SUPABASE_DB_NAME}" \
    --no-owner \
    --no-acl \
    --format=plain \
    2> "${BACKUP_DIR}/last_dump_stderr.log" | gzip > "${OUT_FILE}.tmp"

# Atomic rename (no partial files on error)
mv "${OUT_FILE}.tmp" "${OUT_FILE}"

SIZE="$(du -h "${OUT_FILE}" | awk '{print $1}')"
log "pg_dump complete: ${SIZE}"

# Prune old backups
find "${BACKUP_DIR}" -name '*.sql.gz' -mtime +${RETENTION_DAYS} -print -delete >> "${LOG_FILE}" 2>&1

log "Retention pruning complete (retained ${RETENTION_DAYS} days)"
log "SUCCESS"
