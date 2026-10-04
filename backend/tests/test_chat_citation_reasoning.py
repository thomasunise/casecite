"""
Tests for the post-answer citation reasoning pass (services/rag/citation_reasoning).

Pure-function tests for prompt/ref building, payload normalization, and the
join-by-ref logic, plus mocked-LLM tests of the enrichment orchestrator:
happy path, omitted refs, garbage payload, and total LLM failure.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

import json
from unittest.mock import AsyncMock, Mock, patch

from app.models.schemas import Citation, CitationLogic, ReasoningStep
from app.services.rag.citation_reasoning import (
    MAX_REASONING_STEPS,
    SNIPPET_LIMIT,
    apply_citation_reasoning,
    build_citation_refs,
    build_reasoning_prompt,
    enrich_citations_with_reasoning,
    join_reasoning_by_ref,
    normalize_reasoning_steps,
)


def make_citation(source="contract.pdf", type_="document", passage="The term is 30 days."):
    """Build a minimal Citation the way the RAG pipeline does (templated reasoning)."""
    return Citation(
        id="cit-1",
        source=source,
        type=type_,
        confidence=90,
        similarity=0.9,
        relevance_rank=1,
        chunk_index=0,
        token_count=10,
        passage=passage,
        reasoning=[ReasoningStep(type="Semantic Matching", description="templated", evidence=None)],
        logic=CitationLogic(
            query_intent="q",
            matching_criteria="m",
            application="templated application",
        ),
    )


class TestBuildRefs:
    """Server-assigned refs and compact snippets."""

    def test_refs_are_positional_and_snippets_truncated(self):
        citations = [
            make_citation(source="a.pdf", passage="word " * 200),
            make_citation(source="Smith v. Jones", type_="case_law", passage="short excerpt"),
        ]
        refs = build_citation_refs(citations)

        assert [r["ref"] for r in refs] == ["c0", "c1"]
        assert refs[0]["source"] == "a.pdf"
        assert len(refs[0]["snippet"]) <= SNIPPET_LIMIT
        assert refs[1]["type"] == "case_law"
        assert refs[1]["snippet"] == "short excerpt"

    def test_snippet_whitespace_is_collapsed_and_empty_passage_ok(self):
        citations = [make_citation(passage="line1\n\n  line2\tline3"), make_citation(passage="")]
        refs = build_citation_refs(citations)
        assert refs[0]["snippet"] == "line1 line2 line3"
        assert refs[1]["snippet"] == ""

    def test_prompt_includes_question_answer_and_all_refs(self):
        refs = build_citation_refs([make_citation(), make_citation(source="b.pdf")])
        prompt = build_reasoning_prompt("my question", "x" * 5000, refs)
        assert "my question" in prompt
        assert "[c0]" in prompt and "[c1]" in prompt
        # Answer is truncated to ~4000 chars
        assert "x" * 4000 in prompt
        assert "x" * 4001 not in prompt


class TestNormalizeReasoningSteps:
    """_clean-style normalization of the per-citation reasoning list."""

    def test_happy_path(self):
        steps = normalize_reasoning_steps(
            [
                {"type": "Claim", "description": "The answer asserts X.", "evidence": "quote"},
                {"type": "Support", "description": "The source states X.", "evidence": None},
            ]
        )
        assert steps == [
            {"type": "Claim", "description": "The answer asserts X.", "evidence": "quote"},
            {"type": "Support", "description": "The source states X.", "evidence": None},
        ]

    def test_drops_empty_descriptions_and_caps_type_length(self):
        steps = normalize_reasoning_steps(
            [
                {"type": "T" * 80, "description": "kept"},
                {"type": "Support", "description": "   "},
                {"type": "", "description": "typed fallback"},
                "not-a-dict",
            ]
        )
        assert len(steps) == 2
        assert steps[0]["type"] == "T" * 40
        assert steps[1]["type"] == "Analysis"
        assert steps[1]["evidence"] is None

    def test_caps_step_count_and_rejects_non_list(self):
        many = [{"type": "S", "description": f"step {i}"} for i in range(10)]
        assert len(normalize_reasoning_steps(many)) == MAX_REASONING_STEPS
        assert normalize_reasoning_steps("garbage") == []
        assert normalize_reasoning_steps(None) == []
        assert normalize_reasoning_steps({"description": "dict not list"}) == []


class TestJoinByRef:
    """Joining the LLM payload back onto server refs."""

    def test_happy_path_joins_all_refs(self):
        payload = {
            "citations": [
                {
                    "ref": "c0",
                    "reasoning": [{"type": "Support", "description": "d0", "evidence": "e0"}],
                    "application": "Supports the 30-day term.",
                },
                {
                    "ref": "c1",
                    "reasoning": [{"type": "Holding", "description": "d1"}],
                    "application": "Provides precedent.",
                },
            ]
        }
        joined = join_reasoning_by_ref(payload, ["c0", "c1"])
        assert joined["c0"]["application"] == "Supports the 30-day term."
        assert joined["c0"]["reasoning"][0]["evidence"] == "e0"
        assert joined["c1"]["reasoning"][0]["type"] == "Holding"

    def test_omitted_refs_get_empty_reasoning(self):
        payload = {
            "citations": [
                {"ref": "c0", "reasoning": [{"type": "S", "description": "d"}], "application": "a"}
            ]
        }
        joined = join_reasoning_by_ref(payload, ["c0", "c1", "c2"])
        assert joined["c0"]["application"] == "a"
        assert joined["c1"] == {"reasoning": [], "application": None}
        assert joined["c2"] == {"reasoning": [], "application": None}

    def test_garbage_payloads_yield_all_empty(self):
        for payload in ("not json-shaped", None, [], {"citations": "nope"}, {"other": 1}):
            joined = join_reasoning_by_ref(payload, ["c0", "c1"])
            assert joined == {
                "c0": {"reasoning": [], "application": None},
                "c1": {"reasoning": [], "application": None},
            }

    def test_invented_refs_and_garbage_items_are_ignored(self):
        payload = {
            "citations": [
                "garbage-item",
                {"ref": "c99", "reasoning": [], "application": "invented"},
                {"reasoning": [], "application": "no ref"},
                {"ref": "c0", "reasoning": "garbage", "application": "   "},
            ]
        }
        joined = join_reasoning_by_ref(payload, ["c0"])
        # c0 was matched but its reasoning was garbage and application blank
        assert joined["c0"] == {"reasoning": [], "application": None}

    def test_apply_attaches_reasoning_and_application(self):
        citations = [make_citation(), make_citation(source="b.pdf")]
        joined = {
            "c0": {
                "reasoning": [{"type": "Support", "description": "d", "evidence": "e"}],
                "application": "app sentence",
            },
            "c1": {"reasoning": [], "application": None},
        }
        apply_citation_reasoning(citations, joined)

        assert citations[0].application == "app sentence"
        assert [s.model_dump() for s in citations[0].reasoning] == [
            {"type": "Support", "description": "d", "evidence": "e"}
        ]
        assert citations[1].reasoning == []
        assert citations[1].application is None


def _mock_llm_client(content: str):
    """Async OpenAI client double whose chat completion returns `content`."""
    client = Mock()
    response = Mock()
    response.choices = [Mock(message=Mock(content=content))]
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


class TestEnrichCitations:
    """Mocked-LLM tests of the orchestrator (one call per chat request)."""

    async def test_happy_path_enriches_document_and_case_law_citations(self):
        citations = [make_citation(), make_citation(source="Smith v. Jones", type_="case_law")]
        payload = json.dumps(
            {
                "citations": [
                    {
                        "ref": "c0",
                        "reasoning": [
                            {"type": "Claim", "description": "Answer says 30 days."},
                            {"type": "Support", "description": "Doc states it.", "evidence": "30"},
                        ],
                        "application": "Directly supports the stated term.",
                    },
                    {
                        "ref": "c1",
                        "reasoning": [{"type": "Holding", "description": "Case held same."}],
                        "application": "Precedential support.",
                    },
                ]
            }
        )
        client = _mock_llm_client(payload)
        with patch(
            "app.services.rag.citation_reasoning.make_openai", return_value=client
        ) as mock_make:
            await enrich_citations_with_reasoning(citations, "q", "answer text")

        # Exactly ONE utility call for the whole request
        assert client.chat.completions.create.await_count == 1
        mock_make.assert_called_once()
        assert citations[0].application == "Directly supports the stated term."
        assert len(citations[0].reasoning) == 2
        assert citations[0].reasoning[1].evidence == "30"
        assert citations[1].application == "Precedential support."
        assert citations[1].reasoning[0].type == "Holding"

    async def test_llm_failure_leaves_empty_reasoning_and_never_raises(self):
        citations = [make_citation(), make_citation(source="b.pdf")]
        client = Mock()
        client.chat.completions.create = AsyncMock(side_effect=ConnectionError("boom"))
        with patch("app.services.rag.citation_reasoning.make_openai", return_value=client):
            await enrich_citations_with_reasoning(citations, "q", "a")

        for c in citations:
            assert c.reasoning == []
            assert c.application is None

    async def test_garbage_llm_output_leaves_empty_reasoning(self):
        citations = [make_citation()]
        client = _mock_llm_client("this is not json {{{")
        with patch("app.services.rag.citation_reasoning.make_openai", return_value=client):
            await enrich_citations_with_reasoning(citations, "q", "a")
        assert citations[0].reasoning == []
        assert citations[0].application is None

    async def test_no_client_available_leaves_empty_reasoning(self):
        citations = [make_citation()]
        with patch("app.services.rag.citation_reasoning.make_openai", return_value=None):
            await enrich_citations_with_reasoning(citations, "q", "a")
        assert citations[0].reasoning == []
        assert citations[0].application is None

    async def test_zero_citations_skips_the_llm_call_entirely(self):
        with patch("app.services.rag.citation_reasoning.make_openai") as mock_make:
            await enrich_citations_with_reasoning([], "q", "a")
        mock_make.assert_not_called()
