"""Regression tests for case-detail lookup.

The bug: search_cases returns the CLUSTER id (V4), but get_case_detail fetched
/opinions/{id}/ — treating that cluster id as an opinion id, so CourtListener
404'd every case-detail open. get_case_detail is now cluster-first with an
opinion-id fallback.
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars!")
os.environ.setdefault("ENCRYPTION_SALT", "test-salt-16chars!")
os.environ.setdefault("DEBUG", "true")

from contextlib import asynccontextmanager
from unittest.mock import patch

from app.services.legal_tools.service import LegalToolsService


class _Resp:
    def __init__(self, status_code: int, data: dict):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"unexpected raise_for_status on {self.status_code}")


class _Client:
    def __init__(self, routes: dict):
        self.routes = routes

    async def get(self, url: str, headers=None):
        for key, resp in self.routes.items():
            if key in url:
                return resp
        return _Resp(404, {})


def _patch_client(routes: dict):
    @asynccontextmanager
    async def _cm(timeout=None):
        yield _Client(routes)

    return patch("app.services.legal_tools._case_lookup.cl_client", _cm)


async def test_get_case_detail_resolves_cluster_id():
    svc = LegalToolsService()
    svc.api_token = "test-token"
    routes = {
        "/clusters/10590063/": _Resp(
            200,
            {
                "case_name": "Foo v. Bar",
                "sub_opinions": ["https://www.courtlistener.com/api/rest/v4/opinions/999/"],
                "citations": [],
                "court": "",
                "date_filed": "2020-01-01",
                "citation_count": 3,
                "precedential_status": "Published",
            },
        ),
        "/opinions/999/": _Resp(200, {"plain_text": "The opinion text here."}),
    }
    with _patch_client(routes):
        result = await svc.get_case_detail(10590063)
    assert result is not None
    assert result["id"] == 10590063
    assert result["case_name"] == "Foo v. Bar"
    assert "opinion text" in result["opinion_text"]


async def test_get_case_detail_falls_back_to_opinion_id():
    svc = LegalToolsService()
    svc.api_token = "test-token"
    routes = {
        "/clusters/55/": _Resp(404, {}),
        "/opinions/55/": _Resp(
            200,
            {"plain_text": "Op text", "cluster": "https://www.courtlistener.com/api/rest/v4/clusters/77/"},
        ),
        "/clusters/77/": _Resp(200, {"case_name": "Baz v. Qux"}),
    }
    with _patch_client(routes):
        result = await svc.get_case_detail(55)
    assert result is not None
    assert result["case_name"] == "Baz v. Qux"
    assert result["id"] == 55


async def test_get_case_detail_returns_none_when_truly_absent():
    svc = LegalToolsService()
    svc.api_token = "test-token"
    routes = {"/clusters/1/": _Resp(404, {}), "/opinions/1/": _Resp(404, {})}
    with _patch_client(routes):
        result = await svc.get_case_detail(1)
    assert result is None
