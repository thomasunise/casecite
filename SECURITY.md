# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest  | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do not** open a public GitHub issue
2. Email the address specified in `SECURITY_EMAIL` (default: **security@casecite.com**) with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)
3. You will receive an acknowledgment within 48 hours
4. We will work with you to understand and address the issue before any public disclosure

## Security Architecture

### Authentication
- JWT tokens with HS256 signing (60-minute expiry)
- Azure AD SSO with RS256 JWKS validation
- Token revocation via JTI tracking (Redis primary, in-memory fallback)
- Session management: max 5 concurrent sessions per user, 8-hour timeout

### Data Protection
- AES-256-GCM encryption at rest for stored API keys
- PBKDF2 key derivation with 100,000 iterations; per-record keys separated via HKDF
- Per-user tenant isolation across all data stores
- BYOK keys are persisted server-side, AES-256-GCM-encrypted, in a file store on
  the data volume (`backend/app/services/key_storage.py`). They are displayed to
  users only in masked form and are never returned to the client; the backend
  decrypts them on demand per request

### Web Security
- CSRF protection via double-submit cookies with HMAC signatures
- Content Security Policy (CSP) headers
- HSTS with 1-year max-age
- X-Frame-Options, X-Content-Type-Options, Permissions-Policy

### Rate Limiting
- Default: 100 requests/minute
- Chat: 20 requests/minute
- Login: 3 attempts per 5 minutes
- Signup: 2 per hour

### Abuse Prevention
- Brute force detection in audit logs
- Login attempt lockout and signup throttling

### Deployment Recommendations
- Set `REGISTRATION_BOOTSTRAP_TOKEN` before first boot on any network-reachable
  install: the first account to register becomes the admin, and the token stops
  an attacker who finds a fresh instance from seizing that slot
- Keep `ALLOW_REGISTRATION=false` (the default) unless the instance runs on a
  trusted network

### Audit Trail
- 79 event types with SHA-256 chain hashing
- JSONL daily rotation
- SOC 2-style controls (self-hosted; no certification implied)

## Dependencies

We pin all Python dependencies to exact versions. Security updates are applied promptly.
