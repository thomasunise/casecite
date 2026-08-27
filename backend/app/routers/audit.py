"""Admin audit-log router.

Exposes the tamper-evident audit trail to administrators so compliance
questions ("who viewed this document?", "who signed in last week?") can be
answered in-product, and the HMAC hash chain can be verified on demand.
Access to the audit trail is itself audited.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request

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
    """Query the audit trail with optional date/type/user filters (admin-only)."""
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
    it was written — treat it as a security incident.
    """
    logs = await audit_service.get_logs(
        start_date=start_date,
        end_date=end_date,
        limit=_VERIFY_SCAN_LIMIT,
    )
    # get_logs returns newest-file-first; the chain must be verified in write order.
    logs.sort(key=lambda entry: entry.get("timestamp", ""))
    is_valid, first_invalid_id = await audit_service.verify_chain_integrity(logs)

    await audit_service.log_event(
        event_type=AuditEventType.AUDIT_LOG_ACCESS,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="audit_log",
        resource_id="verify",
        ip_address=get_client_ip(request),
        details={"entries_checked": len(logs), "valid": is_valid},
        success=is_valid,
    )
    return AuditVerifyResponse(
        valid=is_valid,
        entries_checked=len(logs),
        first_invalid_id=first_invalid_id,
    )
