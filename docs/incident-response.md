# Incident Response Plan

This plan covers security incidents affecting a CaseCite deployment, including
suspected exposure of attorney–client privileged data. It is a template: the
firm operating the deployment owns the plan and must fill in its own contacts,
timelines and notification obligations before it is needed.

## 1. Severity levels

| Sev | Definition | Examples | Target ack |
|-----|------------|----------|------------|
| **SEV-1** | Confirmed or likely exposure of client data; auth bypass; RCE | Cross-tenant data read, leaked credentials, DB exfiltration | 1 hour |
| **SEV-2** | Security control failure without confirmed data exposure | Broken authz on an endpoint, disabled audit log, dependency RCE with no evidence of use | 4 hours |
| **SEV-3** | Degraded control / policy violation | Missing security header, non-blocking misconfig, phishing attempt | 1 business day |

## 2. Roles

- **Incident Commander (IC):** owns the response, decisions, and comms. This is a person at the firm operating the deployment (its security owner or IT lead) — name them in §5.
- **Scribe:** maintains the timeline (UTC timestamps, actions, evidence).
- **Comms lead:** handles internal and client/regulator notification.

## 3. Response workflow

1. **Detect & report.** Anyone who suspects an incident notifies the IC via the
   channel below. Sources: `security.*` events in the audit log (Settings →
   Audit log, or `GET /api/v1/admin/audit/logs`), host and proxy monitoring,
   user reports. The application does not send alerts itself; forward the audit
   log and application logs to your monitoring if you need paging.
2. **Triage & classify.** IC assigns a severity and opens an incident record.
3. **Contain.** Cut off access, then preserve evidence:
   - **One account:** an admin deactivates it (Settings → Users, or
     `PATCH /api/v1/admin/users/{id}/active`). Deactivation ends every session
     and invalidates every access and refresh token for that account.
   - **A user's own sessions:** "Sign out everywhere" (`POST /api/v1/auth/logout/all`)
     does the same for the signed-in user.
   - **Everyone:** recreating Redis and restarting the backend ends all
     sessions; rotating `SECRET_KEY` also invalidates every token but makes
     stored documents unreadable — read `docs/secret-rotation.md` first.
   - Rotate any exposed provider keys and connector credentials
     (`docs/secret-rotation.md`), block network paths, and take a snapshot of
     the data volume, the database and the audit logs **before** remediation.
4. **Eradicate & recover.** Patch the root cause, restore from known-good backups
   if needed (`scripts/restore_database.sh`), and verify the audit chain
   (`GET /api/v1/admin/audit/verify`, or Settings → Audit Log → Verify).
5. **Notify.** See §4.
6. **Post-incident review.** Within 5 business days: root-cause analysis, timeline,
   and corrective actions. Track fixes to closure.

## 4. Breach notification

Attorney–client data is subject to legal and ethical obligations. On a confirmed
breach of client data:

- Notify affected client(s) and the firm's General Counsel/ethics partner without
  undue delay per the firm's obligations and applicable law (e.g. state breach-
  notification statutes, GDPR Art. 33/34 where applicable — 72 hours to the
  supervisory authority).
- Preserve evidence (audit logs, snapshots) for the retention period.
- Record what data, whose data, the window of exposure, and remediation. To
  scope access, filter the audit log by user and date for sign-ins, document
  uploads, views, downloads and deletions, exports, and matter-membership
  changes. The audit log records identifiers and metadata, not document
  content; reverse-proxy access logs (Caddy: `/data/access.log`) give
  request-level detail for the same window.

## 5. Contacts

These are the operating firm's contacts, not the software project's. Replace
each placeholder before going live and review them at least yearly.

| Role | Name | Contact | Backup |
|------|------|---------|--------|
| Incident Commander / security owner | `<name>` | `<phone / email>` | `<name>` |
| On-call for the host and network | `<name>` | `<phone / email>` | `<name>` |
| General Counsel / ethics partner | `<name>` | `<phone / email>` | `<name>` |
| Cyber-insurance carrier / breach counsel | `<firm>` | `<hotline>` | |

A vulnerability in CaseCite itself (as opposed to an incident in your
deployment) is reported upstream as described in [SECURITY.md](../SECURITY.md).

## 6. Evidence sources

- Audit trail: `audit_logs/audit_YYYY-MM-DD.jsonl` on the data volume
  (HMAC-chained; older files are gzip-compressed, see `AUDIT_RETENTION_DAYS`).
- Reverse-proxy access log (Caddy: `/data/access.log` in the caddy container).
- Application logs (JSON, correlated by `X-Request-ID`).
- Database backups: `scripts/backup_database.sh` output.
- `data/` volume snapshot.
