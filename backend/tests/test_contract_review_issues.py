"""
Tests for the direction-aware unified issues report.

Source: backend/app/services/contract_analysis/issues.py
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from app.services.contract_analysis.issues import (  # noqa: E402
    FALLBACK_CONTRACT_TYPE,
    KNOWN_CONTRACT_TYPES,
    annotate_issues,
    collect_findings,
    detect_contract_type,
    merge_issues,
    verify_absence_claims,
)

CLAUSE_RESULT = {
    "deviations": [
        {
            "canonical_slug": "limitation_of_liability",
            "deviation_type": "missing_sub_element",
            "sub_element": "aggregate_cap",
            "severity": "critical",
            "span_start": 100,
            "span_end": 220,
            "matched_text": "Liability shall be unlimited. " * 20,
        },
        {
            "canonical_slug": "indemnification",
            "deviation_type": "one_sided",
            "sub_element": None,
            "severity": "minor",
            "span_start": 300,
            "span_end": 350,
            "matched_text": "Customer shall indemnify Provider.",
        },
    ],
    "missing": {
        "missing_required": [{"canonical_slug": "governing_law", "name": "Governing Law"}],
        "missing_recommended": [{"canonical_slug": "counterparts", "name": "Counterparts"}],
    },
    "jurisdiction_flags": [
        {
            "canonical_slug": "non_compete",
            "severity": "informational",
            "note": "Non-competes are unenforceable in California.",
        }
    ],
}

# Shape produced by document_analyzer.analyze_contract (general-purpose LLM).
GENERAL_ANALYSIS = {
    "summary": "This residential lease strongly favors the landlord on deposits and entry.",
    "risks": [
        {
            "risk_type": "financial",
            "description": "Tenant forfeits the entire security deposit on any breach",
            "severity": "high",
            "mitigation": "Cap deductions to actual damages.",
        },
        {
            "risk_type": "legal",
            "description": "Landlord may enter the premises without notice",
            "severity": "medium",
        },
        {
            "risk_type": "operational",
            "description": "Late fees compound daily",
            "severity": "low",
        },
    ],
    "missing_clauses": [
        # Duplicates the rules finding miss-0 (governing_law) — must be deduped.
        {"clause": "Governing Law", "importance": "critical", "reason": "No choice of law."},
        {"clause": "Quiet Enjoyment", "importance": "recommended", "reason": "Standard in leases."},
    ],
    "unusual_provisions": [
        {
            "provision": "Tenant must repaint at own expense annually",
            "concern": "Shifts maintenance costs unusually.",
            "section": "12",
        },
    ],
    "recommendations": [{"priority": "high", "recommendation": "Negotiate deposit terms."}],
    "model_used": "gpt-5.5",
}


def _mock_llm_client(payload: dict) -> MagicMock:
    """An AsyncOpenAI-shaped client whose one completion returns `payload` as JSON."""
    client = MagicMock()
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = json.dumps(payload)
    client.chat.completions.create = AsyncMock(return_value=resp)
    return client


class TestCollectFindings:
    def test_assigns_stable_refs_per_source(self):
        findings = collect_findings(CLAUSE_RESULT)
        refs = [f["ref"] for f in findings]
        assert refs == ["dev-0", "dev-1", "miss-0", "miss-1", "jur-0"]

    def test_spans_and_slugs_are_preserved(self):
        by_ref = {f["ref"]: f for f in collect_findings(CLAUSE_RESULT)}
        assert by_ref["dev-0"]["span_start"] == 100
        assert by_ref["dev-0"]["span_end"] == 220
        assert by_ref["dev-0"]["clause_slug"] == "limitation_of_liability"
        assert by_ref["miss-0"]["span_start"] is None
        assert by_ref["miss-0"]["clause_slug"] == "governing_law"

    def test_matched_text_is_truncated(self):
        by_ref = {f["ref"]: f for f in collect_findings(CLAUSE_RESULT)}
        assert len(by_ref["dev-0"]["matched_text"]) <= 200

    def test_severity_normalization(self):
        by_ref = {f["ref"]: f for f in collect_findings(CLAUSE_RESULT)}
        assert by_ref["dev-0"]["severity"] == "critical"
        # missing_required -> major, missing_recommended -> minor
        assert by_ref["miss-0"]["severity"] == "major"
        assert by_ref["miss-1"]["severity"] == "minor"
        # jurisdiction "informational" -> minor
        assert by_ref["jur-0"]["severity"] == "minor"

    def test_empty_pipeline_yields_no_findings(self):
        assert collect_findings({}) == []


class TestMergeIssues:
    def test_happy_path_joins_by_ref_and_attaches_spans(self):
        findings = collect_findings(CLAUSE_RESULT)
        payload = {
            "issues": [
                {
                    "ref": "dev-0",
                    "title": "Uncapped liability",
                    "status": "off_market",
                    "severity": "critical",
                    "why": "Customer faces unlimited exposure.",
                    "suggested_language": "Liability shall not exceed fees paid.",
                },
                {
                    "ref": "dev-1",
                    "title": "One-sided indemnity",
                    "status": "unusual",
                    "severity": "minor",
                    "why": "Only Customer indemnifies.",
                    "suggested_language": None,
                },
            ]
        }
        issues = merge_issues(findings, payload)
        by_ref = {i["ref"]: i for i in issues}

        dev0 = by_ref["dev-0"]
        assert dev0["title"] == "Uncapped liability"
        assert dev0["why"] == "Customer faces unlimited exposure."
        assert dev0["suggested_language"] == "Liability shall not exceed fees paid."
        # Offsets/slugs come from the source finding, not the LLM.
        assert dev0["span_start"] == 100
        assert dev0["span_end"] == 220
        assert dev0["clause_slug"] == "limitation_of_liability"
        assert dev0["source_kind"] == "deviation"
        assert by_ref["dev-1"]["span_start"] == 300

    def test_llm_offsets_are_ignored(self):
        findings = collect_findings(CLAUSE_RESULT)
        payload = {
            "issues": [
                {
                    "ref": "dev-0",
                    "title": "X",
                    "status": "off_market",
                    "severity": "critical",
                    "why": "w",
                    "suggested_language": None,
                    "span_start": 99999,
                    "span_end": 100000,
                }
            ]
        }
        issues = merge_issues(findings, payload)
        dev0 = next(i for i in issues if i["ref"] == "dev-0")
        assert dev0["span_start"] == 100
        assert dev0["span_end"] == 220

    def test_unknown_refs_dropped_and_omitted_findings_appended(self):
        findings = collect_findings(CLAUSE_RESULT)
        payload = {
            "issues": [
                {"ref": "dev-0", "title": "T", "status": "off_market", "severity": "critical"},
                {"ref": "hallucinated-9", "title": "Bogus", "status": "info", "severity": "minor"},
            ]
        }
        issues = merge_issues(findings, payload)
        refs = {i["ref"] for i in issues}
        assert "hallucinated-9" not in refs
        # Every source finding is still represented.
        assert refs == {f["ref"] for f in findings}
        # Omitted findings get mechanical entries (no why/suggested_language).
        dev1 = next(i for i in issues if i["ref"] == "dev-1")
        assert dev1["why"] is None
        assert dev1["suggested_language"] is None
        assert dev1["status"] == "off_market"
        assert dev1["severity"] == "minor"

    def test_sorted_critical_major_minor(self):
        findings = collect_findings(CLAUSE_RESULT)
        issues = merge_issues(findings, None)
        severities = [i["severity"] for i in issues]
        order = {"critical": 0, "major": 1, "minor": 2}
        assert severities == sorted(severities, key=lambda s: order[s])
        assert severities[0] == "critical"

    def test_llm_failure_fallback_is_fully_mechanical(self):
        findings = collect_findings(CLAUSE_RESULT)
        issues = merge_issues(findings, None)
        assert len(issues) == len(findings)
        assert all(i["why"] is None for i in issues)
        assert all(i["suggested_language"] is None for i in issues)
        miss0 = next(i for i in issues if i["ref"] == "miss-0")
        assert miss0["status"] == "missing"
        dev0 = next(i for i in issues if i["ref"] == "dev-0")
        assert dev0["status"] == "off_market"
        assert dev0["span_start"] == 100

    def test_garbage_payload_degrades_to_mechanical(self):
        findings = collect_findings(CLAUSE_RESULT)
        for payload in ({"issues": "not-a-list"}, {"nope": []}, {"issues": [42, "x", None]}):
            issues = merge_issues(findings, payload)
            assert len(issues) == len(findings)

    def test_invalid_status_and_severity_are_coerced_from_source(self):
        findings = collect_findings(CLAUSE_RESULT)
        payload = {
            "issues": [
                {"ref": "dev-0", "title": "T", "status": "terrible", "severity": "catastrophic"}
            ]
        }
        dev0 = next(i for i in merge_issues(findings, payload) if i["ref"] == "dev-0")
        assert dev0["status"] == "off_market"  # mechanical status for deviations
        assert dev0["severity"] == "critical"  # source finding severity

    def test_duplicate_refs_use_first_entry(self):
        findings = collect_findings(CLAUSE_RESULT)
        payload = {
            "issues": [
                {"ref": "dev-0", "title": "First", "status": "off_market", "severity": "critical"},
                {"ref": "dev-0", "title": "Second", "status": "info", "severity": "minor"},
            ]
        }
        issues = merge_issues(findings, payload)
        dev_entries = [i for i in issues if i["ref"] == "dev-0"]
        assert len(dev_entries) == 1
        assert dev_entries[0]["title"] == "First"


class TestDetectContractType:
    @pytest.mark.asyncio
    async def test_returns_known_type(self):
        client = _mock_llm_client({"contract_type": "NDA"})
        assert await detect_contract_type(client, "MUTUAL NON-DISCLOSURE AGREEMENT ...") == "nda"

    @pytest.mark.asyncio
    async def test_unknown_type_falls_back(self):
        client = _mock_llm_client({"contract_type": "interpretive-dance-agreement"})
        assert await detect_contract_type(client, "text") == FALLBACK_CONTRACT_TYPE

    @pytest.mark.asyncio
    async def test_llm_error_falls_back(self):
        client = MagicMock()
        client.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))
        assert await detect_contract_type(client, "text") == FALLBACK_CONTRACT_TYPE

    @pytest.mark.asyncio
    async def test_document_text_is_truncated(self):
        client = _mock_llm_client({"contract_type": "msa"})
        await detect_contract_type(client, "x" * 50_000)
        prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert len(prompt) < 10_000

    def test_known_types_come_from_taxonomy(self):
        assert set(KNOWN_CONTRACT_TYPES) == {"nda", "msa", "saas", "employment", "license", "sow"}


class TestAnnotateIssues:
    @pytest.mark.asyncio
    async def test_returns_parsed_payload(self):
        payload = {"issues": [{"ref": "dev-0", "title": "T"}]}
        client = _mock_llm_client(payload)
        findings = collect_findings(CLAUSE_RESULT)
        result = await annotate_issues(
            client,
            findings=findings,
            parties=[{"canonical_name": "Acme Corp", "role": "customer"}],
            representing="Customer",
            posture="strict",
            contract_type="msa",
        )
        assert result == payload
        prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        # The LLM sees refs, the represented side, and posture — but no offsets.
        assert "dev-0" in prompt
        assert "Customer" in prompt
        assert "STRICT" in prompt
        assert "span_start" not in prompt

    @pytest.mark.asyncio
    async def test_llm_failure_returns_none(self):
        client = MagicMock()
        client.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))
        result = await annotate_issues(
            client,
            findings=collect_findings(CLAUSE_RESULT),
            parties=[],
            representing=None,
            posture="balanced",
            contract_type="nda",
        )
        assert result is None
        # End to end: the merge still produces a full mechanical report.
        issues = merge_issues(collect_findings(CLAUSE_RESULT), result)
        assert len(issues) == 5


class TestGeneralFindings:
    """General-analyzer results mapped into gen-N findings (no spans)."""

    def test_omitting_general_matches_two_arg_call(self):
        assert collect_findings(CLAUSE_RESULT, None) == collect_findings(CLAUSE_RESULT)

    def test_general_refs_kinds_and_no_spans(self):
        findings = collect_findings(CLAUSE_RESULT, GENERAL_ANALYSIS)
        gen = [f for f in findings if f["ref"].startswith("gen-")]
        assert [f["ref"] for f in gen] == ["gen-0", "gen-1", "gen-2", "gen-3", "gen-4"]
        assert [f["kind"] for f in gen] == [
            "general_risk",
            "general_risk",
            "general_risk",
            "general_missing",
            "general_unusual",
        ]
        assert all(f["span_start"] is None and f["span_end"] is None for f in gen)
        assert all(f["clause_slug"] is None for f in gen)
        # Rule findings keep their refs untouched ahead of the general ones.
        assert [f["ref"] for f in findings[:5]] == [
            "dev-0",
            "dev-1",
            "miss-0",
            "miss-1",
            "jur-0",
        ]

    def test_general_severity_mapping(self):
        by_ref = {
            f["ref"]: f for f in collect_findings(CLAUSE_RESULT, GENERAL_ANALYSIS)
        }
        # risks: high -> critical, medium -> major, low -> minor
        assert by_ref["gen-0"]["severity"] == "critical"
        assert by_ref["gen-1"]["severity"] == "major"
        assert by_ref["gen-2"]["severity"] == "minor"
        # missing: recommended -> minor (critical -> major, but that one deduped)
        assert by_ref["gen-3"]["severity"] == "minor"
        # unusual provisions default to minor
        assert by_ref["gen-4"]["severity"] == "minor"

    def test_dedup_prefers_rules_version(self):
        findings = collect_findings(CLAUSE_RESULT, GENERAL_ANALYSIS)
        governing = [f for f in findings if "governing law" in f["name"].lower()]
        # Exactly one Governing Law finding survives — the rules one, with a slug.
        assert len(governing) == 1
        assert governing[0]["ref"] == "miss-0"
        assert governing[0]["clause_slug"] == "governing_law"

    def test_unknown_taxonomy_document_still_yields_findings(self):
        # A residential lease: the rules pipeline produces nothing, yet the
        # issues report is not empty.
        findings = collect_findings({}, GENERAL_ANALYSIS)
        assert [f["ref"] for f in findings] == [
            "gen-0",
            "gen-1",
            "gen-2",
            "gen-3",
            "gen-4",
            "gen-5",
        ]
        # Without a rules duplicate, the Governing Law clause is kept as general.
        assert any(f["name"] == "Missing clause: Governing Law" for f in findings)
        issues = merge_issues(findings, None)
        assert len(issues) == 6

    def test_general_kinds_mechanical_statuses(self):
        issues = merge_issues(collect_findings({}, GENERAL_ANALYSIS), None)
        statuses = {i["source_kind"]: i["status"] for i in issues}
        assert statuses["general_risk"] == "unusual"
        assert statuses["general_missing"] == "missing"
        assert statuses["general_unusual"] == "unusual"

    def test_llm_annotations_join_general_refs(self):
        findings = collect_findings({}, GENERAL_ANALYSIS)
        payload = {
            "issues": [
                {
                    "ref": "gen-0",
                    "title": "Deposit forfeiture",
                    "status": "off_market",
                    "severity": "critical",
                    "why": "Client loses the full deposit on any breach.",
                    "suggested_language": "Deductions limited to actual damages.",
                }
            ]
        }
        issues = merge_issues(findings, payload)
        gen0 = next(i for i in issues if i["ref"] == "gen-0")
        assert gen0["title"] == "Deposit forfeiture"
        assert gen0["why"] == "Client loses the full deposit on any breach."
        # General findings never gain offsets, even via the LLM.
        assert gen0["span_start"] is None
        assert gen0["span_end"] is None

    def test_garbage_general_entries_skipped(self):
        general = {
            "risks": [42, {"description": ""}, {"description": "Real risk", "severity": "weird"}],
            "missing_clauses": ["nope", {"clause": "   "}],
            "unusual_provisions": [None, {"provision": "  "}],
        }
        findings = collect_findings({}, general)
        assert [f["ref"] for f in findings] == ["gen-0"]
        assert findings[0]["name"] == "Real risk"
        assert findings[0]["severity"] == "major"  # unknown severity -> default


LEASE_TEXT = """RESIDENTIAL LEASE AGREEMENT

