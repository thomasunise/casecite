"""
Unit tests for the case-law citation guard.

The guard enforces the product's hardest rule: case law is never trusted from
the model. Any case name or reporter citation in an answer that is not
traceable to this request's CourtListener results or the user's own retrieved
passages must be redacted.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from app.services.rag.case_law_guard import (
    REDACTION,
    find_unverified_case_references,
    redact_unverified_case_law,
)


def _case(case_name: str, citation: str = "", text: str = "") -> dict:
    return {
        "text": text,
        "metadata": {
            "case_name": case_name,
            "citation": citation,
            "filename": f"{case_name} ({citation})" if citation else case_name,
        },
    }


def _doc(text: str) -> dict:
    return {"text": text, "metadata": {"filename": "brief.pdf"}}


class TestDetection:
    def test_invented_case_name_is_flagged(self):
        content = "As held in Mata v. Avianca, the claim fails."
        assert find_unverified_case_references(content) != []

    def test_invented_reporter_citation_is_flagged(self):
        content = "See 573 F. Supp. 3d 100 for the standard."
        assert find_unverified_case_references(content) != []

    def test_invented_westlaw_citation_is_flagged(self):
        content = "The court agreed, 2023 WL 1234567."
        assert find_unverified_case_references(content) != []

    def test_plain_prose_is_not_flagged(self):
        content = (
            "The agreement terminates on December 31, 2024. Section 8.2 requires "
            "30 days notice, and the indemnity cap is $2 million."
        )
        assert find_unverified_case_references(content) == []

    def test_provided_case_is_allowed(self):
        cases = [_case("Smith v. Jones", "123 F.3d 456")]
        content = "Smith v. Jones controls here, 123 F.3d 456."
        assert find_unverified_case_references(content, cases) == []

    def test_vs_spelling_matches_provided_v_dot(self):
        cases = [_case("Smith v. Jones", "123 F.3d 456")]
        content = "Smith vs. Jones is directly on point."
        assert find_unverified_case_references(content, cases) == []

    def test_shortened_form_of_provided_case_is_allowed(self):
        cases = [_case("John Smith v. Acme Jones Corp.")]
        content = "Smith v. Jones supports this reading."
        assert find_unverified_case_references(content, cases) == []

    def test_case_discussed_in_user_document_is_allowed(self):
        docs = [_doc("Our motion relies on Miranda v. Arizona, 384 U.S. 436.")]
        content = "Your own brief already cites Miranda v. Arizona, 384 U.S. 436."
        assert find_unverified_case_references(content, None, docs) == []

    def test_case_absent_from_all_sources_is_flagged_alongside_allowed_one(self):
        cases = [_case("Smith v. Jones", "123 F.3d 456")]
        content = "Smith v. Jones applies, unlike Roe v. Wade."
        spans = find_unverified_case_references(content, cases)
        assert len(spans) == 1
        start, end = spans[0]
        assert content[start:end] == "Roe v. Wade"


class TestRedaction:
    def test_clean_content_is_returned_unchanged(self):
        content = "The termination clause requires 30 days notice."
        out, removed = redact_unverified_case_law(content)
        assert out == content
        assert removed == []

    def test_invented_reference_is_redacted_with_visible_note(self):
        content = "As held in Mata v. Avianca, sanctions follow."
        out, removed = redact_unverified_case_law(content)
        assert "Mata v. Avianca" not in out.split("\n\n> ⚠")[0]
        assert REDACTION in out
        assert removed == ["Mata v. Avianca"]
        assert "could not be verified" in out

    def test_adjacent_name_and_citation_merge_into_one_redaction(self):
        content = "See Fake v. Case, 999 F.3d 111 (2020)."
        out, removed = redact_unverified_case_law(content)
        assert len(removed) == 1
        assert "Fake v. Case, 999 F.3d 111" in removed[0]
        assert out.count(REDACTION) == 1

    def test_empty_content_passes_through(self):
        out, removed = redact_unverified_case_law("")
        assert out == ""
        assert removed == []

    def test_provided_case_survives_while_invented_is_removed(self):
        cases = [_case("Smith v. Jones", "123 F.3d 456", "indemnity holding text")]
        content = "Smith v. Jones controls. Ghost v. Invented does not exist."
        out, removed = redact_unverified_case_law(content, cases)
        assert "Smith v. Jones" in out
        assert "Ghost v. Invented" not in out
        assert removed == ["Ghost v. Invented"]
