# Deployment Guide

This guide covers the three supported deployment modes for CaseCite.

## Deployment Modes

| Mode | Use Case | Database | Reverse Proxy | Containers |
|------|----------|----------|---------------|------------|
| Development | Local dev | SQLite | None | 1 (backend) |
| Coolify | PaaS hosting | PostgreSQL (external) | Platform-managed | 1 (unified) |
| Production VPS | Self-hosted | PostgreSQL | Caddy (auto-HTTPS) | 4 |

---

## Development

```bash
# 1. Clone and configure
git clone <repo-url> && cd "CaseCite"
cp .env.example .env
# Edit .env — set at minimum OPENAI_API_KEY

# 2. Start backend (Docker)
docker compose -f docker-compose.dev.yml up -d

# 3. Start frontend (hot-reload)
cd frontend && npm install && npm run dev
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- API docs: http://localhost:8000/docs

---

## Coolify / Single Container

The unified `Dockerfile` builds both frontend and backend into one container with nginx serving static files and proxying API requests to uvicorn.

```bash
# Build
docker build -t casecite .

# Run
docker run -p 80:80 \
  -e OPENAI_API_KEY=sk-... \
  -e SECRET_KEY=$(openssl rand -hex 32) \
  -e ENCRYPTION_SALT=$(openssl rand -hex 16) \
  -e DATABASE_URL=postgresql+asyncpg://user:pass@host/db \
  -v casecite_data:/app/data \
  casecite
```

For Coolify: point to the repo, set environment variables in the Coolify dashboard, and deploy. The health check endpoint is `GET /health`.

---

## Production VPS (Auto-HTTPS)

### Server setup

Any provider works the same way (Hetzner, DigitalOcean, Linode, Vultr,
on-prem). Minimum 2 vCPU / 4 GB RAM, Ubuntu 22.04+ LTS, public IPv4, your SSH
key installed. Point a DNS A record (`casecite.yourfirm.com → SERVER_IP`) at it
before starting the stack so Caddy can obtain a certificate.

```bash
ssh root@SERVER_IP
curl -fsSL https://get.docker.com | sh          # Docker + Compose v2
apt-get install -y git
git clone https://github.com/thomasunise/casecite.git /opt/casecite
cd /opt/casecite
```

Before going live, have to hand: the domain and DNS control; each provider
API key the firm will use (the install brings its own keys); for SSO, the
Azure AD tenant ID and app registration; for connectors, the OAuth client
credentials of each service; the firm's data- and audit-retention policy; and
host-level encryption on the disk that will hold the `rag_data` volume
(`DISK_ENCRYPTION_ACKNOWLEDGED` is a promise you are making).

```bash
# 1. Generate secrets
python scripts/setup_production.py --create-env
# Review and edit .env with your values

# 2. Validate configuration
python scripts/setup_production.py --validate

