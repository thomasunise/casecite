"""HTTP-level tests for the contract-analysis router (/api/v1/contract-analysis).

Covers the wiring the service-level tests cannot: authentication, the
``contracts.use`` permission, ownership of stored analyses, request bounds,
the delete endpoint, and that reads/exports/deletes are audited.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from app.models.clause_intel import ClauseTagFinding, ContractAnalysisRun
from app.models.contract_analysis import ContractParty
from app.services.audit import AuditEventType

from tests.helpers import db_add, db_count, headers, make_user

pytestmark = pytest.mark.usefixtures("no_rate_limit")

BASE = "/api/v1/contract-analysis"


def _seed_analysis(owner, **summary) -> str:
    run_id = uuid.uuid4().hex
    db_add(
        ContractAnalysisRun(
            id=run_id,
            user_id=owner.id,
            document_id="doc-1",
            contract_type="nda",
            document_length_chars=42,
            summary={"executive_summary": "Short NDA.", "issues": [{"ref": "I1"}], **summary},
            is_complete=True,
        ),
        ContractParty(
            analysis_id=run_id,
            canonical_name="Acme Corp",
            role="counterparty",
            detection_method="defined",
        ),
    )
    return run_id


class TestAuthAndPermission:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/analyses"),
            ("get", "/analyses/abc"),
            ("get", "/analyses/abc/export"),
            ("delete", "/analyses/abc"),
            ("post", "/analyze"),
            ("post", "/compare"),
            ("post", "/draft-export"),
        ],
    )
    def test_requires_authentication(self, client, method, path):
        assert getattr(client, method)(f"{BASE}{path}").status_code == 401

    def test_viewer_lacks_contracts_permission(self, client, non_admin_headers):
        resp = client.get(f"{BASE}/analyses", headers=non_admin_headers)
        assert resp.status_code == 403
        resp = client.post(
            f"{BASE}/analyze", json={"document_text": "x"}, headers=non_admin_headers
        )
        assert resp.status_code == 403


class TestStoredAnalyses:
    def test_owner_lists_and_reads_own_analysis(self, client, audit_events):
        owner = make_user("ca-owner")
        run_id = _seed_analysis(owner)

        listed = client.get(f"{BASE}/analyses", headers=headers(owner))
        assert listed.status_code == 200
        assert [a["analysis_id"] for a in listed.json()["analyses"]] == [run_id]
        assert listed.json()["analyses"][0]["issues"] == 1

        detail = client.get(f"{BASE}/analyses/{run_id}", headers=headers(owner))
        assert detail.status_code == 200

        views = [e for e in audit_events if e["details"].get("action") == "contract_analysis_view"]
        assert len(views) == 1
        assert views[0]["event_type"] == AuditEventType.DATA_ACCESS
        assert views[0]["resource_id"] == run_id
        assert views[0]["user_id"] == owner.id

    def test_unknown_analysis_is_404(self, client):
        owner = make_user("ca-owner")
        assert client.get(f"{BASE}/analyses/nope", headers=headers(owner)).status_code == 404

    @pytest.mark.parametrize("limit", [0, 201, -5])
    def test_list_limit_is_bounded(self, client, limit):
        owner = make_user("ca-owner")
        resp = client.get(f"{BASE}/analyses?limit={limit}", headers=headers(owner))
        assert resp.status_code == 422

    def test_export_markdown_is_audited_as_export(self, client, audit_events):
        owner = make_user("ca-owner")
        run_id = _seed_analysis(owner)

        resp = client.get(f"{BASE}/analyses/{run_id}/export?format=md", headers=headers(owner))
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")
        assert f"contract-analysis-{run_id[:8]}.md" in resp.headers["content-disposition"]
        assert "Acme Corp" in resp.text

        exports = [e for e in audit_events if e["event_type"] == AuditEventType.DATA_EXPORT]
        assert len(exports) == 1
        assert exports[0]["details"]["action"] == "contract_analysis_export"
        assert exports[0]["details"]["format"] == "md"

    def test_export_rejects_unknown_format(self, client):
        owner = make_user("ca-owner")
        run_id = _seed_analysis(owner)
        resp = client.get(f"{BASE}/analyses/{run_id}/export?format=pdf", headers=headers(owner))
        assert resp.status_code == 400

    def test_redline_export_without_redlines_is_404(self, client):
        owner = make_user("ca-owner")
        run_id = _seed_analysis(owner)
        resp = client.get(f"{BASE}/analyses/{run_id}/redline-export", headers=headers(owner))
        assert resp.status_code == 404
        assert "No redlines" in resp.json()["detail"]

    def test_redline_export_rejects_oversized_override(self, client):
        owner = make_user("ca-owner")
        run_id = _seed_analysis(owner)
        resp = client.post(
            f"{BASE}/analyses/{run_id}/redline-export",
            json={"exclude": [], "overrides": {"R1": "x" * 100_001}},
            headers=headers(owner),
        )
        assert resp.status_code == 422


class TestDeleteAnalysis:
    def test_owner_deletes_run_and_children(self, client, audit_events):
        owner = make_user("ca-owner")
        run_id = _seed_analysis(owner)
        db_add(
            ClauseTagFinding(
                analysis_id=run_id,
                canonical_slug="confidentiality",
                span_start=0,
                span_end=31,
                matched_text="verbatim privileged clause text",
                method="regex",
                confidence=0.9,
            )
        )

        resp = client.delete(f"{BASE}/analyses/{run_id}", headers=headers(owner))
        assert resp.status_code == 200
        assert resp.json() == {"status": "deleted", "id": run_id}

        assert db_count(ContractAnalysisRun, ContractAnalysisRun.id == run_id) == 0
        assert db_count(ContractParty, ContractParty.analysis_id == run_id) == 0
        assert db_count(ClauseTagFinding, ClauseTagFinding.analysis_id == run_id) == 0
        assert client.get(f"{BASE}/analyses/{run_id}", headers=headers(owner)).status_code == 404

        deletions = [e for e in audit_events if e["event_type"] == AuditEventType.DATA_DELETION]
        assert len(deletions) == 1
        assert deletions[0]["resource_id"] == run_id

    def test_matter_member_cannot_delete(self, client):
        """A run shared through a matter is readable by members, deletable by its owner only."""
        from tests.helpers import make_shared_matter

        owner, member = make_user("ca-owner"), make_user("ca-member")
        matter_id = make_shared_matter(owner, member)
        run_id = uuid.uuid4().hex
        db_add(
            ContractAnalysisRun(
                id=run_id,
                user_id=owner.id,
                matter_id=matter_id,
                contract_type="nda",
                document_length_chars=1,
                summary={},
            )
        )

        assert client.get(f"{BASE}/analyses/{run_id}", headers=headers(member)).status_code == 200
        assert (
            client.delete(f"{BASE}/analyses/{run_id}", headers=headers(member)).status_code == 404
        )
        assert db_count(ContractAnalysisRun, ContractAnalysisRun.id == run_id) == 1


class TestAnalyzeAndCompare:
    def test_analyze_requires_text_or_document(self, client):
        owner = make_user("ca-owner")
        resp = client.post(f"{BASE}/analyze", json={}, headers=headers(owner))
        assert resp.status_code == 400

    def test_analyze_rejects_bad_effective_date(self, client):
        owner = make_user("ca-owner")
        resp = client.post(
            f"{BASE}/analyze",
            json={"document_text": "Some contract.", "effective_date": "not-a-date"},
            headers=headers(owner),
        )
        assert resp.status_code == 400

    def test_analyze_unknown_document_is_404(self, client):
        """document_id is resolved against the caller's own documents only."""
        owner = make_user("ca-owner")
        resp = client.post(
            f"{BASE}/analyze", json={"document_id": "someone-elses-doc"}, headers=headers(owner)
        )
        assert resp.status_code == 404

    def test_analyze_happy_path_passes_caller_identity(self, client):
        owner = make_user("ca-owner")
        result = {"analysis_id": "a1", "contract_type": "nda", "issues": []}
        with patch(
            "app.routers.contract_analysis.contract_analysis_service.analyze",
            new_callable=AsyncMock,
            return_value=result,
        ) as analyze:
            resp = client.post(
                f"{BASE}/analyze",
                json={"document_text": "This NDA is made between A and B."},
                headers=headers(owner),
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["analysis_id"] == "a1"
        assert analyze.await_args.kwargs["user_id"] == owner.id
        assert analyze.await_args.kwargs["text"] == "This NDA is made between A and B."

    def test_compare_needs_two_documents(self, client):
        owner = make_user("ca-owner")
        resp = client.post(f"{BASE}/compare", json={}, headers=headers(owner))
        assert resp.status_code == 400


class TestDraftExport:
    def test_draft_export_returns_docx_and_is_audited(self, client, audit_events):
        owner = make_user("ca-owner")
        resp = client.post(
            f"{BASE}/draft-export",
            json={"title": "Demand Letter – Smith", "text": "Dear Counsel,\n\nPlease be advised."},
            headers=headers(owner),
        )
        assert resp.status_code == 200
        assert resp.content[:2] == b"PK"  # a .docx is a zip
        assert (
            resp.headers["content-disposition"]
            == 'attachment; filename="Demand Letter  Smith.docx"'
        )

        exports = [e for e in audit_events if e["event_type"] == AuditEventType.DATA_EXPORT]
        assert [e["details"]["action"] for e in exports] == ["contract_draft_export"]

    def test_draft_export_rejects_empty_text(self, client):
        owner = make_user("ca-owner")
        resp = client.post(
            f"{BASE}/draft-export", json={"title": "x", "text": ""}, headers=headers(owner)
        )
        assert resp.status_code == 422

    def test_generate_rejects_oversized_plan(self, client):
        owner = make_user("ca-owner")
        resp = client.post(
            f"{BASE}/draft/generate",
            json={"message": "draft it", "plan": {"sections": ["x" * 200_001]}},
            headers=headers(owner),
        )
        assert resp.status_code == 422
