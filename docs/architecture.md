# Architecture Overview

## System Design

CaseCite follows a layered architecture with strict separation of concerns:

```
┌─────────────────────────────────────────────────┐
│                  React SPA                       │
│  Views → Hooks → API Client → AppContext         │
├─────────────────────────────────────────────────┤
│              Reverse Proxy (Caddy/nginx)          │
├─────────────────────────────────────────────────┤
│            Middleware Stack (5 layers)            │
│  CORS → Security → TrustedHost → CSRF            │
├─────────────────────────────────────────────────┤
│        FastAPI Routers (24 domain routers)        │
│  HTTP concerns only: auth, validation, response   │
├─────────────────────────────────────────────────┤
│              Services (114 modules)                │
│  Business logic, AI orchestration, integrations   │
├─────────────────────────────────────────────────┤
│              Data Layer                           │
│  PostgreSQL │ ChromaDB/Pinecone │ Redis │ Files   │
└─────────────────────────────────────────────────┘
```

## Frontend Architecture

### Data Flow

```
User Interaction
  → View (pure rendering, destructures from AppContext)
  → Hook (state + handlers, calls API layer)
  → API Client (HTTP requests with CSRF + BYOK headers)
  → Backend
```

### Key Patterns

- **Views** are pure rendering functions. They destructure state from `useApp()` and return JSX. No business logic.
- **Hooks** (`useXxxState`) own all state and handlers for a feature. One hook per feature/view.
- **Stores** (Zustand) hold truly global state that persists across navigation: auth, UI, settings.
- **AppContext** merges all hook/store state into a single context value distributed to all views.
- **Components** are reusable UI pieces. They receive parent CSS modules via an `s` prop.
- **API modules** are organized one-per-domain and attach methods to a singleton `api` object.

### Directory Map

| Directory | Purpose | Count |
|-----------|---------|-------|
| `views/` | Page-level components (one per tab) | 8 |
| `hooks/` | State hooks (one per feature) | 5 |
| `stores/` | Zustand global stores | 17 |
| `components/shared/` | Reusable UI components | 44 |
| `components/modals/` | Modal dialogs | 11 |
| `api/` | Backend API client modules | 16 |
| `layout/` | App shell (header, sidebar, footer) | 7 |

## Backend Architecture

### Request Lifecycle

```
HTTP Request
  → Middleware Stack (rate limit, CSRF, security headers)
  → Router (auth check, input validation, HTTP concerns)
  → Service (business logic, AI calls, DB operations)
  → Database / Vector DB / External API
  → Response
```

### Key Patterns

- **Routers** are thin. They handle auth (`Depends(get_current_user)`), validate input (Pydantic), call a service, and return a response. No business logic.
- **Services** contain all business logic. They never import routers or HTTP constructs.
- **Route ordering**: Literal paths are always defined before parameterized catch-alls to prevent shadowing.
- **Error handling**: Specific exceptions only (never bare `except:`). HTTPException for client errors.
- **Async throughout**: All database operations, external API calls, and I/O use `async/await`.

### Service Organization

Complex domains use subdomain packages:

```
services/
  rag/                    # RAG pipeline (6 modules)
    service.py            # Orchestrator
    search.py             # Hybrid semantic + BM25
    generation.py         # LLM response generation
    citations.py          # Citation extraction
    intent.py             # Query classification
    prompts.py            # Prompt templates
  pleading_paper/         # Pleading generation (8 modules)
  judge_intel/            # Judge intelligence (2 modules)
  auth.py                 # JWT + Azure AD SSO
  audit.py                # Tamper-evident audit trail
  encryption.py           # AES-256-GCM at rest
  ...                     # 114 total modules
```

## Security Architecture

### Middleware Stack (processed top to bottom)

1. **CORSMiddleware** — Origin validation, credential support
2. **SecurityMiddleware** — Rate limiting, security headers (CSP, HSTS), IP blocking
3. **TrustedHostMiddleware** — Host header validation
4. **CSRFMiddleware** — Double-submit cookie with HMAC signatures

### Authentication

- **JWT** (HS256, 60-minute access tokens) with JTI-based revocation via Redis
- **Azure AD SSO** with RS256 JWKS validation and 1-hour cache
- **RBAC**: admin, attorney, paralegal, viewer roles
- **Session management**: max 5 concurrent sessions per user, 8-hour timeout

### Data Protection

- AES-256-GCM encryption at rest for sensitive fields (PBKDF2, 100K iterations)
- Tenant isolation: all queries scoped by `user_id`
- File upload validation with magic bytes (not just extensions)

### Audit Trail

- 79 event types across AUTH, DOCUMENT, RAG, ADMIN, SECURITY, COMPLIANCE, HIPAA categories
- SHA-256 chain hashing for tamper detection
- JSONL format with daily rotation
- Correlation IDs for request tracking

## Database Schema

22 tables across the primary database (PostgreSQL in production). The court
list used by jurisdiction pickers is a static module (`services/courts.py`):

| Domain | Tables |
|--------|--------|
| Auth | users, instance_secrets |
| Matters | matters, matter_members |
| Chat & workspace | chat_sessions, chat_messages, workspace_sessions |
| Contract intelligence | contract_analysis_runs, contract_parties, contract_obligations, contract_deadlines, contract_defined_terms, contract_type_requirements |
| Clause intelligence | clause_canonicals, clause_deviations, clause_jurisdiction_rules, clause_tag_findings |
| Authority mapping | authority_map_runs, authority_mappings |
| Tracking | branding_config |
| Audit | audit_logs |

## AI Pipeline (RAG)

```
User Query
  → Intent Detection (FACTUAL vs ANALYTICAL, 70+ regex patterns)
  → Hybrid Search (semantic embeddings + BM25 keyword)
  → Reranking (Cohere or cross-encoder)
  → Context Assembly (with source metadata)
  → LLM Generation (OpenAI/Anthropic/Gemini via BYOK)
  → Citation Extraction + Validation
  → Response with provenance chain
```

### Embedding Providers

| Provider | Model | Dimensions | Use Case |
|----------|-------|------------|----------|
| OpenAI | text-embedding-3-small | 1536 | General purpose |
| Voyage AI | voyage-law-2 | 1024 | Legal-specific (recommended) |
| Cohere | embed-english-v3.0 | 1024 | Multilingual support |
