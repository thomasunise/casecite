"""
Judge Intel opinion text: cached opinions are keyed by cluster id and most
CourtListener opinions carry only HTML — both paths must still yield text.
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars!")
os.environ.setdefault("ENCRYPTION_SALT", "test-salt-16chars!")
os.environ.setdefault("DEBUG", "true")

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from app.services.judge_intel import JudgeIntelService


class _Resp:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


class _Client:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def get(self, url, headers=None, timeout=None, params=None):
        self.calls.append(url)
        for key, resp in self.routes.items():
            if key in url:
                return resp
        return _Resp(404, {})


ROUTES = {
    "/clusters/555/": _Resp(
        200,
        {
            "sub_opinions": [
                "https://www.courtlistener.com/api/rest/v4/opinions/1/",
                "https://www.courtlistener.com/api/rest/v4/opinions/2/",
            ]
        },
    ),
    # lead opinion: no plain_text, HTML only (the common case)
    "/opinions/1/": _Resp(
        200,
        {
            "id": 1,
            "type": "020lead",
            "author_str": "Roberts",
            "plain_text": "",
            "html_with_citations": "<p>We <em>hold</em> that the statute applies.</p>",
        },
    ),
    "/opinions/2/": _Resp(
        200,
        {"id": 2, "type": "040dissent", "plain_text": "I respectfully dissent.", "author_str": ""},
    ),
}


@pytest.mark.asyncio
async def test_fetch_cluster_text_strips_html_and_joins_parts():
    svc = JudgeIntelService()
    svc.api_token = "t"
    client = _Client(ROUTES)
    text, parts = await svc._fetch_cluster_text(client, 555)
    assert "We hold that the statute applies." in text
    assert "<p>" not in text and "<em>" not in text
    assert "Lead opinion — Roberts" in text
    assert "Dissent" in text and "I respectfully dissent." in text
    assert [p["type_label"] for p in parts] == ["Lead opinion", "Dissent"]


@pytest.mark.asyncio
async def test_get_opinion_full_text_fetches_via_cluster_and_caches():
    svc = JudgeIntelService()
    svc.api_token = "t"
    row = SimpleNamespace(
        judge_data={"name": "Judge X"},
        opinions_data={"opinions": [{"id": 555, "case_name": "A v. B", "full_text": ""}]},
    )
    client = _Client(ROUTES)

    @asynccontextmanager
    async def _cm(timeout=None):
        yield client

    with (
        patch.object(svc, "_get_cache", AsyncMock(return_value=row)),
        patch.object(svc, "_set_cache", AsyncMock()) as set_cache,
        patch("app.services.courtlistener_gate.cl_client", _cm),
    ):
        op = await svc.get_opinion_full_text(42, 555)

    assert op is not None
    assert "statute applies" in op["full_text"]
    assert op["word_count"] > 0
    assert any("/clusters/555/" in c for c in client.calls)
    assert not any("/opinions/555/" in c for c in client.calls)
    set_cache.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_opinion_full_text_marks_unavailable():
    svc = JudgeIntelService()
    svc.api_token = "t"
    row = SimpleNamespace(
        judge_data={"name": "Judge X"},
        opinions_data={"opinions": [{"id": 777, "case_name": "C v. D", "full_text": ""}]},
    )
    client = _Client({"/clusters/777/": _Resp(200, {"sub_opinions": []})})

    @asynccontextmanager
    async def _cm(timeout=None):
        yield client

    with (
        patch.object(svc, "_get_cache", AsyncMock(return_value=row)),
        patch.object(svc, "_set_cache", AsyncMock()),
        patch("app.services.courtlistener_gate.cl_client", _cm),
    ):
        op = await svc.get_opinion_full_text(42, 777)
    assert op["text_unavailable"] is True
    assert not op.get("full_text")
