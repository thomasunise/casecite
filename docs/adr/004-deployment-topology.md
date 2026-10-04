# ADR-004: Deployment Topology

**Status:** Accepted — revised 2026-10-04 to match the code as shipped
**Date:** Recorded 2026-05-03 (the decision predates the record)
**Decision makers:** Core maintainers

> **Revision note (2026-10-04).** Corrected the Redis eviction policy, the scaling path (Pinecone alone does not allow multiple workers) and the description of what Coolify provides.

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

### Coolify / PaaS mode (root `Dockerfile`, deployed via the root `docker-compose.yml`)

- **1 container**: Multi-stage build combining frontend (Vite → static files) and backend (nginx + uvicorn)
- **Database and Redis**: External PostgreSQL **and** Redis, both required in production (provisioned on the hosting platform or managed services)
- **Persistent volume**: `/app/data` must be a named volume (the root `docker-compose.yml` declares it). Deploying the bare Dockerfile gives the container an anonymous volume that is replaced on redeploy, losing uploads, the vector index and the audit log
- **Reverse proxy**: Platform-managed (Coolify/Render handle HTTPS)
- **Entrypoint** (`start.sh`): Starts nginx (daemonized) then uvicorn (foreground), drops privileges to non-root `appuser` via gosu, handles SIGTERM gracefully
- **SPA routing**: nginx serves static files from `/var/www/html`, proxies `/api/*` to uvicorn on localhost:8000

### Production VPS mode (`docker-compose.prod.yml`)

- **4 containers**: Caddy, PostgreSQL 16, Redis 7, Backend (nginx + uvicorn)
- **Reverse proxy**: Caddy with automatic Let's Encrypt HTTPS
- **Resource limits**: Backend capped at 2 CPU / 4 GB RAM
- **Redis**: Token revocation, account lockout, rate limiting, job results (512 MB, `noeviction` — an LRU policy would silently drop revocation and lockout keys)
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

All deployment modes run a single uvicorn worker, and the app refuses to start otherwise. ChromaDB's SQLite backend is one reason; the session store, the document registry (`uploads/index.json`) and the connector caches are also process-local.

The scaling path is:
1. Move the session store, document registry and connector caches to Redis/PostgreSQL (not done — see `ROADMAP.md`)
2. Switch to Pinecone (`VECTOR_DB=pinecone`)
3. Increase `UVICORN_WORKERS` and deploy multiple backend instances behind a load balancer

Until step 1 is done, scale vertically.

## Consequences

### Positive

- **One image, three environments.** The same Dockerfile builds the artifact for Coolify, VPS, and (with target selection) development. No per-environment build divergence.
- **Zero-to-production in minutes.** Development: `docker compose up`. Coolify: point repo, set env vars, deploy. VPS: `setup_production.py --create-env && docker compose up`.
- **Automatic HTTPS.** Caddy eliminates certificate management — no cron jobs for certbot renewal, no manual key rotation, no certificate expiry incidents.
- **Each mode brings only what it needs.** Development runs without Redis or PostgreSQL (`DEBUG=true`); the single-container mode needs an external PostgreSQL and Redis but no Caddy; the VPS stack bundles everything.
- **Cost efficient.** A $20/month 2-CPU VPS runs the full production stack. No Kubernetes cluster fees, no managed service premiums.

### Negative

- **Single-worker bottleneck.** Process-local state (sessions, document registry, connector caches, the embedded vector index) means the backend cannot be scaled horizontally today.
- **No container orchestration.** Without Kubernetes or Swarm, there is no automated container restart, rolling deployment, or health-based routing. Docker Compose restarts on failure but does not do zero-downtime deploys.
- **Nginx duplication.** Nginx runs inside the backend container (for SPA routing) while Caddy runs outside (for HTTPS). Two reverse proxies in the request path adds latency and configuration surface.
- **Manual scaling.** Scaling from 1 to N backend instances requires manual load balancer configuration. Kubernetes would automate this, but its operational overhead is not justified at current scale.

### Alternatives rejected

- **Kubernetes**: Requires a managed cluster ($75+/month minimum) or self-hosted control plane. Operational overhead (RBAC, ingress controllers, service mesh, resource quotas) is disproportionate to a 4-container deployment. Justified at 10+ services or when auto-scaling is required.
- **Separate frontend/backend images**: Adds a second build pipeline, second image registry, and version coordination between frontend and backend. The unified image ensures the frontend and backend are always in sync.
- **Serverless (Lambda/Cloud Run)**: ChromaDB requires persistent local storage (SQLite files), which is incompatible with ephemeral serverless containers. Cold start latency (2-5 seconds for Python + ML libraries) degrades user experience. Legal workloads are also long-running (RAG queries take 5-30 seconds), which conflicts with serverless pricing models.
- **Bare metal / systemd**: No reproducibility, no isolation, manual dependency management. Docker ensures identical behavior across developer machines, CI, and production.
- **Traefik**: More complex configuration than Caddy for the same feature set. Docker provider integration is powerful for dynamic service discovery in Kubernetes, but unnecessary for a static 4-container compose file.