# 3. Start all services
docker compose -f docker-compose.prod.yml up -d
```

This starts 4 services:
- **caddy** — Reverse proxy with automatic Let's Encrypt certificates
- **postgres** — PostgreSQL 16 database
- **redis** — Redis 7 for sessions, rate limiting, and token revocation
- **backend** — Application server (nginx + uvicorn)

### DNS Setup

Point your domain's A record to your server's IP. Caddy handles certificate provisioning automatically once DNS resolves.

Set the `DOMAIN` environment variable in `.env`:
```
DOMAIN=app.yourfirm.com
```

### Resource Requirements

- **Minimum**: 2 CPU, 4 GB RAM, 20 GB SSD
- **Recommended**: 4 CPU, 8 GB RAM, 50 GB SSD (for larger document corpora)

---

## Health Checks

All deployment modes expose these endpoints:

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Application health (returns `{"status": "healthy"}`) |
| `GET /ready` | Readiness check (database connectivity) |
| `GET /metrics` | Basic metrics (uptime, request counts) — requires an admin bearer token in production |

---

## Scaling Considerations

**CaseCite currently runs as exactly one backend process.** The app refuses to
start when `UVICORN_WORKERS` is set to anything other than `1` (or unset),
whatever `VECTOR_DB` is, and the same constraint applies to running more than
one container replica behind a single URL. Switching the vector database to
Pinecone does **not** lift it.

Three stores are process-local and are not safe to share between workers or
replicas:

| Store | Where | What breaks with two processes |
|-------|-------|--------------------------------|
| Session store | `middleware/security.py` `SessionManager` — in-memory dict mirrored to `data/sessions.jsonl` | Logins, logouts and "terminate all sessions" only take effect in the process that handled them |
| Document registry | `services/documents.py` — `data/uploads/index.json` is read once per process and rewritten whole on every change | Processes overwrite each other's uploads and deletions; documents "index" and can never be found |
| Connector caches | `services/connectors/*` — per-process credential/state caches | Token refreshes in one process are invisible to the others |

(The embedded Chroma store is a fourth, but it is the only one Pinecone fixes.)

Horizontal scaling therefore needs those stores moved to Redis/Postgres first —
this is tracked in `ROADMAP.md` under "Multi-worker / multi-replica
deployments". Until then, scale vertically (CPU/RAM for the single container)
and keep `UVICORN_WORKERS` unset.

PostgreSQL and Redis themselves already support multi-instance deployments, so
once the app-side stores move there, the remaining steps are: switch to Pinecone
(`VECTOR_DB=pinecone`, `PINECONE_API_KEY`, `PINECONE_ENVIRONMENT`,
`PINECONE_INDEX_NAME`), raise `UVICORN_WORKERS` (read by `start.sh`), and put a
load balancer in front of the replicas.

---

## Rollback Procedure

### Application (image tag)

`docker-compose.prod.yml` runs `CASECITE_IMAGE:CASECITE_TAG` (default: the
image CI publishes to GHCR, tagged with each commit's full SHA and `latest`).
Rolling back is choosing an earlier tag — the frontend is copied out of the
same image, so it rolls back with the backend.

```bash
# 1. Find the tag you were running before (the CD workflow records it in .env;
#    otherwise: docker images ghcr.io/thomasunise/casecite)
grep CASECITE_TAG .env

# 2. Start the previous build. Postgres, Redis and the data volume are untouched.
CASECITE_TAG=<previous-sha> docker compose -f docker-compose.prod.yml pull backend frontend-build
CASECITE_TAG=<previous-sha> docker compose -f docker-compose.prod.yml up -d

# 3. Make it stick for later `up -d` runs
sed -i 's/^CASECITE_TAG=.*/CASECITE_TAG=<previous-sha>/' .env

# 4. Verify
curl -sf https://app.yourfirm.com/health
```

If the release you are leaving added a database migration, decide whether to
keep it (the older code ignores tables and columns it does not know about —
usually fine) or roll it back too (below, **before** starting the old image).
When in doubt, restore the pre-deploy backup instead.

### Database migration

```bash
# Roll back the most recent migration (runs inside the backend container)
docker compose -f docker-compose.prod.yml exec backend alembic downgrade -1

# Or to a specific revision
docker compose -f docker-compose.prod.yml exec backend alembic downgrade <revision_id>
```

### Backup before every deploy

```bash
./scripts/backup_database.sh                                    # database + data volume
./scripts/restore_database.sh backups/casecite_<ts>.sql.gz \
    --data backups/rag_data_<ts>.tar.gz --yes                   # if the deploy goes wrong
```

---

## Backups

`scripts/backup_database.sh` runs on the **host**, from the directory that
holds `docker-compose.prod.yml` (the backend image ships neither `pg_dump` nor
the script). It produces two files per run and encrypts both when
`BACKUP_ENCRYPTION_KEY` is set:

| File | Contents |
|---|---|
| `casecite_<ts>.sql.gz` | PostgreSQL: users, matters, chat history, analyses, audit-log mirror |
| `rag_data_<ts>.tar.gz` | the `/app/data` volume: uploaded documents (encrypted at rest), ChromaDB vector index, audit-log chain, BYOK key store, sessions, instance secrets |

```bash
# Daily at 02:00 — put BACKUP_ENCRYPTION_KEY (and S3_* if used) in the cron
# environment or a file sourced by it, not on the command line.
0 2 * * * cd /opt/casecite && ./scripts/backup_database.sh >> /var/log/casecite-backup.log 2>&1
```

Keep `BACKUP_ENCRYPTION_KEY` somewhere other than this server (password
manager, KMS). Without it the `.enc` files are unrecoverable, and with it on
the same disk the encryption protects nothing.

Managed/external Postgres: set `BACKUP_MODE=direct` with `POSTGRES_HOST`,
`POSTGRES_USER`, `PGPASSWORD` and `pg_dump` on the host, plus `DATA_VOLUME`
(docker volume name) or `DATA_DIR` (host path) so the data volume is still
archived.

**Restore** — always from the same run, otherwise document records and their
vectors drift out of sync. The script stops the backend, recreates the
database, restores the dump and (with `--data`) the volume, then starts the
backend, which applies any pending migrations:

```bash
BACKUP_ENCRYPTION_KEY=… ./scripts/restore_database.sh \
    backups/casecite_<ts>.sql.gz.enc --data backups/rag_data_<ts>.tar.gz.enc --yes
