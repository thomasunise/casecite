# Incident Response Plan

This plan covers security incidents affecting a CaseCite deployment, including
suspected exposure of attorney–client privileged data. Self-hosting firms should
adapt contacts and timelines to their own obligations. (SOC 2 CC7.3–CC7.5.)

## 1. Severity levels

| Sev | Definition | Examples | Target ack |
|-----|------------|----------|------------|
| **SEV-1** | Confirmed or likely exposure of client data; auth bypass; RCE | Cross-tenant data read, leaked credentials, DB exfiltration | 1 hour |
| **SEV-2** | Security control failure without confirmed data exposure | Broken authz on an endpoint, disabled audit log, dependency RCE with no evidence of use | 4 hours |
| **SEV-3** | Degraded control / policy violation | Missing security header, non-blocking misconfig, phishing attempt | 1 business day |

## 2. Roles

- **Incident Commander (IC):** owns the response, decisions, and comms. (Default: the deployment's security owner — see `CODEOWNERS`.)
- **Scribe:** maintains the timeline (UTC timestamps, actions, evidence).
- **Comms lead:** handles internal and client/regulator notification.

## 3. Response workflow

1. **Detect & report.** Anyone who suspects an incident notifies the IC via the
   channel below. Sources: audit-log alerts (`security.*` events), monitoring,
   user reports, the vulnerability disclosure inbox in `SECURITY.md`.
2. **Triage & classify.** IC assigns a severity and opens an incident record.
3. **Contain.** Cut off access: revoke sessions/tokens (`/auth/logout/all`, deactivate
   users via `PATCH /admin/users/{id}/active`), rotate secrets
   (`docs/secret-rotation.md`), block network paths, take a forensic snapshot of the
   `data/` volume and audit logs **before** remediation.
4. **Eradicate & recover.** Patch the root cause, restore from known-good backups
   if needed (`scripts/restore_database.sh`), verify integrity of the audit chain
   (`AUDIT_HALT_ON_TAMPERING`).
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
- Record what data, whose data, the window of exposure (use `DOCUMENT_VIEW` /
  `DATA_EXPORT` / auth audit events to scope access), and remediation.

## 5. Contacts

Configure these for your deployment:

- Security / IC contact: `SECURITY_EMAIL` (see `SECURITY.md`).
- Escalation / on-call: _fill in_.
- Legal / GC: _fill in_.

## 6. Evidence sources

- Audit trail: `data/audit_logs/*.jsonl` (HMAC-chained, tamper-evident).
- Application logs (JSON, correlated by `X-Request-ID`).
- Database backups: `scripts/backup_database.sh` output.
- `data/` volume snapshot.
