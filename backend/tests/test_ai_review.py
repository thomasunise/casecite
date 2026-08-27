"""AI-first contract review: instruction-driven, verbatim-grounded."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.contract_analysis.ai_review import ai_review_findings

CONTRACT = (
    "SECURITY DEPOSIT. Tenant forfeits the entire deposit upon any breach, "
    "however minor.\n"
    "ENTRY. Landlord may enter the premises at any time without notice.\n"
)


def _client_with(payload: dict) -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = json.dumps(payload)
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


class TestAiReviewFindings:
    @pytest.mark.asyncio
    async def test_verified_quote_becomes_span_grounded_finding(self):
        quote = "Landlord may enter the premises at any time without notice."
        client = _client_with({"issues": [{
            "title": "Unrestricted entry right",
            "severity": "critical",
            "why": "Tenant has no privacy protection.",
            "quote": quote,
            "suggested_direction": "Require 24 hours' notice.",
        }]})
        findings = await ai_review_findings(client, CONTRACT, "represent the tenant", "other", [])
        [finding] = findings
        assert finding["ref"] == "ai-0"
        assert finding["kind"] == "ai"
        assert CONTRACT[finding["span_start"]:finding["span_end"]] == quote
        assert finding["suggested_language"] == "Require 24 hours' notice."

    @pytest.mark.asyncio
    async def test_fabricated_quote_is_discarded(self):
        client = _client_with({"issues": [{
            "title": "Phantom clause",
            "severity": "major",
            "why": "w",
            "quote": "A sentence that appears nowhere in this contract.",
        }]})
        assert await ai_review_findings(client, CONTRACT, None, "other", []) == []

    @pytest.mark.asyncio
    async def test_overlap_with_rule_findings_is_skipped(self):
        quote = "Tenant forfeits the entire deposit upon any breach, however minor."
        start = CONTRACT.index(quote)
        client = _client_with({"issues": [{
            "title": "Deposit forfeiture",
            "severity": "major",
            "why": "w",
            "quote": quote,
        }]})
        findings = await ai_review_findings(
            client, CONTRACT, None, "other", [(start, start + len(quote))]
        )
        assert findings == []

    @pytest.mark.asyncio
    async def test_no_client_returns_empty(self):
        assert await ai_review_findings(None, CONTRACT, "x", "other", []) == []

    @pytest.mark.asyncio
    async def test_llm_failure_never_raises(self):
        client = MagicMock()
        client.chat.completions.create = AsyncMock(side_effect=ConnectionError("down"))
        assert await ai_review_findings(client, CONTRACT, "x", "other", []) == []
