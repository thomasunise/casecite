"""
Authority mapper: the whole document and whole opinions are read, in windows,
and whatever the bounds leave out is reported.
"""

import json
import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.authority_mapper import service as mapper
from app.services.authority_mapper.service import AuthorityMapperService, _windows


def _client(handler) -> MagicMock:
    """Fake OpenAI client: ``handler(prompt)`` returns the JSON payload to reply with."""
    client = MagicMock()

    async def create(**kwargs):
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = json.dumps(handler(kwargs["messages"][0]["content"]))
        return response

    client.chat.completions.create = AsyncMock(side_effect=create)
    return client


class TestWindows:
    def test_short_text_is_one_window(self):
        assert _windows("short", 4) == (["short"], 5)

    def test_long_text_is_fully_covered_with_overlap(self):
        text = "".join(chr(65 + i % 26) for i in range(mapper.WINDOW_CHARS * 2 + 500))
        windows, covered = _windows(text, 10)
        assert covered == len(text)
        assert len(windows) == 3
        # Each window starts inside the previous one, so nothing falls in a gap.
        assert windows[0][-mapper.WINDOW_OVERLAP :] == windows[1][: mapper.WINDOW_OVERLAP]
        assert text.endswith(windows[-1])

    def test_cap_reports_how_much_was_covered(self):
        text = "x" * (mapper.WINDOW_CHARS * 5)
        windows, covered = _windows(text, 2)
        assert len(windows) == 2
        assert covered < len(text)


class TestPropositionExtraction:
    @pytest.mark.asyncio
    async def test_text_beyond_the_first_window_is_read(self):
        """The old behaviour read 18,000 characters and stopped."""
        late = "The limitation period was tolled by the defendant's concealment."
        text = ("Background facts. " * 5000) + late
        assert len(text) > mapper.WINDOW_CHARS
        seen_parts: list[str] = []

        def handler(prompt: str) -> dict:
            seen_parts.append(prompt)
            if late in prompt:
                return {
                    "propositions": [
                        {"proposition": "Tolling applies.", "doc_quote": late, "query": "tolling"}
                    ]
                }
            return {"propositions": []}

        props, coverage = await AuthorityMapperService()._extract_propositions(
            _client(handler), text
        )

        assert [p["doc_quote"] for p in props] == [late]
        assert len(seen_parts) >= 2
        assert coverage["document_chars_read"] == len(text)
        assert coverage["document_truncated"] is False
        # Document text is delimited as untrusted data.
        assert "<<<BEGIN DOCUMENT" in seen_parts[0]

    @pytest.mark.asyncio
    async def test_propositions_are_drawn_from_every_window_and_the_cap_is_reported(self):
        text = "y" * (mapper.WINDOW_CHARS * 2)
        calls = {"n": 0}

        def handler(prompt: str) -> dict:
            calls["n"] += 1
            window = calls["n"]
            return {
                "propositions": [
                    {"proposition": f"W{window} P{i}", "doc_quote": f"w{window}q{i}", "query": "q"}
                    for i in range(6)
                ]
            }

        props, coverage = await AuthorityMapperService()._extract_propositions(
            _client(handler), text
        )

        assert len(props) == mapper.MAX_PROPOSITIONS
        windows_represented = {p["proposition"].split()[0] for p in props}
        assert len(windows_represented) == calls["n"] >= 2
        assert coverage["propositions_identified"] == 6 * calls["n"]
        assert coverage["propositions_researched"] == mapper.MAX_PROPOSITIONS

    @pytest.mark.asyncio
    async def test_window_cap_marks_the_document_truncated(self):
        text = "z" * (mapper.WINDOW_CHARS * 4)
        with patch.object(mapper, "MAX_DOCUMENT_WINDOWS", 1):
            _props, coverage = await AuthorityMapperService()._extract_propositions(
                _client(lambda _p: {"propositions": []}), text
            )
        assert coverage["document_truncated"] is True
        assert coverage["document_chars_read"] == mapper.WINDOW_CHARS

    @pytest.mark.asyncio
    async def test_one_failed_window_does_not_lose_the_others(self):
        text = "y" * (mapper.WINDOW_CHARS * 2)
        calls = {"n": 0}

        def handler(prompt: str) -> dict:
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("provider hiccup")
            return {"propositions": [{"proposition": "P", "doc_quote": "q", "query": "q"}]}

        props, coverage = await AuthorityMapperService()._extract_propositions(
            _client(handler), text
        )
        assert len(props) == 1
        assert coverage["document_windows_failed"] == 1

    @pytest.mark.asyncio
    async def test_every_window_failing_is_an_error(self):
        def handler(prompt: str) -> dict:
            raise ConnectionError("provider down")

        with pytest.raises(ConnectionError):
            await AuthorityMapperService()._extract_propositions(_client(handler), "short doc")


