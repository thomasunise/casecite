"""
Tests for the rule-based Phase 2 extractors.

Sources:
  backend/app/services/contract_analysis/obligations.py
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from app.services.contract_analysis.deadlines import ExtractedDeadline  # noqa: E402
from app.services.contract_analysis.obligations import (  # noqa: E402
    extract_obligations,
    link_deadlines,
)
from app.services.contract_analysis.parties import ResolvedParty  # noqa: E402

PARTIES = [
    ResolvedParty(canonical_name="Provider", role="provider", aliases=["Provider"]),
    ResolvedParty(canonical_name="Customer", role="customer", aliases=["Customer"]),
]


class TestObligationExtraction:
    def test_may_is_not_an_obligation(self):
        text = "Customer may inspect the premises at any reasonable time."
        assert extract_obligations(text, PARTIES) == []

    def test_should_is_not_an_obligation(self):
        text = "Provider should endeavor to respond within one business day."
        assert extract_obligations(text, PARTIES) == []

    def test_shall_is_an_obligation(self):
        text = "Customer shall pay all invoices within thirty days of receipt."
        obs = extract_obligations(text, PARTIES)
        assert len(obs) == 1
        assert obs[0].modal == "shall"
        assert obs[0].subject_party == "Customer"
        assert obs[0].span_start == 0
        assert obs[0].span_end == len(text)

    def test_mixed_sentences_keep_only_obligations(self):
        text = (
            "Customer may inspect the premises at any time. "
            "Customer shall pay rent of $2,000 per month."
        )
        obs = extract_obligations(text, PARTIES)
        assert len(obs) == 1
        assert obs[0].modal == "shall"
        assert "pay rent" in obs[0].matched_text

    def test_action_is_a_phrase_not_a_token(self):
        text = "Customer shall pay all invoices within thirty days of receipt."
        obs = extract_obligations(text, PARTIES)
        action = obs[0].action
        assert action.startswith("pay")
        assert " " in action  # a phrase, not one lowercased token
        assert "invoices" in action
        assert len(action) <= 120
        assert not action.endswith(".")

    def test_dedup_same_sentence_two_modals(self):
        text = "Provider shall deliver the report and shall maintain the records."
        obs = extract_obligations(text, PARTIES)
        assert len(obs) == 1  # same (subject, span_start) keeps the first
        assert obs[0].action.startswith("deliver")

    def test_dedup_identical_matched_text(self):
        text = "Provider shall pay the fee. Provider shall pay the fee."
        obs = extract_obligations(text, PARTIES)
        assert len(obs) == 1

    def test_capped_at_150(self):
        sentences = [
            f"Provider shall deliver item number {i} to Customer promptly." for i in range(200)
        ]
        obs = extract_obligations(" ".join(sentences), PARTIES)
        assert len(obs) == 150
        # Document order preserved.
        assert obs[0].span_start < obs[1].span_start < obs[-1].span_start


class TestLinkDeadlines:
    def test_deadline_inside_obligation_is_attached(self):
        text = (
            "Customer shall pay all invoices within thirty days of receipt. "
            "The office is located in Springfield."
        )
        obs = extract_obligations(text, PARTIES)
        assert len(obs) == 1
        inside = ExtractedDeadline(
            kind="relative_offset",
            description="within thirty days of receipt",
            offset_days=30,
            span_start=text.index("within thirty"),
            span_end=text.index("receipt") + len("receipt"),
            matched_text="within thirty days",
        )
        outside = ExtractedDeadline(
            kind="fixed_date",
            description="outside any obligation",
            span_start=len(text) - 5,
            span_end=len(text),
            matched_text="field",
        )
        link_deadlines(obs, [inside, outside])
        assert obs[0].deadlines == ["within thirty days of receipt"]

    def test_deadline_matches_at_most_one_obligation(self):
        text = (
            "Provider shall deliver the goods within ten days. "
            "Customer shall pay the invoice within thirty days."
        )
        obs = extract_obligations(text, PARTIES)
        assert len(obs) == 2
        d = ExtractedDeadline(
            kind="relative_offset",
            description="within ten days",
            span_start=text.index("within ten"),
            span_end=text.index("within ten") + len("within ten days"),
            matched_text="within ten days",
        )
        link_deadlines(obs, [d])
        assert obs[0].deadlines == ["within ten days"]
        assert obs[1].deadlines == []

    def test_matched_text_used_when_no_description(self):
        text = "Provider shall deliver the goods within ten days."
        obs = extract_obligations(text, PARTIES)
        d = ExtractedDeadline(
            kind="relative_offset",
            description="",
            span_start=text.index("within ten"),
            span_end=text.index("within ten") + len("within ten days"),
            matched_text="within ten days",
        )
        link_deadlines(obs, [d])
        assert obs[0].deadlines == ["within ten days"]

    def test_deadline_without_span_is_skipped(self):
        text = "Provider shall deliver the goods within ten days."
        obs = extract_obligations(text, PARTIES)
        d = ExtractedDeadline(kind="fixed_date", description="sometime", span_start=None)
        link_deadlines(obs, [d])
        assert obs[0].deadlines == []
