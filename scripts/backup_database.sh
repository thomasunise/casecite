#!/bin/bash
# CaseCite backup — PostgreSQL dump + the application data volume.
#
# Run this on the HOST, from the directory that holds docker-compose.prod.yml
# (the backend image does not ship pg_dump or this script). Daily cron:
#   0 2 * * * cd /opt/casecite && ./scripts/backup_database.sh >> /var/log/casecite-backup.log 2>&1
#
# Produces, under BACKUP_DIR:
#   casecite_<timestamp>.sql.gz          PostgreSQL (users, matters, chats, analyses…)
#   rag_data_<timestamp>.tar.gz          /app/data volume: uploaded documents (encrypted
#                                        at rest), vector index, audit logs, BYOK key
#                                        store, sessions, instance secrets
# Both get a .enc suffix when BACKUP_ENCRYPTION_KEY is set. Restore the two from the
# same run: document records and their vectors drift out of sync otherwise.
#
# Modes (BACKUP_MODE, default "compose"):
#   compose  — bundled stack: pg_dump runs inside the postgres container over its
#              local socket (no password needed) and the data volume is read from
#              the backend container's /app/data mount. Needs docker + compose.
#   direct   — external/managed Postgres: pg_dump on PATH, POSTGRES_HOST/PORT/DB/
#              USER + PGPASSWORD set. The data volume is still archived if
#              DATA_VOLUME is set (docker volume name) or DATA_DIR (a host path).
#
# Environment variables:
#   COMPOSE_FILE_PATH        (default: docker-compose.prod.yml)
#   BACKUP_DIR               (default: ./backups)
#   BACKUP_RETENTION_DAYS    (default: 30)
#   BACKUP_ENCRYPTION_KEY    (optional; AES-256-CBC with PBKDF2 — keep it OUTSIDE the
#                             data volume, e.g. a password manager; without it the
#                             .enc files are unrecoverable)
#   S3_BUCKET / S3_ENDPOINT / S3_SSE   (optional upload; needs the aws CLI)
#   POSTGRES_USER            (default: casecite; must match the compose stack)
#   POSTGRES_DB              (default: casecite)
#   POSTGRES_HOST/PORT, PGPASSWORD      (direct mode only)
#   DATA_VOLUME / DATA_DIR   (direct mode only)

set -euo pipefail

BACKUP_MODE="${BACKUP_MODE:-compose}"
COMPOSE_FILE_PATH="${COMPOSE_FILE_PATH:-docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
POSTGRES_DB="${POSTGRES_DB:-casecite}"
POSTGRES_USER="${POSTGRES_USER:-casecite}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR" 2>/dev/null || true

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

compose() { docker compose -f "$COMPOSE_FILE_PATH" "$@"; }

# Encrypt in place when a key is set; echoes the final path.
finalize() {
    local file="$1"
    if [ -n "${BACKUP_ENCRYPTION_KEY:-}" ]; then
        openssl enc -aes-256-cbc -salt -pbkdf2 -iter 100000 \
            -in "$file" -out "${file}.enc" -pass env:BACKUP_ENCRYPTION_KEY
        rm -f "$file"
        file="${file}.enc"
    fi
    chmod 600 "$file"
    echo "$file"
}

upload() {
    local file="$1"
    [ -n "${S3_BUCKET:-}" ] || return 0
    local dest="s3://${S3_BUCKET}/backups/$(basename "$file")"
    local -a args=()
    [ -n "${S3_SSE:-}" ] && args+=(--sse "$S3_SSE")
    [ -n "${S3_ENDPOINT:-}" ] && args+=(--endpoint-url "$S3_ENDPOINT")
    aws s3 cp "$file" "$dest" "${args[@]}"
    log "Uploaded to $dest"
}

# ---------------------------------------------------------------- database
DB_FILE="${BACKUP_DIR}/${POSTGRES_DB}_${TIMESTAMP}.sql.gz"
log "Dumping PostgreSQL database '${POSTGRES_DB}' (${BACKUP_MODE} mode)…"
if [ "$BACKUP_MODE" = "compose" ]; then
    [ -f "$COMPOSE_FILE_PATH" ] || { log "ERROR: $COMPOSE_FILE_PATH not found — run from the deployment directory"; exit 1; }
    # -T: no TTY, so the dump streams cleanly through the pipe.
    compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        --no-owner --no-privileges --format=plain | gzip > "$DB_FILE"
else
    : "${POSTGRES_HOST:?POSTGRES_HOST is required in direct mode}"
    : "${PGPASSWORD:?PGPASSWORD is required in direct mode}"
    pg_dump -h "$POSTGRES_HOST" -p "${POSTGRES_PORT:-5432}" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        --no-owner --no-privileges --format=plain | gzip > "$DB_FILE"
fi
[ -s "$DB_FILE" ] || { log "ERROR: database dump is empty"; exit 1; }
DB_FILE=$(finalize "$DB_FILE")
log "Database backup: $DB_FILE ($(du -h "$DB_FILE" | cut -f1))"
upload "$DB_FILE"

# ------------------------------------------------------------- data volume
DATA_FILE="${BACKUP_DIR}/rag_data_${TIMESTAMP}.tar.gz"
if [ "$BACKUP_MODE" = "compose" ]; then
    BACKEND_ID=$(compose ps -q backend)
    [ -n "$BACKEND_ID" ] || { log "ERROR: backend container not found"; exit 1; }
    DATA_VOLUME=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Name}}{{end}}{{end}}' "$BACKEND_ID")
fi
if [ -n "${DATA_VOLUME:-}" ]; then
    log "Archiving data volume '${DATA_VOLUME}'…"
    docker run --rm -v "${DATA_VOLUME}:/data:ro" alpine tar czf - -C /data . > "$DATA_FILE"
elif [ -n "${DATA_DIR:-}" ]; then
    log "Archiving data directory '${DATA_DIR}'…"
    tar czf "$DATA_FILE" -C "$DATA_DIR" .
else
    log "WARNING: no data volume configured (set DATA_VOLUME or DATA_DIR) — documents, vectors and audit logs NOT backed up"
    DATA_FILE=""
fi
if [ -n "$DATA_FILE" ]; then
    [ -s "$DATA_FILE" ] || { log "ERROR: data archive is empty"; exit 1; }
    DATA_FILE=$(finalize "$DATA_FILE")
    log "Data backup: $DATA_FILE ($(du -h "$DATA_FILE" | cut -f1))"
    upload "$DATA_FILE"
fi

# ---------------------------------------------------------------- retention
DELETED=$(find "$BACKUP_DIR" -maxdepth 1 -type f \
    \( -name "*.sql.gz" -o -name "*.sql.gz.enc" -o -name "rag_data_*.tar.gz" -o -name "rag_data_*.tar.gz.enc" \) \
    -mtime +"$BACKUP_RETENTION_DAYS" -print -delete | wc -l)
[ "$DELETED" -gt 0 ] && log "Removed $DELETED backup file(s) older than ${BACKUP_RETENTION_DAYS} days"

log "Backup complete."
