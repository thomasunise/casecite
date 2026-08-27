# ADR-003: Authentication and Session Model

**Status:** Accepted
**Date:** 2025-01-15
**Decision makers:** Core maintainers

## Context

CaseCite handles privileged legal documents under attorney-client confidentiality. The authentication system must support both direct email/password login and enterprise SSO (Azure AD), provide granular token revocation for SOC 2 compliance, and work across single-instance and distributed deployments.

The main options considered:

1. **Session-only (server-side sessions in Redis)** — Traditional session cookie approach
2. **Stateless JWT (no revocation)** — Pure stateless tokens with short expiry
3. **JWT with JTI revocation + session management** — Tokens with per-token revocation tracking
4. **OAuth 2.0 Authorization Code Flow** — Full OAuth server implementation
5. **Delegated auth (Auth0/Clerk)** — Third-party authentication service

## Decision

We chose **JWT (HS256) with JTI-based revocation and layered session management** (option 3).

### Token architecture

- **Access tokens**: HS256, 60-minute expiry, contain `user_id`, `email`, `roles`, unique `jti`
- **Refresh tokens**: HS256, 7-day expiry, scoped to `/api/v1/auth/refresh` path only
- **Delivery**: httpOnly cookies (`secure=true` in production, `samesite=strict`) with CSRF double-submit cookie protection
- **CSRF tokens**: HMAC-signed, readable by JavaScript (`httponly=false`), `samesite=lax` to allow OAuth redirects

### Revocation mechanism

Token revocation uses a three-layer approach for reliability:

1. **In-memory set** — Instant revocation, zero latency, lost on process restart
2. **File-based journal** — `data/revoked_tokens.jsonl`, loaded on startup, survives single-instance crashes
3. **Redis** — Distributed across multiple app instances, 7-day TTL matching max token lifetime

Revocation writes to all three layers simultaneously. Verification checks Redis first (distributed), falls back to in-memory if Redis is unavailable.

### Azure AD SSO

Enterprise SSO uses Azure AD token verification, not a full OAuth Authorization Code flow:

1. Frontend redirects to Azure AD login (configured via `/auth/azure/config`)
2. Azure issues a token directly to the frontend
3. Frontend sends the Azure token to `/auth/azure/login`
4. Backend verifies the Azure JWT using Microsoft's JWKS (RS256, 1-hour key cache)
5. Backend creates or updates the local user record
6. Backend issues local JWT tokens (HS256) for subsequent API calls

Azure tenant validation is strict: if `MICROSOFT_CLIENT_ID` is set without `MICROSOFT_TENANT_ID`, SSO is disabled entirely to prevent authentication bypass via the "common" tenant.

### RBAC

Four flat roles: `admin`, `attorney`, `paralegal`, `viewer`. Stored as a JSON list in the `users.roles` column and included in JWT claims. Enforcement via `require_roles()` dependency:

```python
@router.get("/admin-endpoint")
async def admin_only(user: TokenData = Depends(require_roles(UserRole.ADMIN))):
    ...
```

Multiple roles use OR logic — user needs any one of the listed roles.

### Session management

- Max 5 concurrent sessions per user (oldest evicted when exceeded)
- 8-hour session timeout
- Optional IP binding (`ENFORCE_SESSION_IP_BINDING`, default true)
- Session state stored in Redis (primary), file-based JSONL (fallback), or in-memory (dev)

### Account lockout

- 5 failed login attempts within 15 minutes triggers lockout
- Exponential backoff: 15m → 30m → 1h → 2h → 4h (max)
- Cleared on successful login

## Consequences

### Positive

- **SOC 2 compliant revocation.** Every token has a unique JTI that can be individually revoked. Audit logs track all authentication events with correlation IDs. Revocation survives process restarts via file + Redis persistence.
- **Works without Redis.** Single-instance deployments (dev, Coolify) function with in-memory + file-based revocation. Redis is recommended but not required.
- **Enterprise SSO without OAuth complexity.** Azure AD token verification is simpler than implementing a full Authorization Code Flow with state management, PKCE, and callback handling. The local JWT approach means all subsequent API calls use the same auth path regardless of login method.
- **Defense-in-depth.** Five layers protect API endpoints: rate limiting → account lockout → CSRF verification → JWT signature verification → session validation → RBAC check → subscription check.
- **XSS-resistant token delivery.** httpOnly cookies prevent JavaScript from reading tokens. CSRF protection via double-submit cookies prevents cross-site request forgery.

### Negative

- **HS256 symmetric key.** All backend instances share the same signing key. A compromised key allows token forgery. RS256 (asymmetric) would limit exposure to the signing service, but adds key management complexity disproportionate to current deployment size.
- **In-memory revocation gaps.** If Redis is down and the process crashes, revoked tokens in the in-memory set are lost. The file-based journal mitigates this but has a small write-to-disk window.
- **No fine-grained permissions.** Four flat roles without resource-level ACLs. An `attorney` can access all their own data but cannot selectively share with a specific `paralegal`. Adding per-resource permissions would require an authorization table and policy engine.
- **Session IP binding breaks mobile.** Users on cellular networks with dynamic IP addresses may experience session invalidation. The setting is configurable but defaults to on, which could cause support issues for mobile users.

### Alternatives rejected

- **Session-only (no JWT)**: Requires a shared session store for every request. Does not work well with SPA clients that need offline-capable token refresh. Redis dependency becomes mandatory rather than optional.
- **Stateless JWT (no revocation)**: Cannot comply with SOC 2 requirements for immediate access revocation on logout, password reset, or account compromise. Waiting for token expiry (up to 60 minutes) is unacceptable for a legal platform.
- **Full OAuth 2.0 server**: Unnecessary complexity for a single-application platform. CaseCite is not an identity provider — it has one client (the SPA). Authorization Code Flow with PKCE adds state management, callback endpoints, and token exchange that provides no benefit over direct Azure AD token verification.
- **Delegated auth (Auth0/Clerk)**: Introduces external dependency and per-MAU costs. Legal firms may have compliance concerns about routing authentication through third-party services. Self-hosted auth provides full control over the authentication chain.
