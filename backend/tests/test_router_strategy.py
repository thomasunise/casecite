"""HTTP-level tests for the strategy router (POST /api/v1/strategy/brief)."""

from unittest.mock import AsyncMock, patch

import app.main  # noqa: F401 - app.services.strategy only imports cleanly after the RAG package
import pytest
from app.services.strategy import StrategyServiceUnavailable, StrategySynthesisError

from tests.helpers import headers, make_user

pytestmark = pytest.mark.usefixtures("no_rate_limit")

URL = "/api/v1/strategy/brief"
GENERATE = "app.routers.strategy.strategy_service.generate_brief"

BRIEF = {
    "brief": "Lead with the limitation-of-liability clause.",
    "scope": {"documents_considered": 2, "documents_total": 3},
}


def test_requires_authentication(client):
    assert client.post(URL, json={"question": "What is our best argument?"}).status_code == 401


def test_requires_chat_permission(client):
    user = make_user("st-user")
    with patch("app.services.permissions.effective_permissions", AsyncMock(return_value=set())):
        resp = client.post(URL, json={"question": "q"}, headers=headers(user))
    assert resp.status_code == 403


def test_happy_path_scopes_to_the_caller_and_is_audited(client, audit_events):
    user = make_user("st-user")
    with patch(GENERATE, new_callable=AsyncMock, return_value=BRIEF) as generate:
        resp = client.post(
            URL,
            json={"question": "What is our best argument?", "document_ids": ["d1", "d2"]},
            headers=headers(user),
        )
    assert resp.status_code == 200
    assert resp.json() == BRIEF
    kwargs = generate.await_args.kwargs
    assert kwargs["user_id"] == user.id
    assert kwargs["document_ids"] == ["d1", "d2"]

    assert len(audit_events) == 1
    assert audit_events[0]["details"]["action"] == "strategy_brief"
    assert audit_events[0]["details"]["documents_considered"] == 2
    assert audit_events[0]["user_id"] == user.id


def test_blank_question_is_rejected(client):
    user = make_user("st-user")
    assert client.post(URL, json={"question": "   "}, headers=headers(user)).status_code == 422


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (StrategyServiceUnavailable("No AI provider configured"), 503),
        (StrategySynthesisError("Model returned nothing"), 502),
        (LookupError("No documents in scope"), 404),
        (ValueError("Bad scope"), 400),
    ],
)
def test_service_errors_map_to_status_codes(client, audit_events, error, status):
    user = make_user("st-user")
    with patch(GENERATE, new_callable=AsyncMock, side_effect=error):
        resp = client.post(URL, json={"question": "q"}, headers=headers(user))
    assert resp.status_code == status
    assert resp.json()["detail"] == str(error)
    assert audit_events == []  # nothing was produced, so nothing is recorded as accessed
