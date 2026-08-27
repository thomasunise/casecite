# ADR-004: Deployment Topology

**Status:** Accepted
**Date:** 2025-01-15
**Decision makers:** Core maintainers

## Context

CaseCite needs to serve three distinct deployment scenarios with a single codebase:

1. **Local development** — Fast iteration with hot-reload, minimal infrastructure
2. **Managed platform hosting** — PaaS services (Coolify, Render, Railway) that expect a single container
3. **Self-hosted production** — VPS deployments with full infrastructure control, automatic HTTPS, and service isolation

We also need to address the constraint that ChromaDB's SQLite backend does not support concurrent writes, limiting horizontal scaling until a Pinecone migration.

The main options considered:

1. **Single Dockerfile, multiple compose files** — One build artifact, different orchestration per environment
2. **Kubernetes** — Container orchestration with Helm charts
3. **Separate Dockerfiles per service** — Independent frontend and backend images
4. **Serverless (Lambda/Cloud Run)** — Function-level deployment
5. **Bare metal / systemd** — No containerization

## Decision

We chose **one universal Dockerfile with environment-specific compose files** (option 1).

### Development mode (`docker-compose.dev.yml`)

- **1 container**: Backend only (uvicorn with `--reload`)
- **Frontend**: Runs separately via `npm run dev` (Vite hot-reload on port 3000)
- **Database**: SQLite (in-container, no external dependency)
- **No reverse proxy**: Direct access to backend on port 8000
- Backend code mounted as read-only volume for live reload without rebuilds

### Coolify / PaaS mode (root `Dockerfile`)

- **1 container**: Multi-stage build combining frontend (Vite → static files) and backend (nginx + uvicorn)
- **Database**: External PostgreSQL (provided by hosting platform)
- **Reverse proxy**: Platform-managed (Coolify/Render handle HTTPS)
- **Entrypoint** (`start.sh`): Starts nginx (daemonized) then uvicorn (foreground), drops privileges to non-root `appuser` via gosu, handles SIGTERM gracefully
- **SPA routing**: nginx serves static files from `/var/www/html`, proxies `/api/*` to uvicorn on localhost:8000

### Production VPS mode (`docker-compose.prod.yml`)

- **4 containers**: Caddy, PostgreSQL 16, Redis 7, Backend (nginx + uvicorn)
- **Reverse proxy**: Caddy with automatic Let's Encrypt HTTPS
- **Resource limits**: Backend capped at 2 CPU / 4 GB RAM
- **Redis**: Sessions, rate limiting, token revocation (256 MB, LRU eviction)
- **Volumes**: Persistent storage for Caddy certificates, PostgreSQL data, Redis data, application data (ChromaDB, uploads, audit logs)

### Why Caddy over Nginx/Traefik

Caddy was chosen as the production reverse proxy for:

- **Automatic HTTPS**: Provisions, renews, and installs Let's Encrypt certificates with zero configuration. Set `DOMAIN=app.yourfirm.com` and it works.
- **Minimal configuration**: The Caddyfile is 51 lines vs. typical 200+ line nginx configs with separate certbot setup.
- **Built-in security headers**: X-Content-Type-Options, X-Frame-Options, HSTS, and CSP are configured declaratively.
- **Small image**: 13 MB (Alpine) vs. 110 MB (Nginx) — faster pulls, smaller attack surface.
- **Structured logging**: Built-in log rotation (10 MB files, keep 5) without logrotate configuration.

Nginx is still used *inside* the backend container for static file serving and API proxying (it's better suited for same-process SPA routing than Caddy's file_server).

### Scaling constraint

All deployment modes run a single uvicorn worker because ChromaDB's SQLite backend does not support concurrent writes from multiple processes. This is documented in `start.sh` and is the primary throughput bottleneck (~200-400 req/s).

The scaling path is:
1. Switch to Pinecone (`VECTOR_DB=pinecone`)
2. Increase `UVICORN_WORKERS` (no longer constrained by SQLite)
3. Deploy multiple backend instances behind a load balancer
4. PostgreSQL and Redis already support multi-instance deployments

## Consequences

### Positive

- **One image, three environments.** The same Dockerfile builds the artifact for Coolify, VPS, and (with target selection) development. No per-environment build divergence.
- **Zero-to-production in minutes.** Development: `docker compose up`. Coolify: point repo, set env vars, deploy. VPS: `setup_production.py --create-env && docker compose up`.
- **Automatic HTTPS.** Caddy eliminates certificate management — no cron jobs for certbot renewal, no manual key rotation, no certificate expiry incidents.
- **Graceful degradation.** Each mode works without the services of the higher modes: dev works without Redis or PostgreSQL, Coolify works without Caddy, VPS works without external dependencies.
- **Cost efficient.** A $20/month 2-CPU VPS runs the full production stack. No Kubernetes cluster fees, no managed service premiums.

### Negative

- **Single-worker bottleneck.** ChromaDB's SQLite constraint limits throughput. Until Pinecone migration, the platform cannot horizontally scale the backend.
- **No container orchestration.** Without Kubernetes or Swarm, there is no automated container restart, rolling deployment, or health-based routing. Docker Compose restarts on failure but does not do zero-downtime deploys.
- **Nginx duplication.** Nginx runs inside the backend container (for SPA routing) while Caddy runs outside (for HTTPS). Two reverse proxies in the request path adds latency and configuration surface.
- **Manual scaling.** Scaling from 1 to N backend instances requires manual load balancer configuration. Kubernetes would automate this, but its operational overhead is not justified at current scale.

### Alternatives rejected

- **Kubernetes**: Requires a managed cluster ($75+/month minimum) or self-hosted control plane. Operational overhead (RBAC, ingress controllers, service mesh, resource quotas) is disproportionate to a 4-container deployment. Justified at 10+ services or when auto-scaling is required.
- **Separate frontend/backend images**: Adds a second build pipeline, second image registry, and version coordination between frontend and backend. The unified image ensures the frontend and backend are always in sync.
- **Serverless (Lambda/Cloud Run)**: ChromaDB requires persistent local storage (SQLite files), which is incompatible with ephemeral serverless containers. Cold start latency (2-5 seconds for Python + ML libraries) degrades user experience. Legal workloads are also long-running (RAG queries take 5-30 seconds), which conflicts with serverless pricing models.
- **Bare metal / systemd**: No reproducibility, no isolation, manual dependency management. Docker ensures identical behavior across developer machines, CI, and production.
- **Traefik**: More complex configuration than Caddy for the same feature set. Docker provider integration is powerful for dynamic service discovery in Kubernetes, but unnecessary for a static 4-container compose file.
