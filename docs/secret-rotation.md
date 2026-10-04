# Secret Rotation Guide

Rotation procedures for the bundled production stack (`docker-compose.prod.yml`:
Caddy + Postgres + Redis + backend). Where a step differs for the root
`docker-compose.yml` (external Postgres/Redis, e.g. Coolify) it says so.

Two facts shape every procedure below:

- **`docker compose restart` does not re-read `.env`.** After editing `.env`,
  recreate the service with `docker compose -f docker-compose.prod.yml up -d <service>`;
  Compose recreates only the containers whose configuration changed.
- **Postgres and Redis credentials are derived.** The backend's `DATABASE_URL`
  and `REDIS_URL` are built by the compose file from `POSTGRES_PASSWORD` and
  `REDIS_PASSWORD`. Editing `DATABASE_URL`/`REDIS_URL` in `.env` does nothing
  for the bundled stack.

## Secrets Inventory

| Secret | Where | Rotation impact |
|--------|-------|-----------------|
| `SECRET_KEY` | `.env` | Invalidates every session (JWT, CSRF, and — via HKDF — the key that encrypts uploaded files: **see the warning below**) |
| `ENCRYPTION_SALT` | `.env` | BYOK keys, connector tokens, TOTP secrets, instance secrets — safe with `ENCRYPTION_SALT_PREVIOUS` + re-encrypt |
| `AUDIT_HMAC_KEY` | `.env` | Old audit entries only verify while the old key is in `AUDIT_HMAC_KEY_PREVIOUS` |
| `POSTGRES_PASSWORD` | `.env` | Change in Postgres first, then recreate the backend |
| `REDIS_PASSWORD` | `.env` | Recreating Redis + backend applies it; Redis state written since its last snapshot (recent revocations, counters, in-flight jobs) can be lost |
| `OPENAI_API_KEY` etc. | `.env` (and per-user BYOK in Settings) | Rotate at the provider first |
| `SENDGRID_API_KEY` | `.env` | Rotate at the provider first |
| `BACKUP_ENCRYPTION_KEY` | wherever backups run | Old backups need the old key — keep both until they age out |

Log every rotation (who, when, which secret) in your change record; the
application audit log records the resulting session invalidations but not the
rotation itself.

## Procedures

### SECRET_KEY (JWT/CSRF signing)

> **Warning.** Uploaded documents are encrypted at rest with a key derived from
> `SECRET_KEY` (HKDF, `app/utils/file_crypto.py`). There is no previous-key
> mechanism for `SECRET_KEY`: rotating it makes every stored document
> unreadable. Rotate it only after a confirmed compromise, and only with a
> fresh backup and a plan to re-upload the corpus. In-place `SECRET_KEY`
> rotation is on the roadmap, not implemented.
>
> Be clear about what the supported rotations do and do not give you.
> `ENCRYPTION_SALT` is a key-derivation input, not the secret: the secret behind
> every at-rest key is `SECRET_KEY`. Rotating the salt re-derives the keys for
> stored API keys, connector tokens and TOTP secrets, which is useful hygiene,
> but it does **not** help after `SECRET_KEY` itself has leaked — an attacker
> who holds `SECRET_KEY` and the `.env` can derive the new keys too.

```bash
NEW_KEY=$(openssl rand -hex 32)
sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$NEW_KEY/" .env
docker compose -f docker-compose.prod.yml up -d backend
curl -sf https://app.yourfirm.com/health
```

Every user is signed out.

### ENCRYPTION_SALT (BYOK keys, connector tokens, TOTP secrets, instance secrets)

Supported rotation: the old salt stays in `ENCRYPTION_SALT_PREVIOUS`, so
existing ciphertexts keep decrypting while new writes use the new salt; a
re-encryption pass then rewrites everything so the old salt can be retired.

```bash
# 1. Generate the new salt and the exact .env lines to paste
python3 scripts/rotate_encryption_key.py
#    -> ENCRYPTION_SALT=<new>
#    -> ENCRYPTION_SALT_PREVIOUS=<old>[,older,...]

# 2. Put both lines in .env, then recreate the backend
docker compose -f docker-compose.prod.yml up -d backend

# 3. Rewrite every stored ciphertext under the new salt (dry run first)
docker compose -f docker-compose.prod.yml exec backend python -m app.utils.reencrypt --dry-run
docker compose -f docker-compose.prod.yml exec backend python -m app.utils.reencrypt

# 4. When it reports 0 failures, retire the old salt
sed -i '/^ENCRYPTION_SALT_PREVIOUS=/d' .env
docker compose -f docker-compose.prod.yml up -d backend
```

If step 3 reports failures, those values were already unreadable (written under
a salt that is not in the list). Leave `ENCRYPTION_SALT_PREVIOUS` in place
until the affected users re-enter their keys or reconnect the connector.

