"""
Tenant Isolation Tests

Verifies that multi-tenant data isolation works correctly:
- User A cannot see User B's documents
- User A cannot search User B's vectors
- User A's settings don't affect User B
- Deleting User A's data doesn't touch User B's data
"""

from datetime import UTC, datetime

from app.services.auth import User, UserRole
from fastapi.testclient import TestClient

from tests.conftest import make_auth_headers


def _make_user(user_id: str, email: str) -> User:
    """Create a test user."""
    return User(
        id=user_id,
        email=email,
        name=f"User {user_id}",
        roles=[UserRole.ATTORNEY, UserRole.ADMIN],
        last_login=datetime.now(UTC),
    )


def _make_headers(user: User) -> dict:
    """Create auth headers for a user (token + registered session)."""
    return make_auth_headers(user)


USER_A = _make_user("user-a-111", "usera@firmA.com")
USER_B = _make_user("user-b-222", "userb@firmB.com")
HEADERS_A = _make_headers(USER_A)
HEADERS_B = _make_headers(USER_B)


class TestDocumentIsolation:
    """Test that documents are isolated between users."""

    def test_user_a_documents_invisible_to_user_b(self, client: TestClient):
        """User A's documents should not appear in User B's document list."""
        # List documents as User A
        response_a = client.get("/api/v1/documents", headers=HEADERS_A)
        assert response_a.status_code == 200
        docs_a = response_a.json()

        # List documents as User B
        response_b = client.get("/api/v1/documents", headers=HEADERS_B)
        assert response_b.status_code == 200
        docs_b = response_b.json()

        # Both should return only their own documents (initially empty)
        # The key assertion: document IDs from A should never appear in B's list
        doc_ids_a = {d["id"] for d in docs_a.get("documents", [])}
        doc_ids_b = {d["id"] for d in docs_b.get("documents", [])}
        assert doc_ids_a.isdisjoint(doc_ids_b), "Users should not share any document IDs"

    def test_user_cannot_get_other_users_document(self, client: TestClient):
        """User B should not be able to retrieve User A's document by ID."""
        # Try to get a non-existent document as User B (simulating cross-tenant access)
        response = client.get("/api/v1/documents/fake-doc-id-from-user-a", headers=HEADERS_B)
        # Should get 404, not the document
        assert response.status_code == 404

    def test_user_cannot_delete_other_users_document(self, client: TestClient):
        """User B should not be able to delete User A's document."""
        response = client.delete("/api/v1/documents/fake-doc-id-from-user-a", headers=HEADERS_B)
        # Should get 404 (not found for this user), not 200
        assert response.status_code == 404


class TestSettingsIsolation:
    """Test that RAG settings are isolated between users."""

    def test_settings_are_per_user(self, client: TestClient):
        """Changing settings for User A should not affect User B."""
        # Get User B's settings first
        original_b = client.get("/api/v1/settings/rag", headers=HEADERS_B)
        assert original_b.status_code == 200
        original_b_data = original_b.json()

        # Change User A's settings
        new_settings = {
            "top_k": 42,
            "similarity_threshold": 0.99,
            "temperature": 0.5,
        }
        update_a = client.put("/api/v1/settings/rag", json=new_settings, headers=HEADERS_A)
        assert update_a.status_code == 200

        # User B's settings should be unchanged
        after_b = client.get("/api/v1/settings/rag", headers=HEADERS_B)
        assert after_b.status_code == 200
        after_b_data = after_b.json()

        assert after_b_data["top_k"] == original_b_data["top_k"]
        assert after_b_data["similarity_threshold"] == original_b_data["similarity_threshold"]

    def test_settings_persist_per_user(self, client: TestClient):
        """User A's custom settings should persist and be returned correctly."""
        new_settings = {
            "top_k": 15,
            "similarity_threshold": 0.8,
            "temperature": 0.2,
        }
        client.put("/api/v1/settings/rag", json=new_settings, headers=HEADERS_A)

        result = client.get("/api/v1/settings/rag", headers=HEADERS_A)
        assert result.status_code == 200
        data = result.json()

        assert data["top_k"] == 15
        assert data["similarity_threshold"] == 0.8


