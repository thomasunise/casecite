"""
HTTP-level tests for the admin audit router (/api/v1/admin/audit/*).

The router is pointed at an isolated AuditService over a temp directory, so
these never read or write the instance's real audit trail.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

import asyncio
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from app.services.audit import AuditEventType, AuditLog, check_chain

BASE = "/api/v1/admin/audit"


@pytest.fixture
def audit(audit_service_isolated):
    """Route the router's audit_service to the isolated instance."""
    AuditLog._last_hash = None
    with patch("app.routers.audit.audit_service", audit_service_isolated):
        yield audit_service_isolated


def _seed(service, count: int = 3) -> None:
    async def _write():
        for i in range(count):
            await service.log_event(
                AuditEventType.DOCUMENT_VIEW,
                user_id=f"user-{i}",
                resource_type="document",
                resource_id=f"doc-{i}",
            )
        await service.log_event(AuditEventType.LOGIN_FAILURE, user_id="user-0", success=False)

    asyncio.run(_write())


def _stored(service) -> list[dict]:
    return asyncio.run(service.get_logs(limit=10_000, newest_first=False))


class TestAccessControl:
    @pytest.mark.parametrize("path", ["/logs", "/verify", "/export"])
    def test_requires_authentication(self, client, audit, path):
        assert client.get(f"{BASE}{path}").status_code == 401

    @pytest.mark.parametrize("path", ["/logs", "/verify", "/export"])
    def test_non_admin_is_refused(self, client, audit, non_admin_headers, path):
        _seed(audit)
        resp = client.get(f"{BASE}{path}", headers=non_admin_headers)
        assert resp.status_code == 403
        assert "doc-0" not in resp.text


