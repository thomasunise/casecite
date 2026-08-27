"""
Tests for DocumentAnalyzerService.

Source: backend/app/services/document_analyzer.py
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"


@pytest.fixture
def analyzer():
    """Create a DocumentAnalyzerService with mocked AI clients."""
    with patch("app.services.document_analyzer.settings") as mock_settings:
        mock_settings.openai_api_key = None
        mock_settings.anthropic_api_key = None
        from app.services.document_analyzer import DocumentAnalyzerService

        service = DocumentAnalyzerService()
        return service


@pytest.fixture
def analyzer_with_openai():
    """Analyzer with a mocked OpenAI client."""
    with patch("app.services.document_analyzer.settings") as mock_settings:
        mock_settings.openai_api_key = None
        mock_settings.anthropic_api_key = None
        from app.services.document_analyzer import DocumentAnalyzerService

        service = DocumentAnalyzerService()

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(
            {
                "contract_type": "nda",
                "parties": [{"name": "Acme Corp", "role": "Disclosing Party"}],
                "risks": [],
                "summary": "Standard NDA.",
                "confidence_score": 85,
            }
        )
        mock_client.chat.completions.create.return_value = mock_response
        service.openai_client = mock_client
        return service


SAMPLE_CONTRACT = """
MUTUAL NON-DISCLOSURE AGREEMENT

This Agreement is entered into as of January 1, 2024, by and between
Acme Corp ("Disclosing Party") and Beta LLC ("Receiving Party").

The Receiving Party shall hold and maintain the Confidential Information
in strict confidence. This obligation shall survive termination.

The indemnification clause requires each party to defend and indemnify
the other. Termination at will is permitted for either party.

Exclusive jurisdiction shall be in the State of California.
Mandatory arbitration applies to all disputes.
"""


class TestAnalyzeContract:
    """Tests for analyze_contract method."""

    @pytest.mark.asyncio
    async def test_analyze_contract_with_openai(self, analyzer_with_openai):
        """analyze_contract returns structured analysis via OpenAI."""
        result = await analyzer_with_openai.analyze_contract(
            document_text=SAMPLE_CONTRACT,
            document_name="test_nda.pdf",
            user_id="user-1",
        )
        from app.services.llm_clients import chat_model

        assert result["contract_type"] == "nda"
        # Model comes from the runtime config, not a hardcoded id.
        assert result["model_used"] == chat_model()
        call_kwargs = analyzer_with_openai.openai_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == chat_model()
        assert "analysis_time_ms" in result
        assert result["analysis_depth"] == "standard"

    @pytest.mark.asyncio
    async def test_analyze_contract_no_client(self, analyzer):
        """analyze_contract without any AI client raises a clear error."""
        with pytest.raises(ValueError, match="No AI provider configured"):
            await analyzer.analyze_contract(
                document_text=SAMPLE_CONTRACT,
            )

    @pytest.mark.asyncio
    async def test_analyze_contract_deep_depth(self, analyzer_with_openai):
        """analysis_depth='deep' sets max_tokens to 4000."""
        result = await analyzer_with_openai.analyze_contract(
            document_text=SAMPLE_CONTRACT,
            analysis_depth="deep",
        )
        call_kwargs = analyzer_with_openai.openai_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["max_tokens"] == 4000
        assert result["analysis_depth"] == "deep"

    @pytest.mark.asyncio
    async def test_analyze_contract_quick_depth(self, analyzer_with_openai):
        """analysis_depth='quick' sets max_tokens to 1000."""
        await analyzer_with_openai.analyze_contract(
            document_text=SAMPLE_CONTRACT,
            analysis_depth="quick",
        )
        call_kwargs = analyzer_with_openai.openai_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["max_tokens"] == 1000


class TestClientConstruction:
    """Server-side clients carry settings.api_timeout and bounded retries."""

    def test_openai_client_built_via_factory_with_timeout(self):
        from app.config import settings as real_settings

        with (
            patch("app.services.document_analyzer.settings") as mock_settings,
            patch.dict("app.services.llm_clients._runtime", {"base_url": None}),
        ):
            mock_settings.openai_api_key = "sk-test-ci-dummy-key-not-real"
            mock_settings.anthropic_api_key = None
            from app.services.document_analyzer import DocumentAnalyzerService

            service = DocumentAnalyzerService()
        assert service.openai_client is not None
        assert service.openai_client.timeout == real_settings.api_timeout
        assert service.openai_client.max_retries == 2

    def test_anthropic_client_has_timeout_and_bounded_retries(self):
        with (
            patch("app.services.document_analyzer.settings") as mock_settings,
            patch("anthropic.Anthropic") as mock_anthropic,
        ):
            mock_settings.openai_api_key = None
            mock_settings.anthropic_api_key = "sk-ant-test-dummy"
            mock_settings.api_timeout = 12.5
            from app.services.document_analyzer import DocumentAnalyzerService

            service = DocumentAnalyzerService()
        assert service.anthropic_client is mock_anthropic.return_value
        mock_anthropic.assert_called_once_with(
            api_key="sk-ant-test-dummy", timeout=12.5, max_retries=2
        )

    @pytest.mark.asyncio
    async def test_anthropic_model_comes_from_settings(self):
        with patch("app.services.document_analyzer.settings") as mock_settings:
            mock_settings.openai_api_key = None
            mock_settings.anthropic_api_key = None
            mock_settings.anthropic_model = "claude-test-model"
            from app.services.document_analyzer import DocumentAnalyzerService

            service = DocumentAnalyzerService()
            client = MagicMock()
            response = MagicMock()
            response.content = [MagicMock(text=json.dumps({"contract_type": "lease"}))]
            client.messages.create.return_value = response
            service.anthropic_client = client

            result = await service.analyze_contract(document_text=SAMPLE_CONTRACT)
        assert result["model_used"] == "claude-test-model"
        assert client.messages.create.call_args.kwargs["model"] == "claude-test-model"
