"""Long-document drafting: plan → parallel sections → reconcile; scoped revision."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.services.contract_analysis import long_drafting as ld


def _response(content: str, finish_reason: str = "stop") -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.choices[0].finish_reason = finish_reason
    return response


def _client(handler):
    """A fake OpenAI client whose reply is computed from the request messages.

    The handler returns the reply text, or a ready-made ``_response`` when the
    test needs to control ``finish_reason``.
    """
    client = MagicMock()

    async def create(**kwargs):
        system = kwargs["messages"][0]["content"]
        user = kwargs["messages"][-1]["content"]
        out = handler(system, user, kwargs)
        return out if isinstance(out, MagicMock) else _response(out)

    client.chat.completions.create = AsyncMock(side_effect=create)
    return client


PLAN = {
    "title": "Master Services Agreement",
    "document_type": "MSA",
    "sections": [
        {
            "number": 1,
            "title": "Definitions",
            "brief": "Defined terms.",
            "exclude": "",
            "target_words": 400,
        },
        {
            "number": 2,
            "title": "Services",
            "brief": "Scope of services.",
            "exclude": "Fees (Section 3).",
            "target_words": 600,
        },
        {
            "number": 3,
            "title": "Fees",
            "brief": "Fees and invoicing.",
            "exclude": "Termination (Section 4).",
            "target_words": 500,
        },
        {
            "number": 4,
            "title": "Termination",
            "brief": "Termination rights.",
            "exclude": "",
            "target_words": 500,
        },
    ],
    "definitions": '"Supplier" means Acme Ltd. "Customer" means Widget Co.',
    "style_guide": "Numbered sections, defined terms capitalised.",
}


# ---------------------------------------------------------------------------
# Budgeting and references
# ---------------------------------------------------------------------------


class TestContextWindow:
    def test_known_models(self):
        assert ld.context_window_tokens("gpt-5.5") == 400_000
        assert ld.context_window_tokens("gpt-4o-mini") == 128_000
        assert ld.context_window_tokens("claude-sonnet-4") == 200_000

    def test_unknown_model_uses_default(self):
        assert ld.context_window_tokens("mystery-9000") == ld._DEFAULT_WINDOW

    def test_setting_overrides(self, monkeypatch):
        # Settings is frozen; swap the module's reference for a stand-in.
        monkeypatch.setattr(ld, "settings", SimpleNamespace(llm_context_window=32_000))
        assert ld.context_window_tokens("gpt-5.5") == 32_000


class TestReferenceBlock:
    def test_full_mode_when_everything_fits(self):
        text, mode = ld.build_reference_block([("MSA", "x" * 4000), ("SOW", "y" * 4000)], 10_000)
        assert mode == "full"
        assert "x" * 4000 in text and "y" * 4000 in text
        assert "=== MSA ===" in text and "=== SOW ===" in text

    def test_excerpt_mode_keeps_the_chunks_relevant_to_the_focus(self):
        indemnity = "\n\n".join(["The Supplier shall indemnify the Customer against claims."] * 400)
        payment = "\n\n".join(["Fees are payable within thirty days of invoice."] * 400)
        refs = [("MSA", indemnity + "\n\n" + payment)]
        budget = ld.estimate_tokens(payment) // 2  # a fraction of the whole document
        text, mode = ld.build_reference_block(refs, budget, focus="Fees and invoicing payment")
        assert mode == "excerpts"
        assert "(excerpts)" in text
        assert "payable within thirty days" in text
        assert text.count("indemnify") < text.count("payable")
        assert ld.estimate_tokens(text) <= budget + 50

    def test_empty_references(self):
        assert ld.build_reference_block([], 1000) == ("", "none")


class TestNormalizePlan:
    def test_scales_section_words_to_the_target(self):
        plan = ld.normalize_plan(PLAN, target_words=4000)
        assert plan["target_words"] == 4000
        assert [s["number"] for s in plan["sections"]] == [1, 2, 3, 4]

    def test_rejects_planless_input(self):
        with pytest.raises(RuntimeError):
            ld.normalize_plan({"title": "x", "sections": []})

    def test_fills_missing_word_counts(self):
        data = {"sections": [{"title": "A"}, {"title": "B"}]}
        plan = ld.normalize_plan(data, target_words=1000)
        assert [s["target_words"] for s in plan["sections"]] == [500, 500]


# ---------------------------------------------------------------------------
# Phase 1 — plan
# ---------------------------------------------------------------------------


class TestPlanDocument:
    @pytest.mark.asyncio
    async def test_plan_reads_full_references_and_parses_json(self):
        seen = {}

        def handler(system, user, kwargs):
            seen["user"] = user
            seen["format"] = kwargs.get("response_format")
            return json.dumps(PLAN)

        client = _client(handler)
        plan = await ld.plan_document(
            client,
            instructions="Draft an MSA",
            references=[("Old MSA", "The Supplier shall provide the Services. " * 500)],
            target_pages=10,
        )
        assert seen["format"] == {"type": "json_object"}
        assert "=== Old MSA ===" in seen["user"]
        assert seen["user"].count("The Supplier shall provide") == 500  # not truncated
        assert "about 10 pages" in seen["user"]
        assert plan["references_mode"] == "full"
        assert len(plan["sections"]) == 4
        assert plan["target_words"] == 10 * ld.WORDS_PER_PAGE

    @pytest.mark.asyncio
    async def test_plan_survives_code_fences(self):
        client = _client(lambda s, u, k: "```json\n" + json.dumps(PLAN) + "\n```")
        plan = await ld.plan_document(client, instructions="x", references=[], target_pages=3)
        assert plan["title"] == "Master Services Agreement"

    @pytest.mark.asyncio
    async def test_plan_failure_is_a_clean_runtime_error(self):
        client = MagicMock()
        client.chat.completions.create = AsyncMock(side_effect=ConnectionError("down"))
        with pytest.raises(RuntimeError, match="planning failed"):
            await ld.plan_document(client, instructions="x", references=[], target_pages=3)


# ---------------------------------------------------------------------------
# Phase 2/3 — sections in parallel, then reconcile
# ---------------------------------------------------------------------------


def _section_or_reconcile(system, user, kwargs, *, in_flight=None, peak=None):
    if "senior reviewer" in system:
        return (
            user.replace("DOCUMENT:\n", "", 1)
            + "\n=== RECONCILE NOTES ===\n- Fixed a cross-reference."
        )
    m = ld.re.search(r"YOUR SECTION: (\d+)\. ([^\n]+)", user)
    return f"{m.group(1)}. {m.group(2).upper()}\n\nBody of section {m.group(1)}."


class TestGenerateFromPlan:
    @pytest.mark.asyncio
    async def test_every_section_sees_references_plan_definitions_and_its_brief(self):
        prompts = []

        def handler(system, user, kwargs):
            if "senior reviewer" not in system:
                prompts.append(user)
            return _section_or_reconcile(system, user, kwargs)

        client = _client(handler)
        refs = [("Old MSA", "Reference contract text. " * 200)]
        result = await ld.generate_from_plan(
            client, plan=PLAN, instructions="Draft an MSA", references=refs
        )
        assert len(prompts) == 4
        for user in prompts:
            assert "=== Old MSA ===" in user
            assert "DEFINITIONS (use exactly)" in user and "Acme Ltd" in user
            assert "STYLE GUIDE" in user
            # Every section knows the whole plan, including the others' briefs.
            for s in PLAN["sections"]:
                assert f"{s['number']}. {s['title']}" in user
        assert any("EXCLUDE (owned by other sections): Fees (Section 3)." in u for u in prompts)
        # Same shared prefix across sections — the cacheable part.
        prefixes = {u.split("YOUR SECTION")[0] for u in prompts}
        assert len(prefixes) == 1
        assert result["references_mode"] == "full"

    @pytest.mark.asyncio
    async def test_sections_run_in_parallel_and_assemble_in_order(self):
        in_flight = 0
        peak = 0
        prompts_seen = 0

        client = MagicMock()

        async def create(**kwargs):
            nonlocal in_flight, peak, prompts_seen
            system = kwargs["messages"][0]["content"]
            user = kwargs["messages"][-1]["content"]
            if "senior reviewer" not in system:
                in_flight += 1
                peak = max(peak, in_flight)
                prompts_seen += 1
                await asyncio.sleep(0.01)
                in_flight -= 1
            return _response(_section_or_reconcile(system, user, kwargs))

        client.chat.completions.create = AsyncMock(side_effect=create)
        result = await ld.generate_from_plan(
            client, plan=PLAN, instructions="x", references=[], concurrency=3
        )
        assert prompts_seen == 4
        assert 1 < peak <= 3
        text = result["text"]
        assert text.startswith("Master Services Agreement")
        assert text.index("1. DEFINITIONS") < text.index("2. SERVICES") < text.index("3. FEES")
        assert [s["number"] for s in result["sections"]] == [1, 2, 3, 4]
        assert result["reconcile_notes"] == ["Fixed a cross-reference."]

    @pytest.mark.asyncio
    async def test_reports_progress(self):
        events = []

        async def progress(message, fraction):
            events.append((message, fraction))

        client = _client(_section_or_reconcile)
        await ld.generate_from_plan(
            client, plan=PLAN, instructions="x", references=[], progress=progress
        )
        assert any("Drafted section" in m for m, _ in events)
        assert any("Reconciling" in m for m, _ in events)
        assert all(0 <= f <= 1 for _, f in events)

    @pytest.mark.asyncio
    async def test_reconcile_that_shortens_the_document_is_discarded(self):
        def handler(system, user, kwargs):
            if "senior reviewer" in system:
                return "Much shorter.\n=== RECONCILE NOTES ===\n- Summarised everything."
            return _section_or_reconcile(system, user, kwargs)

        client = _client(handler)
        result = await ld.generate_from_plan(client, plan=PLAN, instructions="x", references=[])
        assert "Body of section 4." in result["text"]
        assert "discarded" in result["reconcile_notes"][0]

    @pytest.mark.asyncio
    async def test_reconcile_failure_keeps_the_assembled_draft(self):
        def handler(system, user, kwargs):
            if "senior reviewer" in system:
                raise ConnectionError("down")
            return _section_or_reconcile(system, user, kwargs)

        client = _client(handler)
        result = await ld.generate_from_plan(client, plan=PLAN, instructions="x", references=[])
        assert "Body of section 1." in result["text"]
        assert "failed" in result["reconcile_notes"][0]

    @pytest.mark.asyncio
    async def test_section_failure_after_retries_fails_the_draft(self, monkeypatch):
        monkeypatch.setattr(ld.asyncio, "sleep", AsyncMock())

        def handler(system, user, kwargs):
            if "YOUR SECTION: 3." in user:
                raise ConnectionError("down")
            return _section_or_reconcile(system, user, kwargs)

        client = _client(handler)
        with pytest.raises(RuntimeError, match="Section 3"):
            await ld.generate_from_plan(client, plan=PLAN, instructions="x", references=[])

    # -- Reconcile integrity: nothing may vanish between assembly and output --

    @staticmethod
    def _long_section_or_reconcile(system, user, kwargs, *, reconcile=None):
        """Sections with real bodies; ``reconcile`` mutates the echoed document."""
        if "senior reviewer" in system:
            doc = user.replace("DOCUMENT:\n", "", 1)
            if reconcile is not None:
                doc = reconcile(doc)
            return doc + "\n=== RECONCILE NOTES ===\n- Fixed a cross-reference."
        m = ld.re.search(r"YOUR SECTION: (\d+)\. ([^\n]+)", user)
        n = m.group(1)
        return f"{n}. {m.group(2).upper()}\n\n" + f"Clause text of section {n}. " * 40

    @pytest.mark.asyncio
    async def test_reconcile_that_drops_a_section_heading_is_rejected(self):
        def reconcile(doc):
            # The heading line for section 3 disappears; its body is merged into 2.
            return doc.replace("3. FEES\n\n", "", 1)

        client = _client(
            lambda s, u, k: self._long_section_or_reconcile(s, u, k, reconcile=reconcile)
        )
        result = await ld.generate_from_plan(client, plan=PLAN, instructions="x", references=[])
        assert "3. FEES" in result["text"]  # the assembled document was kept
        assert result["text"].count("Clause text of section 3.") == 40
        note = result["reconcile_notes"][0]
        assert "discarded" in note and "section 3" in note and "Fees" in note
        assert "heading is missing" in note

    @pytest.mark.asyncio
    async def test_reconcile_that_shortens_one_section_is_rejected(self):
        def reconcile(doc):
            # Section 2 loses 40% of its clauses; the whole document is still >80%.
            full = ("Clause text of section 2. " * 40).strip()
            assert full in doc
            return doc.replace(full, ("Clause text of section 2. " * 24).strip(), 1)

        client = _client(
            lambda s, u, k: self._long_section_or_reconcile(s, u, k, reconcile=reconcile)
        )
        result = await ld.generate_from_plan(client, plan=PLAN, instructions="x", references=[])
        assert result["text"].count("Clause text of section 2.") == 40
        note = result["reconcile_notes"][0]
        assert "discarded" in note and "section 2" in note and "shorter" in note

    @pytest.mark.asyncio
    async def test_reconcile_within_tolerance_is_accepted(self):
        def reconcile(doc):
            # A genuine reconcile edit: one clause becomes a cross-reference.
            full = ("Clause text of section 2. " * 40).strip()
            assert full in doc
            return doc.replace(
                full, "Clause text of section 2. " * 38 + "Subject to Section 3.", 1
            )

        client = _client(
            lambda s, u, k: self._long_section_or_reconcile(s, u, k, reconcile=reconcile)
        )
        result = await ld.generate_from_plan(client, plan=PLAN, instructions="x", references=[])
        assert "Subject to Section 3." in result["text"]
        assert result["reconcile_notes"] == ["Fixed a cross-reference."]

    @pytest.mark.asyncio
    async def test_reconcile_cut_off_by_the_length_limit_keeps_the_assembled_draft(self):
        def handler(system, user, kwargs):
            if "senior reviewer" in system:
                doc = user.replace("DOCUMENT:\n", "", 1)
                # Truncated mid-document: no notes marker, finish_reason "length".
                return _response(doc[: len(doc) * 9 // 10], finish_reason="length")
            return self._long_section_or_reconcile(system, user, kwargs)

        client = _client(handler)
        result = await ld.generate_from_plan(client, plan=PLAN, instructions="x", references=[])
        assert result["text"].count("Clause text of section 4.") == 40
        note = result["reconcile_notes"][0]
        assert "discarded" in note and "cut off" in note

    @pytest.mark.asyncio
    async def test_truncated_section_is_retried_then_fails_the_draft(self, monkeypatch):
        monkeypatch.setattr(ld.asyncio, "sleep", AsyncMock())
        attempts = 0

        def handler(system, user, kwargs):
            nonlocal attempts
            if "YOUR SECTION: 3." in user:
                attempts += 1
                return _response("3. FEES\n\nThe Customer shall pay", finish_reason="length")
            return _section_or_reconcile(system, user, kwargs)

        client = _client(handler)
        with pytest.raises(RuntimeError, match="Section 3") as exc:
            await ld.generate_from_plan(client, plan=PLAN, instructions="x", references=[])
        assert attempts == 3  # retried, never accepted
        assert "cut off" in str(exc.value)

    def test_check_reconciled_sections_accepts_the_drafted_document(self):
        sections = [
            {"number": 1, "title": "Definitions", "text": "1. DEFINITIONS\n\n" + "a " * 300},
            {"number": 2, "title": "Services", "text": "2. Services\n\n" + "b " * 300},
        ]
        doc = "Title\n\n" + "\n\n".join(s["text"] for s in sections)
        assert ld.check_reconciled_sections(doc, sections) is None
        # Headings are matched case-insensitively, by plan title or drafted heading.
        assert ld.check_reconciled_sections(doc.replace("1. DEFINITIONS", "1. Definitions"), sections) is None
        # Out-of-order headings are a violation too.
        swapped = "Title\n\n" + sections[1]["text"] + "\n\n" + sections[0]["text"]
        assert "heading is missing" in ld.check_reconciled_sections(swapped, sections)

    @pytest.mark.asyncio
    async def test_excerpt_mode_focuses_each_section(self, monkeypatch):
        # A window too small for the whole bundle forces per-section excerpts.
        monkeypatch.setattr(ld, "context_window_tokens", lambda model=None: 6_000)
        prompts = []

        def handler(system, user, kwargs):
            if "senior reviewer" not in system:
                prompts.append(user)
            return _section_or_reconcile(system, user, kwargs)

        fees = "\n\n".join(["Fees are payable within thirty days of invoice."] * 60)
        termination = "\n\n".join(["Either party may terminate for material breach."] * 60)
        client = _client(handler)
        result = await ld.generate_from_plan(
            client, plan=PLAN, instructions="x", references=[("MSA", fees + "\n\n" + termination)]
        )
        assert result["references_mode"] == "excerpts"
        fees_prompt = next(u for u in prompts if "YOUR SECTION: 3." in u)
        term_prompt = next(u for u in prompts if "YOUR SECTION: 4." in u)
        assert fees_prompt.count("payable") > fees_prompt.count("terminate")
        assert term_prompt.count("terminate") > term_prompt.count("payable")


# ---------------------------------------------------------------------------
# Revision
# ---------------------------------------------------------------------------


def _long_draft(n_sections: int = 5, filler: int = 9000) -> str:
    parts = ["MASTER SERVICES AGREEMENT"]
    for i in range(1, n_sections + 1):
        parts.append(
            f"{i}. SECTION {i} TITLE\n\n" + f"Clause text of section {i}. " * (filler // 26)
        )
    return "\n\n".join(parts)


class TestSplitSections:
    def test_finds_top_level_numbered_sections(self):
        text = _long_draft(4)
        sections = ld.split_sections(text)
        assert [s["number"] for s in sections] == [1, 2, 3, 4]
        assert text[sections[1]["start"] : sections[1]["end"]].startswith("2. SECTION 2")

    def test_ignores_numbered_lists_that_do_not_form_a_sequence(self):
        text = "1. FIRST\n\nbody\n\n5. not a section\n\n2. SECOND\n\nbody"
        assert ld.split_sections(text) == []  # fewer than three real sections


class TestReviseDraft:
    @pytest.mark.asyncio
    async def test_short_draft_is_revised_in_one_pass(self, monkeypatch):
        called = {}

        async def fake_draft_document(client, instructions, reference_text=None, revision_of=None):
            called["revision_of"] = revision_of
            return {"title": "T", "text": "revised"}

        monkeypatch.setattr(
            "app.services.contract_analysis.drafting.draft_document", fake_draft_document
        )
        client = _client(lambda s, u, k: "unused")
        result = await ld.revise_draft(client, draft_text="short draft", instructions="change it")
        assert called["revision_of"] == "short draft"
        assert result["revised_sections"] == "all"

    @pytest.mark.asyncio
    async def test_quoted_clause_routes_to_its_section_only(self):
        draft = _long_draft(5)
        quoted = "Clause text of section 3. Clause text of section 3."
        calls = []

        def handler(system, user, kwargs):
            calls.append((system, user))
            assert "revising ONE section" in system
            assert "SECTION TO REVISE: 3." in user
            assert "FULL DOCUMENT" in user and "Clause text of section 5." in user
            return "3. SECTION 3 TITLE\n\nRewritten clause."

        client = _client(handler)
        result = await ld.revise_draft(
            client,
            draft_text=draft,
            instructions=f'Rewrite this clause — keep every other part unchanged:\n"{quoted}"',
        )
        assert len(calls) == 1  # no routing call needed, no other section touched
        assert result["revised_sections"] == [3]
        text = result["text"]
        assert "Rewritten clause." in text
        assert "Clause text of section 3." not in text
        assert text.count("Clause text of section 2.") == draft.count("Clause text of section 2.")
        assert text.count("Clause text of section 4.") == draft.count("Clause text of section 4.")

    @pytest.mark.asyncio
    async def test_routing_call_picks_sections(self):
        draft = _long_draft(5)

        def handler(system, user, kwargs):
            if "route a revision instruction" in system:
                assert kwargs.get("response_format") == {"type": "json_object"}
                return json.dumps({"sections": [2, 4]})
            m = ld.re.search(r"SECTION TO REVISE: (\d+)", user)
            return f"{m.group(1)}. SECTION {m.group(1)} TITLE\n\nNew text for {m.group(1)}."

        client = _client(handler)
        result = await ld.revise_draft(client, draft_text=draft, instructions="Add a cure period")
        assert result["revised_sections"] == [2, 4]
        assert "New text for 2." in result["text"] and "New text for 4." in result["text"]
        assert "Clause text of section 3." in result["text"]

    @pytest.mark.asyncio
    async def test_whole_document_change_falls_back_to_full_revision(self, monkeypatch):
        draft = _long_draft(5)

        async def fake_draft_document(client, instructions, reference_text=None, revision_of=None):
            return {"title": "T", "text": "all revised"}

        monkeypatch.setattr(
            "app.services.contract_analysis.drafting.draft_document", fake_draft_document
        )
        client = _client(lambda s, u, k: json.dumps({"sections": "all"}))
        result = await ld.revise_draft(client, draft_text=draft, instructions="Rename the Supplier")
        assert result["text"] == "all revised"
        assert result["revised_sections"] == "all"
