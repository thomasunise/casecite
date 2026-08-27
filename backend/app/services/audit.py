"""
Audit Logging Service

Tamper-evident log of security-relevant events: each entry is HMAC-signed
over its full stored form and chained to the previous entry, written to daily
JSONL files with a best-effort database mirror.
"""

import asyncio
import hashlib
import hmac as hmac_mod
import json
import logging
import threading
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from app.config import settings


class AuditEventType(str, Enum):
    # Authentication (nosec B105 - these are event type identifiers, not passwords)
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    LOGOUT = "auth.logout"
    TOKEN_REFRESH = "auth.token.refresh"  # nosec B105
    MFA_CHALLENGE = "auth.mfa.challenge"
    MFA_SUCCESS = "auth.mfa.success"
    MFA_FAILURE = "auth.mfa.failure"
    MFA_ENABLED = "auth.mfa.enabled"
    MFA_DISABLED = "auth.mfa.disabled"
    PASSWORD_CHANGE = "auth.password.change"  # nosec B105
    PASSWORD_RESET_REQUEST = "auth.password.reset.request"  # nosec B105
    PASSWORD_RESET_COMPLETE = "auth.password.reset.complete"  # nosec B105

    # Document Access
    DOCUMENT_VIEW = "document.view"
    DOCUMENT_DOWNLOAD = "document.download"
    DOCUMENT_UPLOAD = "document.upload"
    DOCUMENT_DELETE = "document.delete"
    DOCUMENT_SEARCH = "document.search"

    # RAG/Chat
    CHAT_QUERY = "chat.query"
    CITATION_VIEW = "citation.view"
    CITATION_APPROVE = "citation.approve"
    CITATION_REJECT = "citation.reject"

    # Connectors
    CONNECTOR_CONNECT = "connector.connect"
    CONNECTOR_DISCONNECT = "connector.disconnect"
    CONNECTOR_SYNC_START = "connector.sync.start"
    CONNECTOR_SYNC_COMPLETE = "connector.sync.complete"
    CONNECTOR_SYNC_FAILURE = "connector.sync.failure"

    # Admin
    SETTINGS_VIEW = "settings.view"
    SETTINGS_CHANGE = "settings.change"
    USER_CREATE = "user.create"
    USER_UPDATE = "user.update"
    USER_DELETE = "user.delete"
    USER_ROLE_CHANGE = "user.role.change"
    USER_DEACTIVATE = "user.deactivate"

    # API Keys
    API_KEY_CREATED = "apikey.created"
    API_KEY_DELETED = "apikey.deleted"
    API_KEY_USED = "apikey.used"

    # Security Events
    ACCESS_DENIED = "security.access.denied"
    RATE_LIMIT_EXCEEDED = "security.ratelimit.exceeded"
    SUSPICIOUS_ACTIVITY = "security.suspicious"
    DATA_EXPORT = "security.data.export"
    SECURITY_ALERT = "security.alert"
    BRUTE_FORCE_DETECTED = "security.bruteforce"
    UNAUTHORIZED_ACCESS_ATTEMPT = "security.unauthorized"
    CSRF_VIOLATION = "security.csrf.violation"
    SESSION_HIJACK_ATTEMPT = "security.session.hijack"

    # Compliance
    AUDIT_LOG_ACCESS = "compliance.audit.access"
    DATA_ACCESS = "compliance.data.access"
    DATA_MODIFICATION = "compliance.data.modification"
    DATA_DELETION = "compliance.data.deletion"
    CONSENT_GRANTED = "compliance.consent.granted"
    CONSENT_REVOKED = "compliance.consent.revoked"

    # HIPAA Events
    PHI_ACCESS = "hipaa.phi.access"
    PHI_MODIFICATION = "hipaa.phi.modification"
    PHI_EXPORT = "hipaa.phi.export"
    CONSENT_CHANGE = "hipaa.consent.change"
    BREACH_SUSPECTED = "hipaa.breach.suspected"
    BREACH_CONFIRMED = "hipaa.breach.confirmed"
    DATA_RETENTION_VIOLATION = "hipaa.retention.violation"