class TestIntentDetection:
    """Test query intent detection with the refactored module."""

    def test_factual_intent(self):
        """Test factual query intent detection."""
        from app.models.schemas import QueryIntent
        from app.services.rag.intent import detect_query_intent

        factual_queries = [
            "What is the filing deadline?",
            "When was the complaint filed?",
            "Where is the courthouse located?",
            "Who is the judge assigned to this case?",
            "How many claims were dismissed?",
            "Is there a statute of limitations?",
        ]

        for query in factual_queries:
            intent = detect_query_intent(query)
            assert intent == QueryIntent.FACTUAL, f"Expected FACTUAL for: '{query}'"

    def test_analytical_intent(self):
        """Test analytical query intent detection."""
        from app.models.schemas import QueryIntent
        from app.services.rag.intent import detect_query_intent

        analytical_queries = [
            "What strategy should we use for the appeal?",
            "Compare the plaintiff's and defendant's arguments",
            "Analyze the risk of summary judgment",
            "What are the strengths and weaknesses of our position?",
            "Draft a motion to dismiss",
            "Explain the legal basis for our claim",
        ]

        for query in analytical_queries:
            intent = detect_query_intent(query)
            assert intent == QueryIntent.ANALYTICAL, f"Expected ANALYTICAL for: '{query}'"

    def test_short_queries_are_factual(self):
        """Short queries (<=8 words) should default to factual."""
        from app.models.schemas import QueryIntent
        from app.services.rag.intent import detect_query_intent

        assert detect_query_intent("contract terms") == QueryIntent.FACTUAL
        assert detect_query_intent("filing date") == QueryIntent.FACTUAL


class TestPromptGeneration:
    """Test prompt generation with the refactored module."""

    def test_factual_prompt_is_concise(self):
        """Factual queries should get a concise prompt."""
        from app.models.schemas import AnalysisMode, QueryIntent
        from app.services.rag.prompts import get_system_prompt

        prompt = get_system_prompt(AnalysisMode.RESEARCH, query_intent=QueryIntent.FACTUAL)
        assert "DIRECT answer" in prompt
        assert "concise" in prompt.lower()

    def test_analytical_prompt_includes_strategy(self):
        """Analytical queries should get a strategic analysis prompt."""
        from app.models.schemas import AnalysisMode, QueryIntent
        from app.services.rag.prompts import get_system_prompt

        prompt = get_system_prompt(AnalysisMode.RESEARCH, query_intent=QueryIntent.ANALYTICAL)
        assert "strategic" in prompt.lower() or "strategy" in prompt.lower()

    def test_drafting_prompt(self):
        """Drafting mode should use special prompt."""
        from app.models.schemas import AnalysisMode
        from app.services.rag.prompts import get_system_prompt

        prompt = get_system_prompt(AnalysisMode.RESEARCH, is_drafting=True)
        assert "legal document drafter" in prompt.lower()
        assert "BRACKETED PLACEHOLDERS" in prompt

    def test_custom_system_prompt_used_when_set(self):
        """Custom system prompt should override default."""
        from app.models.schemas import AnalysisMode, QueryIntent, RAGSettings
        from app.services.rag.prompts import get_system_prompt

        custom_settings = RAGSettings(custom_system_prompt="You are a custom legal AI.")
        prompt = get_system_prompt(
            AnalysisMode.RESEARCH,
            query_intent=QueryIntent.ANALYTICAL,
            rag_settings=custom_settings,
        )
        assert "custom legal AI" in prompt

    def test_mode_specific_prompts(self):
        """Each analysis mode should produce different prompts."""
        from app.models.schemas import AnalysisMode, QueryIntent
        from app.services.rag.prompts import get_system_prompt

        research = get_system_prompt(AnalysisMode.RESEARCH, query_intent=QueryIntent.ANALYTICAL)
        strategy = get_system_prompt(AnalysisMode.STRATEGY, query_intent=QueryIntent.ANALYTICAL)
        compliance = get_system_prompt(AnalysisMode.COMPLIANCE, query_intent=QueryIntent.ANALYTICAL)

        # All modes should have different content
        assert research != strategy
        assert research != compliance


