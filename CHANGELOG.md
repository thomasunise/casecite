# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [1.2.0] - 2026-08-27

### Added
- Every generated artifact carries a review notice — "AI-generated. Verify every statement, citation and clause against the source documents and current law before relying on it." — in the UI (research answers, contract analyses, redlines, drafts, judge briefs, citation checks, authority maps, contract/case/tool chats) and as a closing paragraph in every Word, Markdown and PDF export. The drafting prompts that told the model to omit caveats and never suggest consulting an attorney are gone.
- Retrieved documents, CourtListener opinions and contract text are passed to the model inside explicit untrusted-content delimiters with a standing rule that instructions found inside them are data to be ignored (and mentioned); the user-query sanitizer no longer rewrites legitimate legal phrasing such as "act as attorney-in-fact".
- `NOTICE.md` lists every bundled third-party license (116 Python, 44 npm packages; none GPL/AGPL/SSPL). Contributions are accepted under the Developer Certificate of Origin (`git commit -s`), documented in CONTRIBUTING.md and the PR template.
- `API_TIMEOUT` (default 180 s) is now applied to every LLM and embedding client, with two SDK retries; previously the SDK's 600 s default was used and the setting was never read.
- Long-document drafting: set a target length in the Drafting workspace and the draft is planned first (sections, briefs, what each section must leave to others, shared definitions, style guide) from the full reference documents; after review, every section is drafted in parallel in its own context window with the full references and the whole plan, then a reconcile pass fixes cross-references, numbering and defined-term drift. `POST /contract-analysis/draft/plan` and `/draft/generate`.
- Revisions of long drafts are scoped: only the sections an instruction touches are rewritten (a selected clause routes straight to its section), the rest is left byte-for-byte.
- Background jobs report progress (`GET /jobs/{id}` → `progress: {message, fraction}`); the Drafting workspace shows it while sections are drafted.
- `LLM_CONTEXT_WINDOW` to declare the chat model's context size for custom/local endpoints whose names don't say.

### Fixed
- Drafting no longer silently truncates reference documents (and the draft being revised) at 40,000 characters — about ten pages; the budget is now derived from the model's context window.
- Redline .docx export renders from the text extracted from the stored original file instead of the vector-chunk reconstruction (which repeated text at every chunk seam); stored edits are re-anchored by their verbatim original text, unlocatable ones are listed in the document, multi-paragraph deletions are tracked per paragraph, and a character-level fidelity check refuses to produce a document whose plain + deleted text differs from the source.
- Chunk-seam de-duplication: consecutive vector chunks share an overlap run; contract analysis no longer sees (or quotes, or redlines) that run twice.
- Citation check ("Shepardize") no longer reports a case as good law after finding negative treatment language. The verdict is tri-state (`is_good_law: true | null`, never `false`), the most-cited citing opinions are scanned alongside the most recent, bare "rejected"/"erroneous" no longer count as negative, "overruled on other grounds" is a caution, and the not-a-citator caveat is shown with the badge. The tool is now labelled "Citation Check".
- Settings save failures are surfaced (toast + rollback) instead of closing the modal as if saved; wrong-password and other credential-endpoint 401s show the server's message instead of triggering a token refresh.
- The sidebar and Sources panel are reachable again on tablets and narrow windows: the responsive stylesheet is now wired to header toggles (with backdrop, Escape, and route-change close) instead of hiding both drawers with no way back.
- Contract review no longer rewrites span-less risk findings ("uncapped liability") as "Addressed" — only absence-type findings are put to the model for absence verification; risks keep their severity and are labelled unverified.
- Long-draft reconcile is checked before it is accepted: a `finish_reason` of `length` on any section or the reconcile pass is treated as a failure, every planned section heading must survive, and each section must stay within ±15% of its drafted length; otherwise the assembled sections are kept and the note names the section that failed.
- Dev/test SQLite no longer shares one connection across every session (`StaticPool`): a session's rollback could discard another session's uncommitted write, which is what made seed-then-request tests flaky.
- Operator runbooks work against the shipped stack: `scripts/backup_database.sh` runs on the host (the image never had `pg_dump` or the script), dumps Postgres through the bundled container and archives the `/app/data` volume in the same run; `scripts/restore_database.sh` decrypts `.enc` backups, quotes identifiers, restores the volume with `--data`, and stops/starts the backend around the restore. `docs/secret-rotation.md` is rewritten for the real stack (`casecite` role, derived `DATABASE_URL`/`REDIS_URL`, `up -d` instead of `restart`, a warning that rotating `SECRET_KEY` makes stored documents unreadable), and `--re-encrypt` is now real: `python -m app.utils.reencrypt` rewrites the BYOK key store, connector credentials, TOTP secrets and instance secrets under a rotated `ENCRYPTION_SALT`.
- `docker-compose.prod.yml` runs `CASECITE_IMAGE:CASECITE_TAG` (default: the GHCR image CI publishes) and the frontend is copied out of that same image, so `pull` + `up -d` deploys and `CASECITE_TAG=<sha> … up -d` rolls back; the VPS deploy example pins each deploy to the commit SHA and no longer forwards `GITHUB_TOKEN` into a remote shell. The bundled Redis healthcheck authenticates (an unauthenticated `ping` returned NOAUTH and passed); `git` is no longer installed in the runtime image.

