# ADR-003: Authentication and Session Model

**Status:** Accepted — revised 2026-10-04 to match the code as shipped
**Date:** Recorded 2026-05-03 (the decision predates the record)
**Decision makers:** Core maintainers

> **Revision note (2026-10-04).** Several statements in the original no longer matched the code: Redis is required in production, sessions are not stored in Redis, IP binding is off by default, authorization uses `require_permission` rather than `require_roles`, and there is no subscription check. "SOC 2 compliant" wording was removed — the project holds no certification. The text below describes the current behaviour.

## Context

CaseCite handles privileged legal documents under attorney-client confidentiality. The authentication system must support both direct email/password login and enterprise SSO (Azure AD) and provide immediate, granular token revocation.

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
- **Refresh tokens**: HS256, rotated on every use, scoped to the `/api/v1/auth/refresh` path, and bound to the session they were issued for — a refresh continues that session and cannot outlive its absolute lifetime
- **Delivery**: httpOnly cookies (`secure=true` in production, `samesite=strict`) with CSRF double-submit cookie protection
- **CSRF tokens**: HMAC-signed, readable by JavaScript (`httponly=false`), `samesite=lax` to allow OAuth redirects

### Revocation mechanism

Individual tokens are revoked by JTI. In production Redis is required and is the store of record for revoked JTIs (with a TTL matching the token lifetime); the in-memory set and the `revoked_tokens.jsonl` journal exist for development without Redis. Redis must therefore not evict keys: the bundled stack runs it with `maxmemory-policy noeviction`.

Account-wide invalidation does not depend on Redis: each user row carries a token version that is embedded in every token. "Sign out everywhere", password change, password reset, role change, deactivation and an admin MFA reset bump it, which invalidates every outstanding access and refresh token for that account.

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

Four roles: `admin`, `attorney`, `paralegal`, `viewer`. Stored as a JSON list in the `users.roles` column and included in JWT claims. Roles map to named permissions (`services/permissions.py`), which an admin can adjust per role; endpoints declare the permission they need:

```python
@router.get("/admin/users")
async def list_users(current_user: TokenData = require_permission("admin.users")):
    ...
```

A user holding several roles has the union of their permissions. Roles always come from the local user record, never from an identity-provider token.

### Session management

- Max 5 concurrent sessions per user (oldest sign-in evicted when exceeded)
- 8-hour absolute lifetime (`SESSION_ABSOLUTE_TIMEOUT_HOURS`); refreshing a token does not extend it
- 2-hour idle timeout (`SESSION_IDLE_TIMEOUT_MINUTES`, 0 disables)
- Optional IP binding (`ENFORCE_SESSION_IP_BINDING`, default **false** — it breaks users on mobile networks)
- Session state is held in the backend process and mirrored to `sessions.jsonl` on the data volume so it survives a restart. It is not in Redis, which is one reason the app runs as a single process

### Account lockout

- 5 failed login attempts within 15 minutes triggers lockout
- Exponential backoff: 15m → 30m → 1h → 2h → 4h (max)
- Cleared on successful login

## Consequences

### Positive

- **Immediate revocation.** Every token has a unique JTI that can be individually revoked, and an account's tokens can be invalidated as a whole. Audit logs track authentication events with correlation IDs.
- **Development works without Redis.** With `DEBUG=true` the app falls back to in-memory + file-based revocation. Production (`DEBUG=false`) requires `REDIS_URL` and refuses to start without it.
- **Enterprise SSO without OAuth complexity.** Azure AD token verification is simpler than implementing a full Authorization Code Flow with state management, PKCE, and callback handling. The local JWT approach means all subsequent API calls use the same auth path regardless of login method.
- **Defense-in-depth.** API endpoints sit behind rate limiting → account lockout → CSRF verification → JWT signature verification → session validation → permission check.
- **XSS-resistant token delivery.** httpOnly cookies prevent JavaScript from reading tokens. CSRF protection via double-submit cookies prevents cross-site request forgery.

### Negative

- **HS256 symmetric key.** All backend instances share the same signing key. A compromised key allows token forgery. RS256 (asymmetric) would limit exposure to the signing service, but adds key management complexity disproportionate to current deployment size.
- **Revocation depends on Redis durability.** A Redis that loses data (eviction, or a restart without persistence) forgets individually revoked JTIs. The token-version check covers account-wide invalidation, and access tokens expire within the hour, but single-token revocation is only as durable as Redis.
- **No resource-level ACLs.** Permissions are per role, not per document. Sharing is by matter membership only (ADR-001).
- **Azure AD only.** SSO is a backend token exchange for Azure AD; there is no SAML, generic OIDC or SCIM, and MFA for SSO accounts is the identity provider's responsibility.
- **Session IP binding breaks mobile.** Users on cellular networks with dynamic IP addresses would be signed out, which is why it is off by default.

### Alternatives rejected

- **Session-only (no JWT)**: Requires a shared session store for every request and does not work well with SPA clients that need silent token refresh.
- **Stateless JWT (no revocation)**: Cannot revoke access immediately on logout, password reset, or account compromise. Waiting for token expiry (up to 60 minutes) is unacceptable for a legal platform.
- **Full OAuth 2.0 server**: Unnecessary complexity for a single-application platform. CaseCite is not an identity provider — it has one client (the SPA). Authorization Code Flow with PKCE adds state management, callback endpoints, and token exchange that provides no benefit over direct Azure AD token verification.
- **Delegated auth (Auth0/Clerk)**: Introduces external dependency and per-MAU costs. Legal firms may have compliance concerns about routing authentication through third-party services. Self-hosted auth provides full control over the authentication chain.
