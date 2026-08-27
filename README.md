# CaseCite — Private Legal RAG

[![License: ELv2](https://img.shields.io/badge/License-Elastic_v2-005571.svg)](LICENSE)

CaseCite is a **source-available, self-hosted** legal research platform. Upload your firm's documents, ask questions, and research cases & judges — all on infrastructure you control. AI calls use your own API keys (BYOK), so document content never passes through a third-party SaaS.

## What it does

Eight tools behind one login, all reading from the same document corpus.

| | |
|---|---|
| **Research** (`/research`) | Chat over your firm's documents — hybrid semantic + BM25 retrieval with reranking and inline citations back to the source. |
| **Documents** (`/documents`) | Upload, index, and organize your corpus. Import from Google Drive, OneDrive, Box, Dropbox, iManage, NetDocuments, Filevine, or Clio — OAuth sync, or a file picker where OAuth verification isn't needed. |
| **Contracts** (`/contracts`) | Full contract review pipeline: analyze an indexed contract or pasted text, chat with a single contract, compare 2–4 contracts clause-by-clause against a baseline, and export a redline, a draft, or the analysis itself. |
| **Drafting** (`/drafting`) | Draft a document grounded in up to four documents you pick from the Knowledge Base, with server-side text extraction and PDF conversion. Set a target length for long documents (30-page agreements): you review a section plan first, then every section is drafted in its own context window against the full references and the whole is reconciled. Revisions to long drafts are scoped to the sections they touch. |
| **Case view** (`/case/:id`) | Open a CourtListener opinion and chat with it directly. |
| **Authority map** (`/case-citations`) | Map the authorities cited across documents you select. |
| **Judge intel** (`/judge-intel`) | Judge analytics from CourtListener. |
| **Legal tools** (`/tools`) | Case lookup, citation check (a scan of citing opinions for negative-treatment language — not a Shepard's/KeyCite substitute), precedents, dockets, oral arguments, and case-law trends. |

**Practice profile.** Nothing about any practice area is baked into the product.
You state what you practice, CaseCite drafts a profile of what matters in that
practice, and you edit and own it (saved via Settings). It then rides along with
every review, redline, and draft as standing context.

AI calls use your own API keys (BYOK). Documents, chat history, and analyses stay
on your infrastructure.

## License & use

CaseCite is licensed under the **Elastic License 2.0** ([LICENSE](LICENSE)). In plain terms:

- ✅ Free to **self-host** for your firm's internal use.
- ✅ Free to **modify** for your own deployment.
- ❌ Not permitted to offer CaseCite to third parties as a hosted/managed service.
- ❌ Not permitted to alter or remove licensing or copyright notices.

For paid private installs, support contracts, or hosted-SaaS licensing, contact the maintainer.

> "Source-available," not OSI "open source." See [LICENSE](LICENSE) for the full terms.

## Quick start

### Prerequisites

- Docker + Docker Compose
- `openssl` (to generate secrets)
- One AI provider API key (OpenAI, Anthropic, or another supported provider)

### Run it (self-contained: bundles Postgres, Redis, and an HTTPS proxy)

```bash
git clone https://github.com/thomasunise/casecite.git && cd casecite
cp .env.example .env

# 1. Generate the three REQUIRED secrets (the .env.example placeholders
#    intentionally refuse to boot). Copy each value into .env:
openssl rand -hex 32   # -> SECRET_KEY
openssl rand -hex 32   # -> AUDIT_HMAC_KEY
openssl rand -hex 16   # -> ENCRYPTION_SALT

# 2. In .env also set one provider key (e.g. OPENAI_API_KEY), then uncomment
#    and set DOMAIN, POSTGRES_PASSWORD, and REDIS_PASSWORD in the "Bundled
#    production stack" section (generation hints are in the file; use
#    DOMAIN=localhost to try it on your machine). CORS_ORIGINS and
#    ALLOWED_HOSTS default from DOMAIN.

# 3. Set DISK_ENCRYPTION_ACKNOWLEDGED=true in .env (required to boot).
#    What this acknowledges: the app encrypts BYOK keys and uploaded documents
#    at the application layer (AES-256-GCM) on the data volume, but derived
#    text (vector chunks, chat history) is stored in cleartext — host-level /
#    full-disk encryption of that volume is YOUR responsibility as operator.

# 4. Start the full stack (bundled Postgres + Redis + Caddy):
docker compose -f docker-compose.prod.yml up -d
```

Then open **https://$DOMAIN** (with `DOMAIN=localhost`: **https://localhost**).
On a localhost trial Caddy redirects HTTP to HTTPS and serves a certificate
from its own self-signed local CA — the browser warning on first visit is
expected. See "TLS on Internal Networks" in [docs/deployment.md](docs/deployment.md)
to trust that CA or bring your own certificate.

The first account you register becomes the admin. For any network-reachable
fresh install, setting `REGISTRATION_BOOTSTRAP_TOKEN` in `.env` before first
boot is strongly recommended — otherwise whoever registers first owns the
admin account.

> Deploying behind an existing reverse proxy (Coolify/Traefik)? Use the root
> `docker-compose.yml` instead, and read `deploy/COOLIFY-SETUP.md` — you must also
> set `TRUSTED_PROXIES` to the proxy's subnet or client IPs collapse to one.

### Key custody (BYOK)

Users provide AI provider keys via the Settings modal. What firm evaluators
should know about custody:

- Per-user keys are stored **server-side**, AES-256-GCM-encrypted (PBKDF2 key
  derivation, HKDF per-record separation), in a file store on the data volume.
- Keys are displayed masked-only and are **never sent to the browser**; the
  backend decrypts them on demand for each request.
- Env-configured fallback keys (e.g. `OPENAI_API_KEY` in `.env`) are shared by
  **all users** of the install — per-user cost attribution requires per-user
  BYOK keys.
- `ENCRYPTION_SALT` can be rotated without losing stored keys: keep the old
  value in `ENCRYPTION_SALT_PREVIOUS` and run `python -m app.utils.reencrypt`
  inside the backend container — see `docs/secret-rotation.md`.

## Configuration

### Required env vars

The app fails closed on startup if any of these are missing or left as placeholders.

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | JWT/CSRF signing key — `openssl rand -hex 32` |
| `ENCRYPTION_SALT` | At-rest encryption salt — `openssl rand -hex 16` (**never change after first run**) |
| `AUDIT_HMAC_KEY` | Audit-log chain key — `openssl rand -hex 32` |
| `POSTGRES_PASSWORD` | Password for the bundled Postgres |
| `REDIS_PASSWORD` | Password for the bundled Redis |
| `DOMAIN` | Public hostname (or `localhost`); `CORS_ORIGINS` + `ALLOWED_HOSTS` default from it |
| `DISK_ENCRYPTION_ACKNOWLEDGED` | Set `true` to acknowledge that host/full-disk encryption of the data volume is your responsibility (app-layer AES-256-GCM covers BYOK keys + document originals; derived text is cleartext) |
| `OPENAI_API_KEY` *(or another provider)* | Default provider when no per-user BYOK key is set |
| `COURTLISTENER_API_TOKEN` | **Required.** CourtListener is the only case-law source in the app — Legal tools, Judge intel, Case view, and citation validation do not function without it. Free token; see [CourtListener API token](#courtlistener-api-token). |

> Using the root `docker-compose.yml` (external DB/Redis) instead of the bundled
> stack? Then `DATABASE_URL`, `REDIS_URL`, `CORS_ORIGINS`, and `ALLOWED_HOSTS`
> are required directly, and set `DB_SSL=require` for a managed database.

### Optional env vars

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Claude access |
| `VOYAGE_API_KEY` | — | Voyage AI legal embeddings |
| `VECTOR_DB` | `chroma` | `chroma` (local) or `pinecone` |
| `TRUSTED_PROXIES` | `127.0.0.1` | Reverse-proxy IP/CIDR — **required behind a proxy** |
| `REGISTRATION_BOOTSTRAP_TOKEN` | — | Token required to create the first (admin) account — strongly recommended for any network-reachable fresh install |
| `SENDGRID_API_KEY` | — | Enables password-reset emails (change-password works without it) |

### CourtListener API token

Legal tools, Judge intel, Case view, and the case-law side of the strategy
engine all read from [CourtListener](https://www.courtlistener.com). CourtListener is the **only** case-law source in
the app. Without a token the research half of the product does not work:

- **Citation check hard-fails without it** — the service raises
  `CourtListener API token required` (`backend/app/services/courtlistener.py`).
- Every other CourtListener call falls back to anonymous access, which is
  rate-limited hard enough that research features become unusable under any
  real load.

Get a **free** token at
<https://www.courtlistener.com/help/api/rest/#permissions>, then either set
`COURTLISTENER_API_TOKEN` in `.env`, or save it instance-wide via the
Integrations API (`POST /integrations/courtlistener`) — the stored token
overrides the `.env` value at runtime without a restart.

## Project structure

```
backend/
  app/
    main.py              FastAPI app, middleware, health
    config.py            Pydantic settings
    routers/             API routers
    services/
      rag/               RAG pipeline (search, generation, citations, intent)
      vectordb.py        ChromaDB/Pinecone abstraction
      embeddings.py      Multi-provider embeddings
      auth.py            JWT auth
      strategy.py        Matter strategy briefs
      courtlistener.py   CourtListener API
      ...
    middleware/          Security, CSRF
  migrations/            Alembic migrations
frontend/
  src/
    App.tsx
    api/                 Per-domain API clients
    views/               Page views
    stores/              Zustand stores
    components/          Shared components + modals
    layout/              App shell
Dockerfile
docker-compose.yml
```

## Backend-only (no UI yet)

These are implemented and reachable over the API, but nothing in the frontend
calls them yet. Treat them as preview:

- **Matters** (`/matters`) — matter records and scoping.
- **Strategy briefs** (`/strategy`) — the strongest thing in the codebase and
  currently API-only: each proposition is searched on CourtListener, each
  candidate opinion is read **in full**, and a citation is kept only when a
  verbatim quote can be located in the real opinion text. Unsupported
  citations are dropped rather than shown.
- **Admin audit log** (`/audit`) — the hash-chained audit trail.
- **Azure AD SSO** — backend login path only.

## Security

- JWT auth with JTI revocation (Redis or in-memory)
- TOTP multi-factor auth with recovery codes (`/mfa`)
- Role-based permissions (`require_permission`) on contract and matter routes
- CSRF double-submit cookies, HMAC-signed
- Rate limiting (configurable)
- AES-256-GCM at-rest encryption for API keys
- CSP, HSTS, X-Frame-Options, Permissions-Policy headers
- Audit trail with SHA-256 chain hashing

See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). PRs welcome for the source-available product. Note that contributions are licensed under ELv2.