### Security
- Deleting a user now also removes their connector OAuth credential files (revoking Google and Dropbox tokens best-effort first) and their per-user settings file; previously a departed employee's Google Drive refresh token stayed on disk and usable.
- The app refuses to start with more than one uvicorn worker regardless of vector backend — the session store, document registry and connector caches are process-local and two workers silently corrupt them. `docs/deployment.md` says so plainly; Pinecone alone does not lift it.
- `TRUSTED_PROXIES` is required in the root `docker-compose.yml` (the Coolify/Traefik variant); defaulting it collapsed every client to the proxy's IP, so one user's failed logins locked out the whole firm.
- Bespoke Serif (a Fontshare font whose license forbids redistribution) is replaced by Source Serif 4 (OFL) from the Google Fonts import the app already made.
- Validation errors no longer log the request body; submitted passwords and BYOK API keys stayed out of the container log stream only by luck before.
- `start.sh` no longer `chmod -R 755`s the data directory on every boot, which re-opened every 0600 secret file (instance secrets, BYOK key store, sessions, revoked tokens, audit logs, connector credentials).
- Audit entries are HMAC-signed over their full stored form (v2; v1 entries still verify), startup recomputes every recent signature instead of only checking linkage, and `AUDIT_HMAC_KEY_PREVIOUS` keeps a rotated key valid until the entries signed under it age out.
- Azure AD SSO mints tokens from the local account's roles rather than a hardcoded `attorney`; first-time SSO users get `AZURE_SSO_DEFAULT_ROLE` (viewer) or are refused when `AZURE_SSO_AUTO_PROVISION=false`; an admin-invited row is adopted by email.
- Logout resets every in-memory store (research, contracts, drafts, judge intel, documents, keys), and the login password is cleared from state after sign-in.

### Changed
- Every modal uses a shared accessible dialog shell (`role="dialog"`, `aria-modal`, focus trap, Escape/backdrop close); form controls carry labels; icon-only buttons and clickable rows are keyboard-reachable and named.
- Module docstrings and the OpenAPI description no longer describe the product as "SOC 2 compliant"; controls are described as what they are.

### Removed
- **`DEMO_MODE`.** One env var used to disable secret/Redis/DB/disk-encryption validation, set `ALLOWED_HOSTS=*`, relax CSP and drop HSTS, mute the audit halt-on-tamper, allow anonymous access to research tools, open registration, and carry SaaS-era daily query limits ("Contact us for full access"). Local development is now `DEBUG=true` alone; production semantics are unchanged. Removed with it: `DEMO_DAILY_QUERY_LIMIT`, `DEMO_MAX_DOCUMENTS`, `DEMO_ACCOUNT_EMAIL`, `SALES_EMAIL`, the `X-Demo-Limit-*` headers, anonymous tool access (`require_permission_optional`), the public `GET /api/v1/config`, `docker-compose.demo.yml` and `.env.demo`. `/auth/demo/login` remains as a `DEBUG`-only dev login for `dev@localhost`. **Upgrading:** the removed keys are ignored with a startup warning if they are still in `.env` — delete them.
- Dead API surface with no caller: connector `upload_file` (four `NotImplementedError` stubs and four never-called implementations) and the `POST /connectors/{type}/upload` / `GET /connectors/{type}/files` routes; `DELETE /documents/all`, `GET /documents/stats`, `POST /documents/batch`; `POST /jobs/{id}/retry`; `DELETE /user/keys/delete` and `/delete-all`; the public `/clause-intel` router (the clause-intelligence service remains, used internally by contract analysis); `EncryptionService.re_encrypt()`.
- Frontend: 61 unused `default` exports, dead barrel re-exports, and the `export` keyword on 28 types nothing imported (knip: unused exports 73 → 0).
- Repo: `backend/pytest.ini` (folded into `pyproject.toml`), `deploy/DEPLOYMENT-GUIDE.md` and `deploy/DEPLOYMENT.md` (merged into `docs/deployment.md`), the Cloud Run deploy example (ADR-004 rules serverless out), `docs/screenshots/.gitkeep`, and the `para.db` pre-rename database fallback — rename `backend/data/para.db` to `casecite.db` on a dev machine that still has one.
- ~14,000 lines of code from removed products that were still compiled, seeded, and migrated: the `document_db` SQLite seeder package (templates, clause library, deadlines, workflows, discovery, Bates, e-filing — replaced by a static court list), the server-side judge brief / analytics / comparison endpoints the UI never called, 59 orphaned request schemas, 9 never-read database tables (dropped by migration 012), 15 response models for endpoints that did not exist, the dev-only debug endpoints, the unused half of `resilience.py`, the never-mounted session-timeout hook, and unused frontend types, barrels, and store actions.