class TestSupportCheck:
    @pytest.mark.asyncio
    async def test_support_past_the_first_window_of_an_opinion_is_found(self):
        """The old behaviour read 14,000 characters of each opinion."""
        holding = "We hold that fraudulent concealment tolls the limitation period."
        opinion = ("Procedural history. " * 4000) + holding
        assert len(opinion) > mapper.WINDOW_CHARS

        def handler(prompt: str) -> dict:
            if holding in prompt:
                return {"supports": True, "quote": holding, "relevance": 0.9}
            return {"supports": False}

        res = await AuthorityMapperService()._check_support(
            _client(handler), "Tolling applies.", "Smith v. Jones", opinion
        )
        assert res["supports"] is True
        assert res["quote"] == holding

    @pytest.mark.asyncio
    async def test_unsupportive_opinion_longer_than_the_cap_is_flagged_partial(self):
        opinion = "w" * (mapper.WINDOW_CHARS * 6)
        client = _client(lambda _p: {"supports": False})
        with patch.object(mapper, "MAX_OPINION_WINDOWS", 2):
            res = await AuthorityMapperService()._check_support(
                client, "Tolling applies.", "Smith v. Jones", opinion
            )
        assert not res.get("supports")
        assert res["partially_read"] is True
        assert client.chat.completions.create.await_count == 2

    @pytest.mark.asyncio
    async def test_short_unsupportive_opinion_is_not_partial(self):
        res = await AuthorityMapperService()._check_support(
            _client(lambda _p: {"supports": False}), "P", "Case", "A short opinion."
        )
        assert res["partially_read"] is False


class TestAnalyzeReportsCoverage:
    @pytest.mark.asyncio
    async def test_summary_carries_coverage(self):
        quote = "Notice must be given within thirty days."
        holding = "Late notice bars the claim only on a showing of prejudice."

        def handler(prompt: str) -> dict:
            if "litigation research assistant" in prompt:
                return {
                    "propositions": [
                        {"proposition": "Notice rule.", "doc_quote": quote, "query": "notice"}
                    ]
                }
            return {"supports": True, "quote": holding, "relevance": 0.8}

        service = AuthorityMapperService()
        service._courtlistener_candidates = AsyncMock(
            return_value=[("courtlistener", "A v. B", "1 F.3d 1", "9", "https://x", holding)]
        )
        session = MagicMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=session)
        session_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(mapper, "make_openai", return_value=_client(handler)),
            patch.object(mapper, "AsyncSessionLocal", return_value=session_cm),
        ):
            result = await service.analyze(
                text=f"Clause 4. {quote}",
                document_name="lease.pdf",
                document_id="doc-1",
                jurisdiction=None,
                user_id="u1",
            )

        coverage = result["summary"]["coverage"]
        assert coverage["document_truncated"] is False
        assert coverage["propositions_researched"] == 1
        assert coverage["opinions_checked"] == 1
        assert coverage["opinions_partially_read"] == 0
        assert result["mappings"][0]["verified"] == 1
        # The persisted run carries the same summary.
        run = session.add.call_args_list[0].args[0]
        assert run.summary["coverage"] == coverage