```

Test a restore onto a scratch host at least quarterly; a backup that has
never been restored is a hope, not a backup.

---

## TLS on Internal Networks

Firms deploying on a LAN or VPN without public DNS can't use Let's Encrypt.
Three options, each a small `Caddyfile` change inside the site block:

**Option 1 — Caddy's internal CA (zero config, self-signed):**

```caddy
{$DOMAIN:localhost} {
    tls internal
    # ... rest of the site block unchanged
}
```

Caddy creates a local root CA and issues certificates from it. Browsers warn
until you install that root CA on client machines; export it from the caddy
container at `/data/caddy/pki/authorities/local/root.crt`. This is also what
happens automatically for a `DOMAIN=localhost` trial — the certificate warning
on first visit is expected.

**Option 2 — bring your own certificate (corporate CA or purchased):**

```caddy
{$DOMAIN} {
    tls /etc/caddy/certs/casecite.crt /etc/caddy/certs/casecite.key
    # ... rest of the site block unchanged
}
```

Mount the files in `docker-compose.prod.yml` under the `caddy` service:

```yaml
    volumes:
      - ./certs:/etc/caddy/certs:ro
```

**Option 3 — internal ACME server (e.g. smallstep, corporate ACME):**

```caddy
{$DOMAIN} {
    tls {
        ca https://ca.internal.example.com/acme/acme/directory
    }
}
```

---

## Troubleshooting

**The app won't start** — `docker compose -f docker-compose.prod.yml logs backend`.
Production fails closed on purpose: the log names the missing or placeholder
setting (`SECRET_KEY`, `AUDIT_HMAC_KEY`, `ENCRYPTION_SALT`, `POSTGRES_PASSWORD`,
`REDIS_PASSWORD`, `DISK_ENCRYPTION_ACKNOWLEDGED`, a provider key). An
`AUDIT ENTRY HMAC MISMATCH` at boot means the audit chain failed verification —
see `docs/secret-rotation.md` before overriding it.

**No certificate / browser warning** — Caddy needs DNS to resolve to this
server and ports 80/443 reachable from the internet. `docker compose -f
docker-compose.prod.yml logs caddy` shows the ACME exchange. On a LAN with no
public DNS, see "TLS on Internal Networks" above.

**Users see 429 or get locked out together** — `TRUSTED_PROXIES` does not
match the proxy in front of the backend, so every client resolves to one IP.
The bundled stack pins it; behind Coolify/Traefik set it to the proxy's subnet.

**Out of memory** — `docker stats`; the backend is capped at 4 GB in the
compose file. OCR and large PDF extraction are the usual culprits; raise the
limit or the VPS size.

---

## Monitoring

### Logs

```bash
# All services
docker compose -f docker-compose.prod.yml logs -f

# Backend only
docker compose -f docker-compose.prod.yml logs -f backend

# Caddy access logs
docker compose -f docker-compose.prod.yml exec caddy cat /data/access.log
```

### Audit Logs

Audit logs are stored in `/app/data/audit_logs/` inside the backend container, rotated daily in JSONL format. They include chain hashing for tamper detection.

```bash
# View today's audit log
docker compose -f docker-compose.prod.yml exec backend \
  cat /app/data/audit_logs/$(date +%Y-%m-%d).jsonl | head -20
```
