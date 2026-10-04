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


class TestFullCaseNameRequired:
    """A reference is verified against a case NAME, not loose party substrings."""

    def test_party_words_scattered_in_a_source_do_not_verify_a_case(self):
        """Regression: "State" and "Smith" each appearing somewhere in a
        retrieved passage used to let an invented "State v. Smith" through."""
        docs = [_doc("The State agency wrote to Mr. Smith about the permit on May 1.")]
        content = "This is settled by State v. Smith."
        spans = find_unverified_case_references(content, None, docs)
        assert [content[s:e] for s, e in spans] == ["State v. Smith"]

    def test_party_words_from_two_different_cases_do_not_combine(self):
        cases = [_case("Smith v. Jones"), _case("Brown v. Board of Education")]
        content = "Compare Smith v. Board on this point."
        assert find_unverified_case_references(content, cases) != []

    def test_wrong_first_party_is_flagged_even_if_it_shares_a_word(self):
        cases = [_case("Acme Inc. v. Beta LLC")]
        content = "Fake Inc. v. Beta is to the same effect."
        assert find_unverified_case_references(content, cases) != []

    def test_sentence_lead_in_is_not_part_of_the_name(self):
        cases = [_case("Smith v. Jones", "123 F.3d 456")]
        content = "In Smith v. Jones, the court enforced the clause."
        assert find_unverified_case_references(content, cases) == []

    def test_text_following_the_name_does_not_break_a_provided_case(self):
        cases = [_case("Smith v. Jones", "123 F.3d 456")]
        content = "The rule comes from Smith v. Jones. The court there enforced the clause."
        assert find_unverified_case_references(content, cases) == []

    def test_case_named_in_opinion_text_is_allowed(self):
        cases = [_case("Smith v. Jones", text="We follow Miranda v. Arizona on this point.")]
        content = "The opinion relies on Miranda v. Arizona."
        assert find_unverified_case_references(content, cases) == []


class TestSinglePartyCaptions:
    """ "In re", "Matter of" and "Ex parte" cases have no "v." to match on."""

    def test_invented_in_re_case_is_flagged(self):
        content = "As explained in In re Gault, the standard applies."
        spans = find_unverified_case_references(content)
        assert [content[s:e] for s, e in spans] == ["In re Gault"]

    def test_invented_ex_parte_case_is_flagged(self):
        content = "Sovereign immunity yields under Ex parte Young."
        spans = find_unverified_case_references(content)
        assert [content[s:e] for s, e in spans] == ["Ex parte Young"]

    def test_invented_matter_of_case_is_flagged(self):
        content = "See Matter of Baby M for the opposite result."
        spans = find_unverified_case_references(content)
        assert [content[s:e] for s, e in spans] == ["Matter of Baby M"]

    def test_provided_in_re_case_is_allowed(self):
        cases = [_case("In re Gault", "387 U.S. 1")]
        content = "In re Gault, 387 U.S. 1, controls juvenile proceedings."
        assert find_unverified_case_references(content, cases) == []

    def test_in_the_matter_of_matches_a_matter_of_caption(self):
        cases = [_case("Matter of Baby M")]
        content = "The court in In the Matter of Baby M refused enforcement."
        assert find_unverified_case_references(content, cases) == []

    def test_in_re_case_quoted_in_the_users_document_is_allowed(self):
        docs = [_doc("Debtor relies on In re Enron Corp. for the safe harbor.")]
        content = "Your brief cites In re Enron Corp. for the safe harbor."
        assert find_unverified_case_references(content, None, docs) == []

    def test_ordinary_ex_parte_usage_is_not_a_case(self):
        content = (
            "An ex parte order was entered. Ex parte communications with the judge "
            "are prohibited, and the Ex Parte Application was denied as a matter of law."
        )
        assert find_unverified_case_references(content) == []

    def test_redaction_removes_the_invented_single_party_case(self):
        out, removed = redact_unverified_case_law("Under In re Winship, proof is required.")
        assert removed == ["In re Winship"]
        assert REDACTION in out


class TestSingleLineNames:
    """A case name never spans a line break."""

    def test_heading_above_a_reference_is_not_swallowed(self):
        content = "KEY AUTHORITY\n\nPer Ghost v. Invented, the clause fails."
        out, removed = redact_unverified_case_law(content)
        assert removed == ["Per Ghost v. Invented"]
        assert out.startswith("KEY AUTHORITY\n\n")

    def test_heading_above_a_provided_case_does_not_break_it(self):
        cases = [_case("Smith v. Jones", "123 F.3d 456")]
        content = "Controlling Authority\n\nSmith v. Jones governs this clause."
        assert find_unverified_case_references(content, cases) == []

    def test_name_split_across_lines_is_not_a_case_name(self):
        content = "The parties are Acme\nv.\nBeta in the caption."
        assert find_unverified_case_references(content) == []
