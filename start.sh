#!/bin/bash
set -e

# Graceful shutdown handler
cleanup() {
    echo "Shutting down..."
    nginx -s quit 2>/dev/null || true
    kill -TERM "$UVICORN_PID" 2>/dev/null || true
    wait "$UVICORN_PID" 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT SIGQUIT

# Fix volume ownership (runs as root). Only directories get a mode: the app
# creates its secret-bearing files (.instance_secrets.json, .user_keys.json,
# sessions, revoked tokens, audit logs, connector credentials) with 0600, and a
# recursive chmod here would re-open them on every boot. appuser owns
# everything after the chown, so owner-rw is all SQLite/Chroma need.
echo "Ensuring data directories..."
mkdir -p /app/data/chroma /app/data/uploads /app/data/audit_logs /app/data/user_settings
chown -R appuser:appuser /app/data
find /app/data -type d -exec chmod 750 {} +

# Clean up stale ChromaDB lock files from unclean shutdowns
rm -f /app/data/chroma/*.lock 2>/dev/null || true

# Run database migrations (PostgreSQL only). Fail loudly if the Alembic config
# is missing — a silent skip means schema changes never apply and the DB drifts
# in production. SQLite (no DATABASE_URL) is a dev-only (DEBUG=true) path whose schema is
# built entirely by the app's create_all on startup; the migration chain uses
# ALTER CONSTRAINT operations SQLite cannot execute.
if [ "${SKIP_MIGRATIONS:-false}" = "true" ]; then
    echo "SKIP_MIGRATIONS=true — skipping Alembic migrations (schema managed out-of-band)."
elif [ -z "${DATABASE_URL:-}" ] || case "$DATABASE_URL" in sqlite*) true;; *) false;; esac; then
    echo "SQLite database — skipping Alembic migrations (schema managed by create_all; dev only)."
elif [ -f "/app/alembic.ini" ]; then
    echo "Running database migrations..."
    # Brownfield bootstrap: databases built by create_all before migrations
    # shipped have tables but no alembic_version — stamp the baseline so
    # `upgrade head` doesn't try to CREATE TABLE over the existing schema.
    cd /app && python -m app.utils.migration_bootstrap || { echo "ERROR: migration bootstrap failed"; exit 1; }
    alembic upgrade head || { echo "ERROR: Alembic migrations failed"; exit 1; }
    echo "Migrations complete."
else
    echo "ERROR: /app/alembic.ini not found — migrations cannot run. This image is misbuilt."
    echo "       Set SKIP_MIGRATIONS=true only if you intentionally manage schema out-of-band."
    exit 1
fi

# Start nginx in background (as root, it will fork workers)
echo "Starting nginx..."
nginx

# Validate gosu is available for privilege drop
if ! command -v gosu &> /dev/null; then
    echo "ERROR: gosu not found - cannot drop privileges safely"
    exit 1
fi

# Verify privilege drop works before starting uvicorn
if ! gosu appuser id &> /dev/null; then
    echo "ERROR: gosu cannot switch to appuser - check user configuration"
    exit 1
fi

# In the unified image nginx proxies to uvicorn over loopback, so the only
# trusted hop is 127.0.0.1. Default TRUSTED_PROXIES accordingly so client-IP
# resolution (rate limiting, lockout, audit) reads the real X-Forwarded-For
# instead of collapsing every client onto the nginx address.
export TRUSTED_PROXIES=${TRUSTED_PROXIES:-127.0.0.1}

# Start uvicorn as appuser for security
echo "Starting uvicorn..."
# ChromaDB PersistentClient uses SQLite which doesn't support concurrent
# writes from multiple processes. Use 1 worker until switching to Pinecone.
WORKER_COUNT=${UVICORN_WORKERS:-1}
gosu appuser uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers $WORKER_COUNT &
UVICORN_PID=$!

# Wait for uvicorn to exit
wait "$UVICORN_PID"