class AuditLog:
    """Structured audit log entry with correlation ID and chain hashing for tamper detection."""

    # Class-level chain for tamper detection
    _last_hash: str | None = None
    _chain_lock = threading.Lock()
    # asyncio lock for coroutine-safe chain updates (used by AuditService.log)
    _async_chain_lock = asyncio.Lock()

    # HMAC key for signing log entries (derived from app secret)
    _hmac_key: bytes = (settings.audit_hmac_key or settings.secret_key).encode()[:32]
    # Previous key, if the operator rotated AUDIT_HMAC_KEY: entries written
    # under it still verify, so rotation doesn't read as tampering at startup.
    _hmac_key_previous: bytes | None = (
        settings.audit_hmac_key_previous.encode()[:32] if settings.audit_hmac_key_previous else None
    )

    # Hash-input format written by this build. v1 covered seven scalar fields
    # only, leaving action details, IP, user agent and error text editable
    # without breaking the chain; v2 signs the entire stored entry.
    HASH_VERSION = 2

    @classmethod
    def verification_keys(cls) -> list[bytes]:
        keys = [cls._hmac_key]
        if cls._hmac_key_previous and cls._hmac_key_previous != cls._hmac_key:
            keys.append(cls._hmac_key_previous)
        return keys

    def __init__(
        self,
        event_type: AuditEventType,
        user_id: str | None = None,
        user_email: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        action_details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        success: bool = True,
        error_message: str | None = None,
        correlation_id: str | None = None,
        request_id: str | None = None,
    ):
        self.id = str(uuid.uuid4())
        self.timestamp = datetime.now(UTC).isoformat() + "Z"
        self.event_type = event_type.value
        self.user_id = user_id
        self.user_email = user_email
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.action_details = action_details or {}
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.success = success
        self.error_message = error_message
        self.environment = "production" if not settings.debug else "development"

        # Correlation ID for request tracing across services
        self.correlation_id = correlation_id or str(uuid.uuid4())

        # Request ID for tracing within a single request
        self.request_id = request_id

        # Chain hash for tamper detection (thread-safe)
        with AuditLog._chain_lock:
            self.previous_hash = AuditLog._last_hash
            self.hash_version = AuditLog.HASH_VERSION
            self.entry_hash: str | None = None
            self.entry_hash = self._compute_hash()
            AuditLog._last_hash = self.entry_hash

    def _compute_hash(self) -> str:
        """Compute HMAC-SHA256 over the full stored entry, chained to the previous one.

        Using HMAC instead of plain SHA-256 prevents an attacker with
        filesystem access from recomputing valid hashes after tampering,
        since they would also need the application secret key. The input is
        exactly what lands on disk (see `to_dict`), so verification can be
        replayed from the JSONL files alone.
        """
        return compute_entry_hash(self.to_dict(), AuditLog._hmac_key)

    @staticmethod
    def _mask_email(email: str | None) -> str | None:
        """Mask email for audit logs: u***@example.com"""
        if not email or "@" not in email:
            return email
        local, domain = email.split("@", 1)
        return f"{local[0]}***@{domain}" if local else f"***@{domain}"

    @staticmethod
    def _mask_ip(ip: str | None) -> str | None:
        """Mask IP for audit logs: 192.168.1.*** / partial IPv6"""
        if not ip:
            return ip
        if "." in ip:
            parts = ip.split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.***"
        elif ":" in ip:
            parts = ip.split(":")
            if len(parts) > 2:
                return ":".join(parts[:3]) + ":***"
        return ip

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "correlation_id": self.correlation_id,
            "request_id": self.request_id,
            "user": {"id": self.user_id, "email": self._mask_email(self.user_email)},
            "resource": {"type": self.resource_type, "id": self.resource_id},
            "action": self.action_details,
            "context": {
                "ip_address": self._mask_ip(self.ip_address),
                "user_agent": self.user_agent,
                "environment": self.environment,
            },
            "outcome": {"success": self.success, "error": self.error_message},
            "integrity": {
                "previous_hash": self.previous_hash,
                "entry_hash": self.entry_hash,
                "hash_version": self.hash_version,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


def _canonical_payload(entry: dict[str, Any]) -> bytes:
    """Serialize everything in a stored entry except its integrity block.

    The payload is round-tripped through JSON first so the bytes hashed at
    write time are identical to the bytes recomputed from the file later
    (tuples become lists, non-string keys become strings, etc.).
    """
    payload = {k: v for k, v in entry.items() if k != "integrity"}
    normalized = json.loads(json.dumps(payload))
    return json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()


def compute_entry_hash(entry: dict[str, Any], key: bytes) -> str:
    """Recompute an entry's chain HMAC from its stored form under `key`.

    Honors the entry's own `integrity.hash_version` so legacy v1 entries keep
    verifying after an upgrade; anything without a version is treated as v1.
    """
    integrity = entry.get("integrity") or {}
    previous = integrity.get("previous_hash") or "GENESIS"
    version = integrity.get("hash_version") or 1
    if version >= 2:
        message = previous.encode() + b"\n" + _canonical_payload(entry)
    else:
        user = entry.get("user") or {}
        resource = entry.get("resource") or {}
        outcome = entry.get("outcome") or {}
        message = (
            f"{previous}:{entry.get('id')}:{entry.get('timestamp')}:{entry.get('event_type')}:"
            f"{user.get('id')}:{resource.get('id')}:{outcome.get('success')}"
        ).encode()
    return hmac_mod.new(key, message, hashlib.sha256).hexdigest()


def verify_entry_hash(entry: dict[str, Any]) -> bool:
    """True if the stored entry_hash matches a recomputation under any accepted key."""
    stored = (entry.get("integrity") or {}).get("entry_hash")
    if not isinstance(stored, str) or not stored:
        return False
    return any(
        hmac_mod.compare_digest(compute_entry_hash(entry, key), stored)
        for key in AuditLog.verification_keys()
    )


class AuditService:
    """
    Audit logging service.

    In production, this should write to:
    - Azure Monitor / Log Analytics
    - Azure Blob Storage (immutable)
    - SIEM system
    """

    def __init__(self):
        self.log_dir = Path(settings.upload_dir).parent / "audit_logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._current_log_file = None
        self._current_date = None
        self._load_last_hash()
        self._verify_chain_on_startup()

    def _load_last_hash(self):
        """Load the last chain hash from the most recent log file on startup.

        This ensures the chain is preserved across process restarts.
        """
        try:
            log_files = sorted(self.log_dir.glob("audit_*.jsonl"), reverse=True)
            for log_file in log_files:
                # Read the last line of the most recent file
                last_line = None
                with open(log_file) as f:
                    for line in f:
                        if line.strip():
                            last_line = line
                if last_line:
                    entry = json.loads(last_line)
                    last_hash = entry.get("integrity", {}).get("entry_hash")
                    if last_hash:
                        AuditLog._last_hash = last_hash
                        return
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            pass  # Start fresh chain if we can't load

    def _verify_chain_on_startup(self):
        """Verify integrity of recent audit entries on startup.

        Verifies up to 1000 entries from the most recent log files.
        """

        logger = logging.getLogger(__name__)
        try:
            log_files = sorted(self.log_dir.glob("audit_*.jsonl"), reverse=True)
            if not log_files:
                return

            entries = []
            for log_file in log_files:
                with open(log_file) as f:
                    for line in f:
                        if line.strip():
                            try:
                                entries.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
                if len(entries) >= 1000:
                    break
            entries = entries[-1000:]

            # Verify the chain: linkage between neighbours AND each entry's own
            # HMAC. Linkage alone only proves the previous_hash pointers agree;
            # recomputing the HMAC is what catches an edited entry (or a whole
            # chain rewritten by someone without the key).
            msg = None
            for i, curr_entry in enumerate(entries):
                if i > 0:
                    prev_hash = entries[i - 1].get("integrity", {}).get("entry_hash")
                    curr_prev_hash = curr_entry.get("integrity", {}).get("previous_hash")
                    if prev_hash and curr_prev_hash and prev_hash != curr_prev_hash:
                        msg = (
                            f"AUDIT CHAIN INTEGRITY BROKEN at entry {curr_entry.get('id')}. "
                            f"Expected previous_hash={prev_hash}, got {curr_prev_hash}"
                        )
                        break
                if not verify_entry_hash(curr_entry):
                    msg = (
                        f"AUDIT ENTRY HMAC MISMATCH at entry {curr_entry.get('id')}: "
                        "the stored entry does not match its signature. Either the "
                        "entry was modified after it was written, or AUDIT_HMAC_KEY "
                        "was rotated without setting AUDIT_HMAC_KEY_PREVIOUS."
                    )
                    break

            if msg is not None:
                logger.critical(msg)
                # Only halt in true production (stable HMAC key).
                # In debug (local development) the HMAC key may be
                # auto-generated, so chain breaks are expected and not a
                # sign of tampering.
                _is_production = not settings.debug
                if settings.audit_halt_on_tampering and _is_production:
                    raise RuntimeError(
                        f"FATAL: {msg} — Refusing to start. "
                        "Investigate audit log tampering before restarting. "
                        "Set AUDIT_HALT_ON_TAMPERING=false to override (not recommended)."
                    )
                return

            logger.info(f"Audit chain integrity verified ({len(entries)} entries)")
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Could not verify audit chain on startup: {e}")

    def _get_log_file(self) -> Path:
        """Get current log file, rotating daily."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if self._current_date != today:
            self._current_date = today
            self._current_log_file = self.log_dir / f"audit_{today}.jsonl"
        return self._current_log_file

    async def log(self, entry: AuditLog):
        """Write an audit log entry to both JSONL file and database.

        Uses an asyncio lock around the chain-hash update + file write to
        prevent concurrent coroutines from interleaving chain hashes.
        """
        import os
        import stat

        async with AuditLog._async_chain_lock:
            # Recompute chain hash under the async lock so concurrent
            # coroutines cannot interleave (the __init__ lock only covers
            # thread-level concurrency; this covers async concurrency).
            with AuditLog._chain_lock:
                entry.previous_hash = AuditLog._last_hash
                entry.entry_hash = entry._compute_hash()
                AuditLog._last_hash = entry.entry_hash

            log_file = self._get_log_file()

            # Append to JSONL file (one JSON object per line)
            try:
                with open(log_file, "a") as f:
                    f.write(entry.to_json() + "\n")
            except OSError as exc:
                logging.getLogger(__name__).critical(
                    "AUDIT FILE WRITE FAILED — audit entry %s lost from JSONL: %s",
                    entry.id,
                    exc,
                    exc_info=True,
                )

        # Restrict file permissions to owner only (0o600)
        try:
            os.chmod(log_file, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass  # Windows may not support chmod

        # Persist to database (best-effort — JSONL is the primary record)
        await self._persist_to_db(entry)

        # Log security events with higher priority
        if entry.event_type.startswith("security."):
            await self._handle_security_event(entry)

    async def _persist_to_db(self, entry: AuditLog):
        """Persist audit entry to database for SQL-queryable compliance reporting.

        Best-effort: failures are logged but do not block the primary JSONL write.
        """
        try:
            from datetime import datetime as dt

            from app.database import AsyncSessionLocal
            from app.models.audit import AuditLog as AuditLogDB

            async with AsyncSessionLocal() as session:
                db_entry = AuditLogDB(
                    timestamp=dt.fromisoformat(entry.timestamp.rstrip("Z")),
                    event_type=entry.event_type,
                    user_id=entry.user_id,
                    user_email=AuditLog._mask_email(entry.user_email),
                    resource_type=entry.resource_type,
                    resource_id=entry.resource_id,
                    action_details=entry.action_details,
                    ip_address=AuditLog._mask_ip(entry.ip_address),
                    user_agent=entry.user_agent,
                    success=entry.success,
                    error_message=entry.error_message,
                    environment=entry.environment,
                    entry_hash=entry.entry_hash,
                    previous_hash=entry.previous_hash,
                    correlation_id=entry.correlation_id,
                )
                session.add(db_entry)
                await session.commit()
        except (OSError, ValueError, KeyError, ImportError) as exc:
            logging.getLogger(__name__).warning(
                "Audit DB write failed (JSONL primary record is intact): %s", exc, exc_info=True
            )
        except Exception as exc:
            # Catch SQLAlchemy and other DB errors that escape the above tuple

            logging.getLogger(__name__).warning(
                "Audit DB write failed (unexpected — JSONL primary record is intact): %s",
                exc,
                exc_info=True,
            )

    async def _handle_security_event(self, entry: AuditLog):
        """Handle security-relevant events (alerts, etc.)."""

        logger = logging.getLogger("security")

        # Log security events with high priority
        log_message = (
            f"SECURITY EVENT: {entry.event_type} | "
            f"User: {entry.user_email or entry.user_id or 'unknown'} | "
            f"IP: {entry.ip_address or 'unknown'} | "
            f"Success: {entry.success} | "
            f"Details: {entry.action_details}"
        )

        if entry.success:
            logger.warning(log_message)
        else:
            logger.error(log_message)

        # Track failed login attempts for brute force detection
        if entry.event_type == AuditEventType.LOGIN_FAILURE.value:
            await self._track_failed_login(entry.ip_address, entry.user_email)

        # In production, integrate with:
        # - Azure Monitor / Log Analytics
        # - PagerDuty / Opsgenie for critical alerts
        # - Slack/Teams webhook for security notifications
        # - SIEM system (Splunk, etc.)

    async def _track_failed_login(self, ip_address: str, email: str):
        """Track failed login attempts for brute force detection."""
        # In production, use Redis for tracking
        # This is a simple in-memory implementation
        if not hasattr(self, "_failed_logins"):
            self._failed_logins = {}

        key = f"{ip_address}:{email}" if email else ip_address
        if key not in self._failed_logins:
            self._failed_logins[key] = []

        from datetime import datetime

        self._failed_logins[key].append(datetime.now(UTC))

        # Keep only last hour
        one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
        self._failed_logins[key] = [t for t in self._failed_logins[key] if t > one_hour_ago]

        # Alert on brute force (5+ failures in 1 hour)
        if len(self._failed_logins[key]) >= 5:
            await self.log_event(
                event_type=AuditEventType.BRUTE_FORCE_DETECTED,
                user_email=email,
                ip_address=ip_address,
                details={
                    "failed_attempts": len(self._failed_logins[key]),
                    "window": "1 hour",
                },
                success=False,
            )

    async def log_event(
        self,
        event_type: AuditEventType,
        user_id: str = None,
        user_email: str = None,
        resource_type: str = None,
        resource_id: str = None,
        details: dict[str, Any] = None,
        ip_address: str = None,
        user_agent: str = None,
        success: bool = True,
        error: str = None,
        correlation_id: str = None,
        request_id: str = None,
    ):
        """Convenience method to create and log an event."""
        entry = AuditLog(
            event_type=event_type,
            user_id=user_id,
            user_email=user_email,
            resource_type=resource_type,
            resource_id=resource_id,
            action_details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            error_message=error,
            correlation_id=correlation_id,
            request_id=request_id,
        )
        await self.log(entry)
        return entry.id

    async def verify_chain_integrity(self, logs: list) -> tuple[bool, str | None]:
        """
        Verify the integrity of a chain of audit logs.

        Returns: (is_valid, first_invalid_id)
        """
        previous_hash = None

        for log_entry in logs:
            integrity = log_entry.get("integrity", {})
            stored_previous = integrity.get("previous_hash")
            stored_hash = integrity.get("entry_hash")

            # Verify previous hash matches
            if stored_previous != previous_hash:
                if previous_hash is not None:  # Skip first entry
                    return False, log_entry.get("id")

            # Recompute and verify the entry's own HMAC over its full stored
            # form (or the legacy seven-field input for v1 entries).
            if not verify_entry_hash(log_entry):
                return False, log_entry.get("id")

            previous_hash = stored_hash

        return True, None

    async def get_logs(
        self,
        start_date: datetime = None,
        end_date: datetime = None,
        event_type: AuditEventType = None,
        user_id: str = None,
        limit: int = 100,
    ) -> list:
        """Query audit logs (for compliance reporting)."""
        logs = []

        # Read from log files
        for log_file in sorted(self.log_dir.glob("audit_*.jsonl"), reverse=True):
            # Skip files outside date range based on filename
            if start_date or end_date:
                try:
                    file_date_str = log_file.stem.replace("audit_", "")
                    file_date = datetime.strptime(file_date_str, "%Y-%m-%d")
                    if start_date and file_date.date() < start_date.date():
                        continue
                    if end_date and file_date.date() > end_date.date():
                        continue
                except ValueError:
                    pass

            with open(log_file) as f:
                for line in f:
                    try:
                        entry = json.loads(line)

                        # Apply filters
                        if event_type and entry["event_type"] != event_type.value:
                            continue
                        if user_id and entry["user"]["id"] != user_id:
                            continue

                        # Apply date filters on entry timestamp
                        if start_date or end_date:
                            entry_time = datetime.fromisoformat(entry["timestamp"].rstrip("Z"))
                            if start_date and entry_time < start_date:
                                continue
                            if end_date and entry_time > end_date:
                                continue

                        logs.append(entry)

                        if len(logs) >= limit:
                            return logs
                    except json.JSONDecodeError:
                        continue

        return logs

    # ==================== Log Rotation & Archival ====================

    async def rotate_old_logs(
        self,
        retention_days: int = 90,
        archive: bool = True,
    ) -> dict[str, Any]:
        """Compress logs older than retention_days and remove logs older than 2x retention.

        Designed to be called from a scheduled task (e.g., daily cron or APScheduler).

        Args:
            retention_days: Days to keep uncompressed JSONL files. Files older than
                this are gzip-compressed. Files older than 2x this are deleted.
            archive: If True, compress old files with gzip before eventual deletion.
                If False, delete files past retention without compressing.

        Returns:
            Summary dict with counts of compressed, deleted, and skipped files.
        """
        import gzip
        import shutil

        today = datetime.now(UTC).date()
        compress_cutoff = today - timedelta(days=retention_days)
        delete_cutoff = today - timedelta(days=retention_days * 2)

        stats: dict[str, Any] = {"compressed": 0, "deleted": 0, "skipped": 0, "errors": []}

        for log_file in self.log_dir.glob("audit_*.jsonl"):
            try:
                file_date_str = log_file.stem.replace("audit_", "")
                from datetime import datetime as dt

                file_date = dt.strptime(file_date_str, "%Y-%m-%d").date()
            except ValueError:
                stats["skipped"] += 1
                continue

            # Never touch today's active log
            if file_date >= today:
                stats["skipped"] += 1
                continue

            # Delete very old compressed archives
            gz_path = log_file.with_suffix(".jsonl.gz")
            if file_date < delete_cutoff:
                try:
                    if gz_path.exists():
                        gz_path.unlink()
                    if log_file.exists():
                        log_file.unlink()
                    stats["deleted"] += 1
                except OSError as e:
                    stats["errors"].append(f"Delete {log_file.name}: {e}")
                continue

            # Compress files past retention that aren't already compressed
            if file_date < compress_cutoff and archive:
                if gz_path.exists():
                    # Already compressed — remove uncompressed original
                    try:
                        log_file.unlink()
                    except OSError:
                        pass
                    stats["skipped"] += 1
                    continue
                try:
                    with open(log_file, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                    log_file.unlink()
                    stats["compressed"] += 1
                except OSError as e:
                    stats["errors"].append(f"Compress {log_file.name}: {e}")

        # Prune audit_logs DB rows past the delete cutoff too, so the queryable
        # table doesn't grow unbounded alongside the rotated JSONL files. The
        # tamper-evident JSONL chain is the archival record; the DB table is the
        # query surface and follows the same 2x-retention deletion horizon.
        stats["db_rows_deleted"] = await self._prune_db_rows(delete_cutoff)

        return stats

    @staticmethod
    async def _prune_db_rows(delete_cutoff) -> int:
        """Delete audit_logs rows older than *delete_cutoff* (a date). Returns count."""
        from datetime import datetime as dt
        from datetime import time as dt_time

        try:
            from sqlalchemy import delete as sa_delete

            from app.database import AsyncSessionLocal
            from app.models.audit import AuditLog

            cutoff_ts = dt.combine(delete_cutoff, dt_time.min)
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    sa_delete(AuditLog).where(AuditLog.timestamp < cutoff_ts)
                )
                await session.commit()
                return int(result.rowcount or 0)
        except Exception as e:  # retention must not crash the scheduler
            logging.getLogger(__name__).warning("Audit DB-row pruning failed: %s", e)
            return 0


# Global audit service instance
audit_service = AuditService()
