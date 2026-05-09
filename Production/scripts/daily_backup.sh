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
# Kim's Directus on Supabase — connection info from Doppler (project=mindfulnest, config=dev):
#   Host: SUPABASE_DB_HOST          → db.ugjpauwozlruyctrygby.supabase.co (direct DB)
#   Port: SUPABASE_DB_PORT          → 5432
#   Database: SUPABASE_DB_NAME      → postgres
#   User: SUPABASE_DB_USER_DIRECT   → postgres   (direct-DB role; pooler-form
#                                                 SUPABASE_DB_USER is kept for
#                                                 other consumers per Option B)
#   Password: SUPABASE_DB_PASSWORD  → (rotated via doppler; never logged)
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

# Fail-loud (DS-6): on any error before successful exit, log Failed (exit=N)
# so backup.log unambiguously distinguishes a successful run (ends with SUCCESS)
# from a failed run (ends with Failed).
trap 'rc=$?; log "Failed (exit=${rc}) — see ${BACKUP_DIR}/last_dump_stderr.log"; exit ${rc}' ERR

# Load credentials
# Prefer Doppler (LD-208); fall back to env vars; never hardcode
if command -v doppler >/dev/null 2>&1 && [ -n "${DOPPLER_PROJECT:-}" ]; then
  export $(doppler secrets download --no-file --format env --project "${DOPPLER_PROJECT}" | xargs)
fi

: "${SUPABASE_DB_HOST:?SUPABASE_DB_HOST not set (Doppler or env)}"
: "${SUPABASE_DB_USER_DIRECT:?SUPABASE_DB_USER_DIRECT not set (Doppler or env). daily_backup uses the direct-DB role per Option B; pooler-form SUPABASE_DB_USER stays available for other consumers.}"
: "${SUPABASE_DB_PASSWORD:?SUPABASE_DB_PASSWORD not set}"
: "${SUPABASE_DB_NAME:=postgres}"
: "${SUPABASE_DB_PORT:=5432}"

log "Starting pg_dump → ${OUT_FILE}"

# Use --no-owner --no-acl for portability across environments
PGPASSWORD="${SUPABASE_DB_PASSWORD}" pg_dump \
    -h "${SUPABASE_DB_HOST}" \
    -p "${SUPABASE_DB_PORT}" \
    -U "${SUPABASE_DB_USER_DIRECT}" \
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
