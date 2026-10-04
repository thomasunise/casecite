"""Conversational contract review: intent routing + verified citations."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.services.contract_analysis.chat import (
    answer_contract_question,
    route_contract_message,
)

CONTRACT = (
    "TERMINATION. Either party may terminate this Agreement upon thirty (30) "
    "days' prior written notice.\n"
    "LIMITATION OF LIABILITY. Liability is capped at the fees paid in the "
    "twelve months preceding the claim.\n"
)


def _client_with(payload: dict) -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = json.dumps(payload)
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


class TestRouting:
    @pytest.mark.asyncio
    async def test_no_client_defaults_to_ask(self):
        assert (await route_contract_message(None, "review this"))["intent"] == "ask"

    @pytest.mark.asyncio
    async def test_analyze_intent_with_instructions(self):
        client = _client_with(
            {"intent": "analyze", "instructions": "represent the tenant, flag one-sided terms"}
        )
        route = await route_contract_message(client, "review this lease for the tenant")
        assert route["intent"] == "analyze"
        assert "tenant" in route["instructions"]

    @pytest.mark.asyncio
    async def test_bad_intent_falls_back(self):
        client = _client_with({"intent": "banana", "instructions": ""})
        assert (await route_contract_message(client, "hm"))["intent"] == "ask"

    @pytest.mark.asyncio
    async def test_routing_failure_never_raises(self):
        client = MagicMock()
        client.chat.completions.create = AsyncMock(side_effect=ConnectionError("down"))
        assert (await route_contract_message(client, "x"))["intent"] == "ask"


class TestAnswer:
    @pytest.mark.asyncio
    async def test_verified_citation_carries_offsets(self):
        quote = "Liability is capped at the fees paid in the twelve months preceding the claim."
        client = _client_with({"answer": "Yes — liability is capped [1].", "citations": [quote]})
        result = await answer_contract_question(client, CONTRACT, "is there a cap?")
        [citation] = result["citations"]
        assert CONTRACT[citation["span_start"] : citation["span_end"]] == quote

    @pytest.mark.asyncio
    async def test_fabricated_citation_is_dropped(self):
        client = _client_with(
            {"answer": "The moon clause applies [1].", "citations": ["There is a moon clause."]}
        )
        result = await answer_contract_question(client, CONTRACT, "moon?")
        assert result["citations"] == []

    @pytest.mark.asyncio
    async def test_no_client_raises_value_error(self):
        with pytest.raises(ValueError):
            await answer_contract_question(None, CONTRACT, "anything")


class TestAnswerCaseLawGuard:
    @pytest.mark.asyncio
    async def test_case_not_in_the_contract_or_the_question_is_removed(self):
        client = _client_with(
            {
                "answer": "The cap is enforceable under Madeup v. Imaginary, 999 F.3d 1.",
                "citations": [],
            }
        )
        result = await answer_contract_question(client, CONTRACT, "is the cap enforceable?")
        assert "Madeup" not in result["answer"]
        assert len(result["case_law_removed"]) == 1

    @pytest.mark.asyncio
    async def test_case_the_lawyer_asked_about_is_kept(self):
        answer = "The contract does not address Smith v. Jones."
        client = _client_with({"answer": answer, "citations": []})
        result = await answer_contract_question(
            client, CONTRACT, "does this comply with Smith v. Jones?"
        )
        assert result["answer"] == answer
        assert result["case_law_removed"] == []