**Recommended frequency**: every 180 days or after any suspected compromise.

### AUDIT_HMAC_KEY (audit-chain signing)

Every audit entry is HMAC-signed over its full stored form and chained to the
previous entry. On startup the app recomputes the signatures of the most recent
entries and, in production, refuses to boot if any fail — so the retired key
must stay available until the entries signed under it age out of
`AUDIT_RETENTION_DAYS`.

```bash
# 1. New key
openssl rand -hex 32
# 2. In .env: move the current AUDIT_HMAC_KEY value to AUDIT_HMAC_KEY_PREVIOUS,
#    put the new value in AUDIT_HMAC_KEY
# 3. Recreate the backend — new entries use the new key; startup verification
#    and GET /api/v1/admin/audit/verify accept either
docker compose -f docker-compose.prod.yml up -d backend
# 4. After AUDIT_RETENTION_DAYS have passed
sed -i '/^AUDIT_HMAC_KEY_PREVIOUS=/d' .env
docker compose -f docker-compose.prod.yml up -d backend
```

Rotated without step 2 and now the app refuses to start with
`AUDIT ENTRY HMAC MISMATCH`? Add the old key as `AUDIT_HMAC_KEY_PREVIOUS` and
recreate. Only if the old key is genuinely lost fall back to
`AUDIT_HALT_ON_TAMPERING=false`, run the verify endpoint, and record the break
in your incident log — the chain before that point can no longer be attested.

### POSTGRES_PASSWORD

The bundled database has one role, `casecite` (`POSTGRES_USER`), which owns the
`casecite` database; there is no separate `postgres` superuser password to
know. The backend reads `POSTGRES_PASSWORD` through the compose file.

```bash
NEW_PW=$(openssl rand -hex 32)

# 1. Change it in Postgres (connect as the app role over the container's local socket)
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U casecite -d casecite -c "ALTER USER casecite PASSWORD '$NEW_PW';"

# 2. Update .env — POSTGRES_PASSWORD only; DATABASE_URL is derived from it
sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$NEW_PW/" .env

# 3. Recreate the backend so it picks up the new URL
docker compose -f docker-compose.prod.yml up -d backend
curl -sf https://app.yourfirm.com/ready
```

Root `docker-compose.yml` / managed Postgres: change the password at the
provider, update `DATABASE_URL` in `.env`, then `docker compose up -d backend`.

**Recommended frequency**: every 90 days.

### REDIS_PASSWORD

Redis gets its password as a command-line argument (`--requirepass`), so it is
applied by recreating the container, not by `CONFIG SET` (which an
unauthenticated `redis-cli` cannot run anyway and which would not survive a
restart). Redis holds token revocations, account-lockout and rate-limit
counters, consumed MFA challenges, OAuth state and job results. (Sessions
themselves are held by the backend process and mirrored to `sessions.jsonl` on
the data volume.) Recreating the container keeps the `redis_data` volume, so
Redis reloads its last snapshot; anything written since that snapshot — recent
revocations, counters, in-flight job results — can be lost. Do it in a
maintenance window, and after an incident have affected users change their
passwords, which invalidates their older tokens regardless of Redis.

```bash
NEW_PW=$(openssl rand -hex 32)
sed -i "s/^REDIS_PASSWORD=.*/REDIS_PASSWORD=$NEW_PW/" .env
docker compose -f docker-compose.prod.yml up -d redis backend   # REDIS_URL is derived
curl -sf https://app.yourfirm.com/ready
```

Root `docker-compose.yml` / managed Redis: change the password at the provider,
update `REDIS_URL`, then `docker compose up -d backend`.

**Recommended frequency**: every 90 days.

### Provider API keys (OpenAI, Anthropic, Voyage, Cohere, Google, SendGrid, CourtListener)

1. Create the new key in the provider's dashboard.
2. Instance-wide keys: update the variable in `.env` and
   `docker compose -f docker-compose.prod.yml up -d backend`. The CourtListener
   token can instead be saved at runtime via `POST /api/v1/admin/integrations/courtlistener`
   (no restart).
3. Per-user BYOK keys: each user replaces theirs in Settings → API keys; an
   admin cannot rotate them centrally.
4. Verify (a research query, a citation check, a test email), then revoke the
   old key at the provider.

### BACKUP_ENCRYPTION_KEY

Backups written before the rotation still need the old key. Keep both keys
(clearly labelled with the date range each covers) until every backup made
with the old key has passed `BACKUP_RETENTION_DAYS`.

## Verify after any rotation

```bash
python3 scripts/setup_production.py --validate    # required secrets present and well-formed
curl -sf https://app.yourfirm.com/ready           # DB + Redis reachable
docker compose -f docker-compose.prod.yml logs --tail=50 backend
```
