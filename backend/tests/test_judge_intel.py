"""
Tests for JudgeIntelService.
"""

import datetime as _dt_module
import sys
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Shim datetime.UTC for Python < 3.11 (UTC was added in 3.11)
if sys.version_info < (3, 11) and not hasattr(_dt_module, "UTC"):
    _dt_module.UTC = _dt_module.UTC


class TestJudgeIntelService:
    """Tests for judge intelligence features."""

    def test_ensure_serializable_datetime(self):
        """Test datetime conversion to ISO string."""
        from app.services.judge_intel import judge_intel

        data = {
            "name": "Judge Smith",
            "appointed": datetime(2020, 1, 15, 10, 30),
            "birth_date": date(1960, 5, 20),
        }
        result = judge_intel._ensure_serializable(data)
        assert result["name"] == "Judge Smith"
        assert isinstance(result["appointed"], str)
        assert isinstance(result["birth_date"], str)
        assert "2020" in result["appointed"]

    def test_ensure_serializable_nested(self):
        """Test serialization of nested structures."""
        from app.services.judge_intel import judge_intel

        data = {
            "opinions": [
                {"date": datetime(2023, 6, 1), "case": "Test v. Case"},
            ],
            "metadata": {"updated": datetime(2024, 1, 1)},
        }
        result = judge_intel._ensure_serializable(data)
        assert isinstance(result["opinions"][0]["date"], str)
        assert isinstance(result["metadata"]["updated"], str)

    def test_ensure_serializable_plain_data(self):
        """Test that plain data passes through unchanged."""
        from app.services.judge_intel import judge_intel

        data = {"name": "Smith", "count": 42, "active": True, "tags": ["federal"]}
        result = judge_intel._ensure_serializable(data)
        assert result == data

    def test_parse_judge_data_from_string(self):
        """Test parsing judge data from JSON string."""
        import json

        from app.services.judge_intel import judge_intel

        mock_row = MagicMock()
        mock_row.judge_data = json.dumps({"name": "Judge Smith", "court": "9th Circuit"})

        result = judge_intel._parse_judge_data(mock_row)
        assert result["name"] == "Judge Smith"
        assert result["court"] == "9th Circuit"

    def test_parse_judge_data_from_dict(self):
        """Test parsing judge data when already a dict."""
        from app.services.judge_intel import judge_intel

        mock_row = MagicMock()
        mock_row.judge_data = {"name": "Judge Smith", "court": "9th Circuit"}

        result = judge_intel._parse_judge_data(mock_row)
        assert result["name"] == "Judge Smith"

    def test_parse_wikipedia_sections(self):
        """Test Wikipedia text section parsing."""
        from app.services.judge_intel import judge_intel

        wiki_text = """
== Early life and education ==
Born in New York. Attended Harvard Law School.

== Legal career ==
Practiced at Jones Day for 15 years.

== Federal judicial service ==
Nominated by President in 2015.
"""
        result = judge_intel._parse_wikipedia_sections(wiki_text)
        assert isinstance(result, dict)
        # Should have parsed sections
        assert len(result) >= 2

    @pytest.mark.asyncio
    async def test_search_judges(self):
        """Test judge search via CourtListener API."""
        from app.services.judge_intel import judge_intel

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "id": 123,
                    "name_first": "John",
                    "name_last": "Smith",
                    "court": "ca9",
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            # Need to set API token
            with patch.object(judge_intel, "api_token", "test-token"):
                result = await judge_intel.search_judges(query="Smith", limit=10)

            assert result is not None

    @pytest.mark.asyncio
    async def test_query_opinions_filtering(self):
        """Test opinion query with filters."""
        from app.services.judge_intel import judge_intel

        mock_cache = MagicMock()
        mock_cache.opinions_data = {
            "opinions": [
                {
                    "id": 1,
                    "case_name": "Smith v. Jones",
                    "date_filed": "2023-06-15",
                    "citation_count": 10,
                    "court": "ca9",
                },
                {
                    "id": 2,
                    "case_name": "Doe v. Roe",
                    "date_filed": "2020-01-01",
                    "citation_count": 2,
                    "court": "ca9",
                },
            ]
        }
        mock_cache.judge_data = '{"name": "Judge Smith"}'

        with patch.object(
            judge_intel,
            "_get_cache",
            new_callable=AsyncMock,
            return_value=mock_cache,
        ):
            result = await judge_intel.query_opinions(
                judge_id=42,
                query="Smith",
                limit=50,
                offset=0,
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_query_opinions_pagination(self):
        """Test opinion query with offset/limit."""
        from app.services.judge_intel import judge_intel

        opinions = [
            {
                "id": i,
                "case_name": f"Case {i}",
                "date_filed": f"2023-0{min(i, 9)}-01",
                "citation_count": i * 5,
                "court": "ca9",
            }
            for i in range(1, 11)
        ]

        mock_cache = MagicMock()
        mock_cache.opinions_data = {"opinions": opinions}
        mock_cache.judge_data = '{"name": "Judge Smith"}'

        with patch.object(
            judge_intel,
            "_get_cache",
            new_callable=AsyncMock,
            return_value=mock_cache,
        ):
            result = await judge_intel.query_opinions(
                judge_id=42,
                limit=3,
                offset=0,
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_query_opinions_order_by_citations(self):
        """order="citations" returns most-cited first; default stays date desc."""
        from app.services.judge_intel import judge_intel

        opinions = [
            {"id": 1, "case_name": "Old but famous", "date_filed": "2001-01-01", "citation_count": 900},
            {"id": 2, "case_name": "New and obscure", "date_filed": "2024-01-01", "citation_count": 1},
            {"id": 3, "case_name": "Middling", "date_filed": "2010-01-01", "citation_count": 50},
        ]
        mock_cache = MagicMock()
        mock_cache.opinions_data = {"opinions": opinions}
        mock_cache.judge_data = '{"name": "Judge Smith"}'

        with patch.object(
            judge_intel,
            "_get_cache",
            new_callable=AsyncMock,
            return_value=mock_cache,
        ):
            by_citations = await judge_intel.query_opinions(judge_id=42, order="citations")
            assert [op["id"] for op in by_citations["opinions"]] == [1, 3, 2]

            by_date = await judge_intel.query_opinions(judge_id=42)
            assert [op["id"] for op in by_date["opinions"]] == [2, 3, 1]

    @pytest.mark.asyncio
    async def test_compute_advanced_metrics(self):
        """Test advanced metrics computation."""
        import json

        from app.services.judge_intel import judge_intel

        mock_cache = MagicMock()
        mock_cache.judge_data = json.dumps(
            {
                "name": "Judge Smith",
                "positions": [{"court": "ca9"}],
            }
        )
        mock_cache.opinions_data = json.dumps(
            {
                "opinions": [
                    {
                        "id": 1,
                        "case_name": "Test",
                        "opinion_type": "majority",
                        "citation_count": 10,
                        "full_text": "The court holds that the defendant...",
                    },
                    {
                        "id": 2,
                        "case_name": "Test 2",
                        "opinion_type": "dissent",
                        "citation_count": 5,
                        "full_text": "I respectfully dissent...",
                    },
                ]
            }
        )

        with (
            patch.object(
                judge_intel,
                "_get_cache",
                new_callable=AsyncMock,
                return_value=mock_cache,
            ),
            patch.object(
                judge_intel,
                "_set_cache",
                new_callable=AsyncMock,
            ),
        ):
            result = await judge_intel.compute_advanced_metrics(
                judge_id=42,
                force_recompute=True,
            )

            assert result is not None
