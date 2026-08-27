"""Deep case-law research engine: full reads, verified quotes, honest drops."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.case_law_research import (
    WINDOW_CHARS,
    opinion_windows,
    research_authorities,
    verify_quote,
)


def _opinion(opinion_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=opinion_id,
        case_name=f"Case {opinion_id}",
        citation=[f"{opinion_id} F.3d 1"],
        absolute_url=f"https://www.courtlistener.com/opinion/{opinion_id}/",
        snippet="The court held...",
    )


def _client_seq(payloads: list[dict]) -> MagicMock:
    """LLM client answering with each payload in turn, repeating the last."""
    client = MagicMock()
    remaining = [json.dumps(p) for p in payloads]

    async def _create(*args, **kwargs):
        content = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = content
        return response

    client.chat.completions.create = AsyncMock(side_effect=_create)
    return client


CRAFT = {
    "targets": [
        {
            "proposition": "Late notice does not defeat coverage absent prejudice.",
            "query": "late notice prejudice coverage",
        }
    ]
}


class TestWindows:
    def test_short_text_is_one_window(self):
        assert opinion_windows("short opinion") == ["short opinion"]

    def test_long_text_covers_everything(self):
        text = "x" * (WINDOW_CHARS * 2 + 500)
        windows = opinion_windows(text)
        assert len(windows) >= 3
        # Every character position is inside some window.
        assert sum(len(w) for w in windows) >= len(text)


class TestVerifyQuote:
    def test_exact_quote_found(self):
        text = "Preamble. The rule is settled; late notice requires prejudice. End."
        quote = "The rule is settled; late notice requires prejudice."
        assert verify_quote(text, quote) is not None

    def test_fabricated_quote_rejected(self):
        assert verify_quote("Entirely different opinion text here.", "A made-up holding.") is None


class TestResearchAuthorities:
    @pytest.mark.asyncio
    async def test_verified_quote_is_attached_with_reason(self):
        holding = "Late notice does not defeat coverage absent a showing of prejudice."
        judge = {
            "relevant": True,
            "quote": holding,
            "why": "Directly states the prejudice requirement.",
        }
        with (
            patch(
                "app.services.case_law_research.courtlistener_service.search_opinions",
                new=AsyncMock(return_value=[_opinion(7)]),
            ),
            patch(
                "app.services.case_law_research.courtlistener_service.get_opinion",
                new=AsyncMock(return_value=SimpleNamespace(text=f"Intro. {holding} More.")),
            ),
        ):
            results, status = await research_authorities(
                "find case law on late notice", "late notice", _client_seq([CRAFT, judge])
            )

        assert status["attached"] == 1
        assert status["opinions_read"] == 1
        [result] = results
        assert result["metadata"]["doc_type"] == "case_law"
        assert result["metadata"]["case_name"] == "Case 7"
        assert result["metadata"]["case_summary"] == "Directly states the prejudice requirement."
        assert result["metadata"]["quote_verified"] is True
        assert holding.startswith(result["text"][:40])

    @pytest.mark.asyncio
    async def test_unverifiable_quote_is_dropped(self):
        judge = {
            "relevant": True,
            "quote": "A holding that appears nowhere in the opinion.",
            "why": "Sounds great.",
        }
        with (
            patch(
                "app.services.case_law_research.courtlistener_service.search_opinions",
                new=AsyncMock(return_value=[_opinion(7)]),
            ),
            patch(
                "app.services.case_law_research.courtlistener_service.get_opinion",
                new=AsyncMock(return_value=SimpleNamespace(text="The actual opinion text.")),
            ),
        ):
            results, status = await research_authorities(
                "find case law on late notice", "late notice", _client_seq([CRAFT, judge])
            )

        assert results == []
        assert status["attached"] == 0
        assert status["quote_unverified"] == 1

    @pytest.mark.asyncio
    async def test_search_failure_is_counted_not_raised(self):
        with patch(
            "app.services.case_law_research.courtlistener_service.search_opinions",
            new=AsyncMock(side_effect=ConnectionError("down")),
        ):
            results, status = await research_authorities(
                "find case law on late notice", "late notice", _client_seq([CRAFT])
            )

        assert results == []
        assert status["searches_failed"] == 1

    @pytest.mark.asyncio
    async def test_duplicate_opinions_across_concepts_read_once(self):
        craft_two = {
            "targets": [
                {"proposition": "Rule one.", "query": "rule one"},
                {"proposition": "Rule two.", "query": "rule two"},
            ]
        }
        judge = {"relevant": False, "quote": "", "why": ""}
        get_opinion = AsyncMock(return_value=SimpleNamespace(text="Opinion text."))
        with (
            patch(
                "app.services.case_law_research.courtlistener_service.search_opinions",
                new=AsyncMock(return_value=[_opinion(7)]),
            ),
            patch(
                "app.services.case_law_research.courtlistener_service.get_opinion",
                new=get_opinion,
            ),
        ):
            results, status = await research_authorities(
                "compound research request", None, _client_seq([craft_two, judge])
            )

        assert results == []
        assert get_opinion.await_count == 1
        assert status["opinions_read"] == 1
