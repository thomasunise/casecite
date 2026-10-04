"""HTTP-level tests for the authority-map router (/api/v1/authority-map)."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from app.models.authority_map import AuthorityMapping, AuthorityMapRun
from app.services.audit import AuditEventType

from tests.helpers import db_add, db_count, headers, make_user

pytestmark = pytest.mark.usefixtures("no_rate_limit")

BASE = "/api/v1/authority-map"


def _seed_run(owner) -> str:
    run_id = uuid.uuid4().hex
    db_add(
        AuthorityMapRun(id=run_id, user_id=owner.id, document_name="brief.docx", summary={"n": 1}),
        AuthorityMapping(
            run_id=run_id,
            proposition="Summary judgment requires no genuine dispute of material fact.",
            source="courtlistener",
            case_name="Celotex Corp. v. Catrett",
            verified=1,
            relevance=0.9,
        ),
    )
    return run_id


class TestAuthAndPermission:
    def test_requires_authentication(self, client):
        assert client.post(f"{BASE}/analyze", json={"document_text": "x"}).status_code == 401
        assert client.get(f"{BASE}/abc").status_code == 401
        assert client.delete(f"{BASE}/abc").status_code == 401

    def test_viewer_lacks_authority_map_permission(self, client, non_admin_headers):
        resp = client.post(
            f"{BASE}/analyze", json={"document_text": "x"}, headers=non_admin_headers
        )
        assert resp.status_code == 403
        assert client.get(f"{BASE}/abc", headers=non_admin_headers).status_code == 403


class TestAnalyze:
    def test_submits_job_for_the_caller(self, client, audit_events):
        owner = make_user("am-owner")
        with patch(
            "app.routers.authority_map.job_manager.submit",
            new_callable=AsyncMock,
            return_value="job-123",
        ) as submit:
            resp = client.post(
                f"{BASE}/analyze",
                json={"document_text": "The court should grant the motion.", "jurisdiction": "ca9"},
                headers=headers(owner),
            )
        assert resp.status_code == 200
        assert resp.json() == {"job_id": "job-123"}
        assert submit.await_args.kwargs["user_id"] == owner.id
        assert [e["details"]["action"] for e in audit_events] == ["authority_map_submit"]

    def test_blank_document_is_rejected(self, client):
        owner = make_user("am-owner")
        resp = client.post(f"{BASE}/analyze", json={"document_text": "   "}, headers=headers(owner))
        assert resp.status_code == 400

    def test_oversized_document_is_rejected(self, client):
        owner = make_user("am-owner")
        resp = client.post(
            f"{BASE}/analyze", json={"document_text": "x" * 2_000_001}, headers=headers(owner)
        )
        assert resp.status_code == 422


class TestReadAndDelete:
    def test_owner_reads_run_and_it_is_audited(self, client, audit_events):
        owner = make_user("am-owner")
        run_id = _seed_run(owner)

        resp = client.get(f"{BASE}/{run_id}", headers=headers(owner))
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == run_id
        assert body["document_name"] == "brief.docx"
        assert body["mappings"][0]["case_name"] == "Celotex Corp. v. Catrett"
        assert body["mappings"][0]["verified"] is True

        assert len(audit_events) == 1
        assert audit_events[0]["event_type"] == AuditEventType.DATA_ACCESS
        assert audit_events[0]["resource_id"] == run_id

    def test_unknown_run_is_404(self, client):
        owner = make_user("am-owner")
        assert client.get(f"{BASE}/nope", headers=headers(owner)).status_code == 404

    def test_owner_deletes_run_and_mappings(self, client, audit_events):
        owner = make_user("am-owner")
        run_id = _seed_run(owner)

        resp = client.delete(f"{BASE}/{run_id}", headers=headers(owner))
        assert resp.status_code == 200
        assert resp.json() == {"status": "deleted", "id": run_id}
        assert db_count(AuthorityMapRun, AuthorityMapRun.id == run_id) == 0
        assert db_count(AuthorityMapping, AuthorityMapping.run_id == run_id) == 0
        assert client.get(f"{BASE}/{run_id}", headers=headers(owner)).status_code == 404

        deletions = [e for e in audit_events if e["event_type"] == AuditEventType.DATA_DELETION]
        assert [e["resource_id"] for e in deletions] == [run_id]