class TestQueryLogs:
    def test_returns_newest_first(self, client, audit, auth_headers):
        _seed(audit)
        resp = client.get(f"{BASE}/logs", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 4
        assert [e["event_type"] for e in body["logs"]] == [
            "auth.login.failure",
            "document.view",
            "document.view",
            "document.view",
        ]
        assert body["logs"][1]["resource"]["id"] == "doc-2"

    def test_limit_keeps_the_newest(self, client, audit, auth_headers):
        _seed(audit)
        resp = client.get(f"{BASE}/logs", params={"limit": 1}, headers=auth_headers)
        assert resp.status_code == 200
        (entry,) = resp.json()["logs"]
        assert entry["event_type"] == "auth.login.failure"

    def test_filters_by_event_type_and_user(self, client, audit, auth_headers):
        _seed(audit)
        resp = client.get(
            f"{BASE}/logs",
            params={"event_type": "document.view", "user_id": "user-1"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        (entry,) = resp.json()["logs"]
        assert entry["resource"]["id"] == "doc-1"

    def test_unknown_event_type_is_400(self, client, audit, auth_headers):
        resp = client.get(f"{BASE}/logs", params={"event_type": "nope"}, headers=auth_headers)
        assert resp.status_code == 400

    def test_date_filters_do_not_500(self, client, audit, auth_headers):
        """Naive and offset-bearing bounds both used to raise TypeError."""
        _seed(audit)
        now = datetime.now(UTC)
        naive = now.replace(tzinfo=None)

        resp = client.get(
            f"{BASE}/logs",
            params={
                "start_date": (naive - timedelta(hours=1)).isoformat(),
                "end_date": (naive + timedelta(hours=1)).isoformat(),
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 4

        resp = client.get(
            f"{BASE}/logs",
            params={"start_date": (now + timedelta(hours=1)).isoformat()},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_inverted_range_is_400(self, client, audit, auth_headers):
        resp = client.get(
            f"{BASE}/logs",
            params={"start_date": "2026-02-01T00:00:00", "end_date": "2026-01-01T00:00:00"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_limit_is_bounded(self, client, audit, auth_headers):
        resp = client.get(f"{BASE}/logs", params={"limit": 100_000}, headers=auth_headers)
        assert resp.status_code == 422

    def test_access_is_itself_audited(self, client, audit, auth_headers):
        _seed(audit, count=1)
        client.get(f"{BASE}/logs", headers=auth_headers)
        last = _stored(audit)[-1]
        assert last["event_type"] == "compliance.audit.access"
        assert last["resource"]["id"] == "query"
        assert last["user"]["id"] == "test-user-123"


class TestVerify:
    def test_chain_written_by_the_service_verifies(self, client, audit, auth_headers):
        _seed(audit)
        resp = client.get(f"{BASE}/verify", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body == {
            "valid": True,
            "entries_checked": 4,
            "first_invalid_id": None,
            "reason": None,
            "legacy_entries": 0,
            "truncated": False,
        }
        # Verifying twice stays valid: the access entries are themselves chained
        assert client.get(f"{BASE}/verify", headers=auth_headers).json()["valid"] is True

    def test_edited_entry_is_reported(self, client, audit, auth_headers):
        _seed(audit)
        log_file = audit._get_log_file()
        entries = [json.loads(line) for line in log_file.read_text().splitlines()]
        entries[1]["resource"]["id"] = "some-other-doc"
        log_file.write_text("".join(json.dumps(e) + "\n" for e in entries))

        body = client.get(f"{BASE}/verify", headers=auth_headers).json()
        assert body["valid"] is False
        assert body["first_invalid_id"] == entries[1]["id"]
        assert "HMAC MISMATCH" in body["reason"]

        last = _stored(audit)[-1]
        assert last["resource"]["id"] == "verify"
        assert last["outcome"]["success"] is False

    def test_removed_entry_is_reported(self, client, audit, auth_headers):
        _seed(audit)
        log_file = audit._get_log_file()
        lines = log_file.read_text().splitlines()
        removed_successor = json.loads(lines[2])["id"]
        del lines[1]
        log_file.write_text("\n".join(lines) + "\n")

        body = client.get(f"{BASE}/verify", headers=auth_headers).json()
        assert body["valid"] is False
        assert body["first_invalid_id"] == removed_successor
        assert "CHAIN INTEGRITY BROKEN" in body["reason"]

    def test_scan_limit_sets_truncated(self, client, audit, auth_headers):
        _seed(audit)
        with patch("app.routers.audit._VERIFY_SCAN_LIMIT", 2):
            body = client.get(f"{BASE}/verify", headers=auth_headers).json()
        assert body["valid"] is True
        assert body["entries_checked"] == 2
        assert body["truncated"] is True


class TestExport:
    def test_streams_jsonl_in_write_order(self, client, audit, auth_headers):
        _seed(audit)
        before = _stored(audit)

        resp = client.get(f"{BASE}/export", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/x-ndjson")
        disposition = resp.headers["content-disposition"]
        assert disposition.startswith('attachment; filename="audit-export-')
        assert disposition.endswith('.jsonl"')

        exported = [json.loads(line) for line in resp.text.splitlines()]
        # The export's own access entry is written first, so it is included
        assert [e["id"] for e in exported[:-1]] == [e["id"] for e in before]
        assert exported[-1]["resource"]["id"] == "export"
        # Stored records, integrity blocks intact: the export re-verifies offline
        assert check_chain(exported).valid is True

    def test_filters_apply(self, client, audit, auth_headers):
        _seed(audit)
        resp = client.get(
            f"{BASE}/export", params={"event_type": "auth.login.failure"}, headers=auth_headers
        )
        assert resp.status_code == 200
        (entry,) = [json.loads(line) for line in resp.text.splitlines()]
        assert entry["user"]["id"] == "user-0"

        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        resp = client.get(f"{BASE}/export", params={"start_date": future}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.text == ""

    def test_bad_parameters_are_rejected_before_streaming(self, client, audit, auth_headers):
        resp = client.get(f"{BASE}/export", params={"event_type": "nope"}, headers=auth_headers)
        assert resp.status_code == 400
        resp = client.get(
            f"{BASE}/export",
            params={"start_date": "2026-02-01T00:00:00", "end_date": "2026-01-01T00:00:00"},
            headers=auth_headers,
        )
        assert resp.status_code == 400
