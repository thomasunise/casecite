"""Admin audit-log router.

Exposes the tamper-evident audit trail to administrators so compliance
questions ("who viewed this document?", "who signed in last week?") can be
answered in-product, the HMAC hash chain can be verified on demand, and a
date range can be exported for retention outside the instance.
Access to the audit trail is itself audited.
"""

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.models.schemas import AuditLogListResponse, AuditVerifyResponse
from app.services.audit import AuditEventType, audit_service
from app.services.auth import TokenData
from app.services.permissions import require_permission
from app.utils.ip_resolution import get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/audit", tags=["admin-audit"])

_MAX_QUERY_LIMIT = 1000
_VERIFY_SCAN_LIMIT = 100_000


def _parse_event_type(raw: str | None) -> AuditEventType | None:
    if not raw:
        return None
    try:
        return AuditEventType(raw)
    except ValueError:
        valid = sorted(e.value for e in AuditEventType)
        raise HTTPException(status_code=400, detail=f"Unknown event_type. Valid values: {valid}")


def _check_range(start_date: datetime | None, end_date: datetime | None) -> None:
    """Reject an inverted range. Naive bounds are taken as UTC, like the service."""
    if start_date is None or end_date is None:
        return
    start = start_date if start_date.tzinfo else start_date.replace(tzinfo=UTC)
    end = end_date if end_date.tzinfo else end_date.replace(tzinfo=UTC)
    if start > end:
        raise HTTPException(status_code=400, detail="start_date must not be after end_date")


@router.get("/logs", response_model=AuditLogListResponse)
async def query_audit_logs(
    request: Request,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    event_type: str | None = None,
    user_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=_MAX_QUERY_LIMIT),
    current_user: TokenData = require_permission("admin.audit"),
) -> AuditLogListResponse:
    """Query the audit trail, newest first, with optional date/type/user filters (admin-only).

    Dates without a UTC offset are read as UTC.
    """
    _check_range(start_date, end_date)
    logs = await audit_service.get_logs(
        start_date=start_date,
        end_date=end_date,
        event_type=_parse_event_type(event_type),
        user_id=user_id,
        limit=limit,
    )

    await audit_service.log_event(
        event_type=AuditEventType.AUDIT_LOG_ACCESS,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="audit_log",
        resource_id="query",
        ip_address=get_client_ip(request),
        details={
            "filters": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "event_type": event_type,
                "user_id": user_id,
                "limit": limit,
            },
            "returned": len(logs),
        },
    )
    return AuditLogListResponse(logs=logs, count=len(logs))


@router.get("/verify", response_model=AuditVerifyResponse)
async def verify_audit_chain(
    request: Request,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    current_user: TokenData = require_permission("admin.audit"),
) -> AuditVerifyResponse:
    """Verify the HMAC hash chain over the (optionally date-bounded) audit trail.

    A failed verification means an entry was altered, inserted, or removed after
    it was written — treat it as a security incident. Entries written before
    chain linkage was enforced are signature-checked only and counted in
    `legacy_entries`. At most the newest 100,000 entries in the range are
    scanned; `truncated` says when the range held more.
    """
    _check_range(start_date, end_date)
    # One extra entry tells us whether the range was cut off at the scan limit.
    logs = await audit_service.get_logs(
        start_date=start_date,
        end_date=end_date,
        limit=_VERIFY_SCAN_LIMIT + 1,
        newest_first=False,  # the chain is verified in write order
    )
    truncated = len(logs) > _VERIFY_SCAN_LIMIT
    if truncated:
        logs = logs[1:]
    result = audit_service.check_chain(logs)

    await audit_service.log_event(
        event_type=AuditEventType.AUDIT_LOG_ACCESS,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="audit_log",
        resource_id="verify",
        ip_address=get_client_ip(request),
        details={
            "entries_checked": result.entries_checked,
            "valid": result.valid,
            "first_invalid_id": result.first_invalid_id,
            "truncated": truncated,
        },
        success=result.valid,
    )
    return AuditVerifyResponse(
        valid=result.valid,
        entries_checked=result.entries_checked,
        first_invalid_id=result.first_invalid_id,
        reason=result.reason,
        legacy_entries=result.legacy_entries,
        truncated=truncated,
    )


def _jsonl(entries: Iterator[dict]) -> Iterator[str]:
    for entry in entries:
        yield json.dumps(entry) + "\n"


@router.get("/export")
async def export_audit_logs(
    request: Request,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    event_type: str | None = None,
    user_id: str | None = None,
    current_user: TokenData = require_permission("admin.audit"),
) -> StreamingResponse:
    """Download the audit trail for a date range as JSONL, oldest entry first (admin-only).

    Each entry is the stored record including its `integrity` block, so an
    unfiltered export can be re-verified offline with the instance's
    AUDIT_HMAC_KEY. Compressed archives are included.
    """
    _check_range(start_date, end_date)
    parsed_type = _parse_event_type(event_type)

    # Audited before the stream starts: the record must exist even if the
    # client disconnects mid-download.
    await audit_service.log_event(
        event_type=AuditEventType.AUDIT_LOG_ACCESS,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="audit_log",
        resource_id="export",
        ip_address=get_client_ip(request),
        details={
            "filters": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "event_type": event_type,
                "user_id": user_id,
            },
        },
    )

    entries = audit_service.iter_logs(
        start_date=start_date,
        end_date=end_date,
        event_type=parsed_type,
        user_id=user_id,
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return StreamingResponse(
        _jsonl(entries),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="audit-export-{stamp}.jsonl"'},
    )
