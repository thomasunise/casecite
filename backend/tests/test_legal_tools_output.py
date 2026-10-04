"""
Regression tests for legal-tool output shape: v4 nested snippets, citation
ordering, trend direction, and CourtListener error mapping.
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars!")
os.environ.setdefault("ENCRYPTION_SALT", "test-salt-16chars!")
os.environ.setdefault("DEBUG", "true")

from contextlib import asynccontextmanager
from unittest.mock import patch

import httpx
import pytest
from app.services.courtlistener import CitationTreatment, CourtListenerService
from app.services.courtlistener_errors import courtlistener_http_error
from app.services.legal_tools._helpers import (
    citation_dict_to_string,
    nested_snippet,
    order_citations,
    strip_marks,
)
from app.services.legal_tools.service import LegalToolsService


class TestHelpers:
    def test_official_reporter_first(self):
        cites = ["173 L. Ed. 2d 868", "129 S. Ct. 1937", "556 U.S. 662", "2009 U.S. LEXIS 3472"]
        assert order_citations(cites)[0] == "556 U.S. 662"
        assert order_citations(cites)[:2] == ["556 U.S. 662", "129 S. Ct. 1937"]

    def test_federal_reporter_over_appendix(self):
        assert order_citations(["12 F. App'x 34", "37 F.4th 1098"])[0] == "37 F.4th 1098"

    def test_nested_snippet_and_marks(self):
        result = {"opinions": [{"snippet": "Sup. Ct. <mark>Ariz</mark>.\n Certiorari  denied"}]}
        assert nested_snippet(result) == "Sup. Ct. Ariz. Certiorari denied"
        assert strip_marks("<mark>Miranda v. Arizona</mark>") == "Miranda v. Arizona"
        assert nested_snippet({}) == ""

    def test_cluster_citation_dict(self):
        assert (
            citation_dict_to_string({"volume": 410, "reporter": "U.S.", "page": "113"})
            == "410 U.S. 113"
        )
        assert citation_dict_to_string({"volume": None, "reporter": "", "page": ""}) is None


class _Resp:
    def __init__(self, status_code, data, headers=None):
        self.status_code = status_code
        self._data = data
        self.headers = headers or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "err",
                request=httpx.Request("GET", "https://x"),
                response=httpx.Response(self.status_code),
            )


def _client_cm(handler):
    class _Client:
        async def get(self, url, params=None, headers=None, timeout=None):
            return handler(url, params or {})

    @asynccontextmanager
    async def _cm(timeout=None):
        yield _Client()

    return _cm


class TestTrendDirection:
    @pytest.mark.asyncio
    async def test_partial_current_year_is_excluded_from_direction(self):
        from datetime import datetime

        now = datetime.now().year
        counts = {now - 3: 100, now - 2: 120, now - 1: 150, now: 20}

        def handler(url, params):
            year = int(params["filed_after"][:4])
            return _Resp(200, {"count": counts[year]})

        svc = LegalToolsService()
        svc.api_token = "t"
        with patch("app.services.legal_tools._trends.cl_client", _client_cm(handler)):
            result = await svc.analyze_legal_trend("patent", start_year=now - 3, end_year=now)
        assert result["trend"] == "increasing"
        assert result["current_year_partial"] is True
        assert result["trend_basis"] == {"from_year": now - 3, "to_year": now - 1}
        assert result["years"][-1] == {"year": now, "count": 20}


class TestTreatmentScan:
    def test_word_boundaries(self):
        svc = CourtListenerService()
        # "limitations" must not read as a cautionary "limited"
        assert (
            svc._analyze_treatment("the statute of limitations bars the claim")
            == CitationTreatment.NEUTRAL
        )
        assert (
            svc._analyze_treatment("Roe v. Wade, 410 U.S. 113, overruled by Dobbs")
            == CitationTreatment.NEGATIVE
        )
        assert (
            svc._analyze_treatment("we distinguished Roe on its facts") == CitationTreatment.CAUTION
        )
        assert (
            svc._analyze_treatment("as this court reaffirmed in Roe") == CitationTreatment.POSITIVE
        )

    def test_window_around_mark(self):
        long = "x" * 1000 + "<mark>410 U.S. 113</mark> overruled" + "y" * 1000
        window = CourtListenerService._window_around_mark(long)
        assert "overruled" in window and len(window) < 700


class TestErrorMapping:
    def _status_error(self, code):
        return httpx.HTTPStatusError(
            "e", request=httpx.Request("GET", "https://x"), response=httpx.Response(code)
        )

    def test_bad_token_is_explained(self):
        exc = courtlistener_http_error(self._status_error(401), "x", "fallback")
        assert exc.status_code == 502 and "token" in exc.detail.lower()

    def test_rate_limit(self):
        exc = courtlistener_http_error(self._status_error(429), "x", "fallback")
        assert exc.status_code == 503 and "rate" in exc.detail.lower()

    def test_missing_token_value_error(self):
        exc = courtlistener_http_error(
            ValueError("CourtListener API token required."), "x", "fallback"
        )
        assert exc.status_code == 503

    def test_other_errors_keep_fallback(self):
        exc = courtlistener_http_error(KeyError("boom"), "x", "Search failed.")
        assert exc.status_code == 500 and exc.detail == "Search failed."