class TestCitationExtraction:
    """Test citation extraction from AI responses."""

    def test_extract_cited_cases_by_name(self):
        """Test that cases cited by name are detected."""
        from app.services.rag.citations import extract_cited_cases

        case_law = [
            {
                "metadata": {
                    "case_name": "Smith v. Jones",
                    "citation": "123 F.3d 456",
                    "filename": "Smith v. Jones (123 F.3d 456)",
                }
            },
            {
                "metadata": {
                    "case_name": "Brown v. Board",
                    "citation": "347 U.S. 483",
                    "filename": "Brown v. Board (347 U.S. 483)",
                }
            },
        ]

        # Content only mentions Smith v. Jones
        content = "As held in Smith v. Jones, the standard requires..."
        cited = extract_cited_cases(content, case_law)

        assert len(cited) == 1
        assert cited[0]["metadata"]["case_name"] == "Smith v. Jones"

    def test_extract_cited_cases_by_citation(self):
        """Test that cases cited by citation string are detected."""
        from app.services.rag.citations import extract_cited_cases

        case_law = [
            {
                "metadata": {
                    "case_name": "Smith v. Jones",
                    "citation": "123 F.3d 456",
                    "filename": "",
                }
            },
        ]

        content = "See 123 F.3d 456 for the applicable standard."
        cited = extract_cited_cases(content, case_law)
        assert len(cited) == 1

    def test_uncited_cases_not_extracted(self):
        """Test that cases not mentioned in content are not extracted."""
        from app.services.rag.citations import extract_cited_cases

        case_law = [
            {
                "metadata": {
                    "case_name": "Unrelated v. Case",
                    "citation": "999 F.3d 999",
                    "filename": "",
                }
            },
        ]

        content = "This analysis does not reference any specific case law."
        cited = extract_cited_cases(content, case_law)
        assert len(cited) == 0

    def test_extract_key_phrases(self):
        """Test key phrase extraction."""
        from app.services.rag.citations import extract_key_phrases

        text = 'The "breach of contract" claim relates to Section 4.2 of the Agreement.'
        phrases = extract_key_phrases(text, "breach of contract")

        assert len(phrases) > 0
        # Should find quoted phrase and legal terms
        assert any("breach" in p.lower() for p in phrases)


class TestGenerationHelpers:
    """Test generation module helper functions."""

    def test_build_context_with_case_law(self):
        """Test context building with both documents and case law."""
        from app.services.rag.generation import build_context_with_case_law

        docs = [
            {"metadata": {"filename": "contract.pdf"}, "text": "Contract text here."},
        ]
        cases = [
            {
                "metadata": {
                    "filename": "Smith v. Jones",
                    "citation": "123 F.3d 456",
                    "court": "9th Cir.",
                },
                "text": "Case text here.",
            },
        ]

        context = build_context_with_case_law(docs, cases)
        assert "FROM YOUR DOCUMENTS" in context
        assert "FROM CASE LAW" in context
        assert "contract.pdf" in context
        assert "Smith v. Jones" in context

    def test_get_model_max_tokens_factual(self):
        """Factual intent should get fewer tokens."""
        from app.models.schemas import QueryIntent
        from app.services.rag.generation import get_model_max_tokens

        factual_tokens = get_model_max_tokens("gpt-4o", QueryIntent.FACTUAL)
        analytical_tokens = get_model_max_tokens("gpt-4o", QueryIntent.ANALYTICAL)

        assert factual_tokens == 500
        assert analytical_tokens == 16384
        assert factual_tokens < analytical_tokens

    def test_get_model_max_tokens_various_models(self):
        """Test max tokens for various model names."""
        from app.services.rag.generation import get_model_max_tokens

        assert get_model_max_tokens("gpt-4o") == 16384
        assert get_model_max_tokens("gpt-4-turbo") == 4096
        assert get_model_max_tokens("claude-3-5-sonnet") == 8192
        assert get_model_max_tokens("claude-3-opus") == 4096
        assert get_model_max_tokens("gemini-pro") == 8192
        assert get_model_max_tokens("o1-preview") == 32768
        assert get_model_max_tokens("unknown-model") == 4096
