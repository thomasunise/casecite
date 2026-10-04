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


class TestJudgeOpinion:
    """The shared read-and-judge loop behind research chat and the strategy brief."""

    @staticmethod
    def _prompt(part: str, block: str) -> str:
        return f"JUDGE ({part}):\n{block}"

    @pytest.mark.asyncio
    async def test_window_cap_is_reported_as_a_partial_read(self):
        import asyncio

        from app.services import case_law_research as clr

        text = "x" * (WINDOW_CHARS * 4)
        client = _client_seq([{"relevant": False}] * 2)
        with (
            patch.object(clr, "MAX_WINDOWS_PER_OPINION", 2),
            patch(
                "app.services.case_law_research.courtlistener_service.get_opinion",
                new=AsyncMock(return_value=SimpleNamespace(text=text)),
            ),
        ):
            verdict = await clr.judge_opinion(
                client,
                asyncio.Semaphore(1),
                _opinion(7),
                build_prompt=self._prompt,
                endorse_key="relevant",
                label="test",
            )

        assert verdict.reason == "unsupportive"
        assert verdict.partial is True
        # Exactly the capped number of windows was judged.
        assert client.chat.completions.create.await_count == 2

    @pytest.mark.asyncio
    async def test_short_opinion_is_not_partial(self):
        import asyncio

        from app.services import case_law_research as clr

        holding = "Late notice does not defeat coverage absent a showing of prejudice."
        with patch(
            "app.services.case_law_research.courtlistener_service.get_opinion",
            new=AsyncMock(return_value=SimpleNamespace(text=f"Intro. {holding} More.")),
        ):
            verdict = await clr.judge_opinion(
                _client_seq([{"relevant": True, "quote": holding}]),
                asyncio.Semaphore(1),
                _opinion(7),
                build_prompt=self._prompt,
                endorse_key="relevant",
                label="test",
            )

        assert verdict.reason == "attached"
        assert verdict.quote == holding
        assert verdict.partial is False


class TestResearchScores:
    """No constant confidence: the score is the judge's rating, or absent."""

    HOLDING = "Late notice does not defeat coverage absent a showing of prejudice."

    async def _research(self, judge: dict):
        with (
            patch(
                "app.services.case_law_research.courtlistener_service.search_opinions",
                new=AsyncMock(return_value=[_opinion(7)]),
            ),
            patch(
                "app.services.case_law_research.courtlistener_service.get_opinion",
                new=AsyncMock(return_value=SimpleNamespace(text=f"Intro. {self.HOLDING} More.")),
            ),
        ):
            return await research_authorities(
                "find case law on late notice", "late notice", _client_seq([CRAFT, judge])
            )

    @pytest.mark.asyncio
    async def test_judge_relevance_is_used_as_the_score(self):
        results, status = await self._research(
            {"relevant": True, "quote": self.HOLDING, "why": "On point.", "relevance": 0.62}
        )
        assert results[0]["similarity"] == 0.62
        assert status["partially_read"] == 0

    @pytest.mark.asyncio
    async def test_no_rating_means_no_score(self):
        results, _ = await self._research(
            {"relevant": True, "quote": self.HOLDING, "why": "On point."}
        )
        assert "similarity" not in results[0]
        assert results[0]["metadata"]["quote_verified"] is True

    @pytest.mark.asyncio
    async def test_out_of_range_rating_is_ignored(self):
        results, _ = await self._research(
            {"relevant": True, "quote": self.HOLDING, "why": "On point.", "relevance": 9}
        )
        assert "similarity" not in results[0]

    @pytest.mark.asyncio
    async def test_explanation_cannot_introduce_another_case(self):
        results, _ = await self._research(
            {
                "relevant": True,
                "quote": self.HOLDING,
                "why": "Follows Madeup v. Imaginary, 999 F.3d 1.",
            }
        )
        summary = results[0]["metadata"]["case_summary"]
        assert "Madeup" not in summary
        assert "unverified case-law reference removed" in summary


class TestRedactUnverifiedCaseReferences:
    def test_reference_found_in_a_source_is_kept(self):
        from app.services.case_law_research import redact_unverified_case_references

        text = "As in Smith v. Jones, 123 F.3d 456, notice matters."
        clean, removed = redact_unverified_case_references(
            text, sources=["The brief cites Smith v. Jones, 123 F.3d 456."]
        )
        assert clean == text
        assert removed == []

    def test_reference_found_nowhere_is_redacted_without_a_trailing_note(self):
        from app.services.case_law_research import redact_unverified_case_references

        clean, removed = redact_unverified_case_references(
            "Under Madeup v. Imaginary the clause fails.", sources=["Nothing relevant."]
        )
        assert "Madeup" not in clean
        assert clean.endswith("the clause fails.")
        assert len(removed) == 1

    def test_empty_text_and_none_sources_are_tolerated(self):
        from app.services.case_law_research import redact_unverified_case_references

        assert redact_unverified_case_references("", sources=[None]) == ("", [])
        assert redact_unverified_case_references("Plain prose.", sources=[None, ""]) == (
            "Plain prose.",
            [],
        )

    def test_a_heading_above_a_verified_reference_is_not_swallowed(self):
        """The party pattern spans whitespace; it must not span a line break."""
        from app.services.case_law_research import redact_unverified_case_references

        text = "1. DEFINITIONS\n\nPer Smith v. Jones, notice is required."
        clean, removed = redact_unverified_case_references(
            text, sources=["Our memo relies on Smith v. Jones throughout."]
        )
        assert clean == text
        assert removed == []

    def test_heading_survives_when_the_reference_under_it_is_removed(self):
        from app.services.case_law_research import redact_unverified_case_references

        clean, removed = redact_unverified_case_references(
            "ARGUMENT\n\nSee Madeup v. Imaginary for the rule.", sources=["nothing"]
        )
        assert clean.startswith("ARGUMENT\n\n")
        assert "Madeup" not in clean
        assert len(removed) == 1


class TestKnownPartyCaptions:
    """Drafted pleadings carry the caption of the user's own matter."""

    def test_caption_built_from_the_users_own_party_names_is_kept(self):
        from app.services.case_law_research import redact_unverified_case_references

        text = "Doe v. Acme Corp.\n\nCOMPLAINT\n\nPlaintiff alleges as follows."
        sources = ["Draft a complaint for John Doe against Acme Corp for unpaid wages."]
        strict, strict_removed = redact_unverified_case_references(text, sources=sources)
        assert strict_removed  # the chat rule would remove it
        clean, removed = redact_unverified_case_references(
            text, sources=sources, known_parties=True
        )
        assert clean == text
        assert removed == []

    def test_invented_case_is_still_removed(self):
        from app.services.case_law_research import redact_unverified_case_references

        clean, removed = redact_unverified_case_references(
            "See Madeup v. Imaginary for the rule.",
            sources=["Draft a complaint for John Doe against Acme Corp."],
            known_parties=True,
        )
        assert "Madeup" not in clean
        assert len(removed) == 1

    def test_invented_citation_on_a_known_caption_is_removed_but_the_caption_stays(self):
        from app.services.case_law_research import redact_unverified_case_references

        clean, removed = redact_unverified_case_references(
            "As in Doe v. Acme, 123 F.3d 456, wages are owed.",
            sources=["Draft a complaint for John Doe against Acme Corp."],
            known_parties=True,
        )
        assert "Doe v. Acme" in clean
        assert "123 F.3d 456" not in clean
        assert removed == ["123 F.3d 456"]