## [1.1.0] - 2026-08-24

### Added
- Matter-based sharing model: the matter is the unit of access control, with a full Matter API (creation, membership, document scoping)
- Hybrid search: semantic + BM25 keyword retrieval with cross-encoder reranking
- Judge intelligence: judge profiles, briefs, and side-by-side comparisons backed by CourtListener data
- Contracts analysis rebuilt around user-supplied instructions and playbooks
- Conversation export as Word, PDF, or Markdown from the chat dock
- Expanded CourtListener tools: citation validation with real treatment analysis, dockets, oral arguments, and full opinion retrieval
- Standalone strategy-brief, clause-intelligence, matters, and admin-audit APIs (backend-complete; UI in progress)

### Changed
- Security hardening: upload size/type limits enforced with magic-byte validation, tools endpoints gated behind authentication, CSRF protection always on
- Documentation refreshed for the self-hosted release (deployment, backup, TLS-on-internal-networks guidance)

### Removed
- SaaS/billing-era code removed for the self-hosted source-available release (document-intelligence router, analysis storage, billing enums, frontend feature gating)

## [1.0.0] - 2026-02-22

### Added
- Multi-tenant data isolation (user_id scoping across documents, vectors, settings)
- Tenant context middleware for automatic user scoping
- Per-user RAG settings (database-backed, replacing global singleton)
- Per-user file upload directories (`uploads/{user_id}/`)
- Comprehensive test suite: tenant isolation, RAG intent, citations, prompts
- Vite + React TypeScript frontend with modular API client and CSS Modules
- Code-split views via React.lazy() with Suspense loading
- Extracted React components: Icon, CitationModal, ExportModal, DocumentPanel, DocumentSelector, RAGSettingsModal, CaseComparisonModal
- Multi-stage Dockerfile (Node frontend build + Python runtime)
- pyproject.toml with ruff, pytest, mypy configuration
- White-label support: all branding/emails configurable via environment variables
- Redis required for production deployments
- CONTRIBUTING.md, SECURITY.md, CHANGELOG.md, CODE_OF_CONDUCT.md
- Elastic License 2.0 (ELv2)

### Changed
- Split monolithic `rag.py` (1261 lines) into modular package: service, search, generation, citations, intent, prompts
- Updated Docker build context from `./backend` to `.` (root Dockerfile)
- CI pipeline: fixed build context, added 70% coverage gate
- Production startup: Alembic migrations instead of `create_all`
- Docker Compose dev: single service with hot-reload, removed separate frontend container
- Docker Compose prod: frontend built assets served via volume, updated resource limits
- Health endpoint always returns HTTP 200 (prevents container restart loops)
- Frontend uses import.meta.env.DEV for environment detection
- MFA recovery codes upgraded to HMAC-SHA256 (legacy SHA-256 fallback deprecated)

### Fixed
- Graceful service initialization (ChromaDB, RAG service handle failures without crash)
- Health endpoints handle None vector DB service
- ChromaDB lock file cleanup on startup
- Start script permission fixing for Coolify compatibility
- Resolved 17 npm audit vulnerabilities (ESLint dependency chain)

### Removed
- Monolithic `rag.py` replaced by `services/rag/` package
- In-browser Babel transpilation (replaced by Vite build)
- Global RAG settings singleton (replaced by per-user settings)