This Residential Lease Agreement is entered into by and between
Alpha Properties LLC ("Landlord") and Jane Doe ("Tenant").

Tenant shall pay rent of $2,000 per month. Tenant forfeits the entire
security deposit upon any breach of this Lease. Landlord may enter the
premises at any time without notice.
"""

CLAUSE_INTEL_RESULT = {
    "analysis_id": "run-1",
    "tags": [],
    "deviations": [
        {
            "canonical_slug": "limitation_of_liability",
            "deviation_type": "missing_sub_element",
            "sub_element": None,
            "severity": "critical",
            "span_start": 10,
            "span_end": 40,
            "matched_text": "unlimited liability",
        }
    ],
    "missing": {"missing_required": [], "missing_recommended": []},
    "jurisdiction_flags": [],
}


def _make_session_factory():
    """AsyncSessionLocal stand-in: async context manager around a mock session."""
    session = MagicMock()
    run_row = MagicMock()
    run_row.summary = {}
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = run_row
    session.execute = AsyncMock(return_value=exec_result)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, run_row


class TestServiceGeneralIntegration:
    """ContractAnalysisService.analyze always runs the general analyzer."""

    async def _run(self, general_mock):
        from app.services.contract_analysis import service as svc

        factory, run_row = _make_session_factory()
        clause_mock = AsyncMock(return_value=CLAUSE_INTEL_RESULT)
        user_keys = MagicMock()
        with (
            patch.object(svc.clause_intel_service, "analyze_contract", clause_mock),
            patch.object(svc.document_analyzer_service, "analyze_contract", general_mock),
            patch.object(svc, "AsyncSessionLocal", factory),
            patch.object(svc, "make_openai", MagicMock(return_value=None)),
        ):
            result = await svc.contract_analysis_service.analyze(
                text=LEASE_TEXT,
                contract_type="other",  # outside the seeded taxonomy
                user_id="user-1",
                user_keys=user_keys,
            )
        return result, run_row, user_keys

    @pytest.mark.asyncio
    async def test_unknown_type_yields_general_findings_and_summary(self):
        general_mock = AsyncMock(return_value=GENERAL_ANALYSIS)
        result, run_row, user_keys = await self._run(general_mock)

        assert result["contract_type"] == "other"
        # Executive summary: top-level response key AND persisted run summary.
        assert result["executive_summary"] == GENERAL_ANALYSIS["summary"]
        assert run_row.summary["executive_summary"] == GENERAL_ANALYSIS["summary"]

        gen_issues = [i for i in result["issues"] if i["ref"].startswith("gen-")]
        assert gen_issues, "unknown contract type must still yield general findings"
        assert all(i["span_start"] is None and i["span_end"] is None for i in gen_issues)
        # No built-in clause library in the judgment path: taxonomy deviations
        # never become user-facing issues.
        assert not any(i["ref"].startswith("dev-") for i in result["issues"])
        # The user's LLM keys are passed through to the general analyzer.
        assert general_mock.call_args.kwargs["user_keys"] is user_keys

    @pytest.mark.asyncio
    async def test_general_analyzer_exception_degrades_to_rules_only(self):
        general_mock = AsyncMock(side_effect=RuntimeError("provider down"))
        result, run_row, _ = await self._run(general_mock)

        assert result["executive_summary"] is None
        assert run_row.summary["executive_summary"] is None
        refs = [i["ref"] for i in result["issues"]]
        # No library fallback: with the general analyzer down and no AI review
        # client, the issues list is honestly empty rather than canned.
        assert not any(r.startswith("dev-") for r in refs)
        assert not any(r.startswith("gen-") for r in refs)

    @pytest.mark.asyncio
    async def test_general_analyzer_error_payload_degrades_to_rules_only(self):
        general_mock = AsyncMock(return_value={"error": "OpenAI contract analysis failed"})
        result, _, _ = await self._run(general_mock)

        assert result["executive_summary"] is None
        refs = [i["ref"] for i in result["issues"]]
        assert not any(r.startswith("dev-") for r in refs)
        assert not any(r.startswith("gen-") for r in refs)


class TestVerifyAbsenceClaims:
    """False 'missing clause' accusations must die before the user sees them."""

    CONTRACT = (
        "PAYMENT. Client will pay the fees set forth in the applicable SOW "
        "within 30 days after receipt of a correct invoice.\n"
        "All other legal terms are governed by the MSA.\n"
    )

    def _issues(self):
        return [
            {"ref": "miss-0", "title": "Missing payment terms", "why": "No payment clause found.",
             "grounding": "absence", "severity": "major"},
            {"ref": "miss-1", "title": "Missing arbitration clause", "why": "No arbitration.",
             "grounding": "absence", "severity": "minor"},
            {"ref": "dev-0", "title": "Uncapped liability", "why": "No cap.",
             "grounding": "span", "severity": "critical", "span_start": 0, "span_end": 10},
        ]

    def _client(self, payload):
        import json as _json
        from unittest.mock import AsyncMock, MagicMock
        client = MagicMock()
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = _json.dumps(payload)
        client.chat.completions.create = AsyncMock(return_value=response)
        return client

    @pytest.mark.asyncio
    async def test_refuted_claim_is_downgraded_not_deleted(self):
        quote = "Client will pay the fees set forth in the applicable SOW"
        client = self._client({"verdicts": [
            {"index": 0, "addressed": True, "quote": quote},
            {"index": 1, "addressed": False, "quote": ""},
        ]})
        out = await verify_absence_claims(client, self.CONTRACT, self._issues())
        by_ref = {i["ref"]: i for i in out}
        # Refuted claim survives as a visible, span-grounded "addressed" note.
        addressed = by_ref["miss-0"]
        assert addressed["title"].startswith("Addressed:")
        assert addressed["status"] == "info"
        assert addressed["grounding"] == "span"
        assert self.CONTRACT[addressed["span_start"]:addressed["span_end"]] == quote
        # Genuinely missing claim untouched; span-grounded issues untouched.
        assert by_ref["miss-1"]["grounding"] == "absence"
        assert by_ref["dev-0"]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_refutation_without_locatable_quote_is_ignored(self):
        client = self._client({"verdicts": [
            {"index": 0, "addressed": True, "quote": "A sentence not in the contract."},
        ]})
        out = await verify_absence_claims(client, self.CONTRACT, self._issues())
        miss0 = next(i for i in out if i["ref"] == "miss-0")
        assert miss0["grounding"] == "absence"  # unverifiable refutation ignored

    @pytest.mark.asyncio
    async def test_no_client_passes_everything_through(self):
        issues = self._issues()
        assert await verify_absence_claims(None, self.CONTRACT, issues) == issues

    @pytest.mark.asyncio
    async def test_llm_failure_keeps_all_issues(self):
        from unittest.mock import AsyncMock, MagicMock
        client = MagicMock()
        client.chat.completions.create = AsyncMock(side_effect=ConnectionError("down"))
        issues = self._issues()
        assert await verify_absence_claims(client, self.CONTRACT, issues) == issues

    # -- Only ABSENCE claims may be absence-verified ------------------------
    # A span-less risk finding ("uncapped liability") is a model conclusion,
    # not an accusation that something is missing. Asked "does the contract
    # address it?", the model happily quotes the liability clause — and the
    # risk used to be rewritten as "Addressed", severity minor, no redline.

    LIABILITY_CONTRACT = (
        "LIABILITY. Supplier's liability under this Agreement is unlimited.\n"
        "PAYMENT. Client will pay the fees within 30 days of invoice.\n"
    )

    @pytest.mark.asyncio
    async def test_spanless_risk_finding_is_never_rewritten_as_addressed(self):
        risk = {
            "ref": "gen-0",
            "title": "Uncapped liability",
            "why": "No cap on Supplier's liability.",
            "status": "unusual",
            "severity": "critical",
            "grounding": "unverified",
            "source_kind": "general_risk",
            "span_start": None,
            "span_end": None,
            "suggested_language": "Cap liability at 12 months' fees.",
        }
        # The model "refutes" it with a verbatim quote of the very clause that IS the risk.
        client = self._client({"verdicts": [
            {"index": 0, "addressed": True,
             "quote": "Supplier's liability under this Agreement is unlimited."},
        ]})
        out = await verify_absence_claims(client, self.LIABILITY_CONTRACT, [dict(risk)])
        assert out == [risk]  # untouched: title, severity, grounding, suggested_language
        # ...and it was never even put to the model: no absence claims, no call.
        client.chat.completions.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_spanless_risk_is_excluded_even_alongside_absence_claims(self):
        issues = [
            {"ref": "gen-0", "title": "Uncapped liability", "why": "No cap.",
             "status": "unusual", "severity": "critical", "grounding": "unverified",
             "source_kind": "general_risk", "span_start": None, "span_end": None},
            {"ref": "gen-1", "title": "Missing clause: payment terms", "why": "None found.",
             "status": "missing", "severity": "major", "grounding": "unverified",
             "source_kind": "general_missing", "span_start": None, "span_end": None},
        ]
        # Index 0 in the CLAIMS list is now the general_missing finding (the
        # only absence claim); a verdict about it must land on gen-1, not gen-0.
        client = self._client({"verdicts": [
            {"index": 0, "addressed": True,
             "quote": "Client will pay the fees within 30 days of invoice."},
            {"index": 1, "addressed": True,
             "quote": "Supplier's liability under this Agreement is unlimited."},
        ]})
        out = await verify_absence_claims(client, self.LIABILITY_CONTRACT, issues)
        by_ref = {i["ref"]: i for i in out}
        prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert "Uncapped liability" not in prompt
        assert "Missing clause: payment terms" in prompt
        risk = by_ref["gen-0"]
        assert risk["title"] == "Uncapped liability"
        assert risk["severity"] == "critical"
        assert risk["status"] == "unusual"
        assert risk["grounding"] == "unverified"
        addressed = by_ref["gen-1"]
        assert addressed["title"].startswith("Addressed:")
        assert addressed["status"] == "info"
        assert addressed["grounding"] == "span"

    @pytest.mark.asyncio
    async def test_general_missing_finding_is_still_downgraded_when_quote_verifies(self):
        issues = [
            {"ref": "gen-2", "title": "Missing clause: payment terms", "why": "None found.",
             "status": "missing", "severity": "major", "grounding": "unverified",
             "source_kind": "general_missing", "span_start": None, "span_end": None,
             "suggested_language": "Add a payment clause."},
        ]
        quote = "Client will pay the fees within 30 days of invoice."
        client = self._client({"verdicts": [{"index": 0, "addressed": True, "quote": quote}]})
        out = await verify_absence_claims(client, self.LIABILITY_CONTRACT, issues)
        addressed = out[0]
        assert addressed["title"] == "Addressed: Missing clause: payment terms"
        assert addressed["status"] == "info"
        assert addressed["severity"] == "minor"
        assert addressed["grounding"] == "span"
        assert self.LIABILITY_CONTRACT[addressed["span_start"]:addressed["span_end"]] == quote
        assert addressed["suggested_language"] is None

    def test_is_absence_claim_follows_source_kind(self):
        from app.services.contract_analysis.issues import ABSENCE_SOURCE_KINDS, is_absence_claim

        assert sorted(ABSENCE_SOURCE_KINDS) == ["general_missing", "missing"]
        assert is_absence_claim({"ref": "miss-0", "source_kind": "missing"})
        assert is_absence_claim({"ref": "gen-3", "source_kind": "general_missing"})
        for kind in ("general_risk", "general_unusual", "risk", "ai", "jurisdiction", "deviation"):
            assert not is_absence_claim({"ref": "x-0", "source_kind": kind}), kind
        # A span-grounded finding is never an absence claim, whatever its kind.
        assert not is_absence_claim({"ref": "miss-0", "source_kind": "missing", "span_start": 3})
        # Legacy issues without a source_kind fall back to the miss- ref prefix.
        assert is_absence_claim({"ref": "miss-1"})
        assert not is_absence_claim({"ref": "gen-1"})
