"""HTTP-level tests for the workspace-sessions router (/api/v1/workspace-sessions).

Cross-user access is covered in test_tenant_isolation.py; these cover
authentication, the CRUD happy path, the payload cap and audit events.
"""

import pytest
from app.models.tracking import WorkspaceSessionDB
from app.services.audit import AuditEventType

from tests.helpers import db_count, headers, insert_db_user, make_user

pytestmark = pytest.mark.usefixtures("no_rate_limit")

BASE = "/api/v1/workspace-sessions"


@pytest.fixture
def owner():
    # workspace_sessions.user_id has an FK to users, so the owner needs a row.
    user = make_user("ws-user")
    insert_db_user(user)
    return user


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", ""), ("post", ""), ("get", "/abc"), ("put", "/abc"), ("delete", "/abc")],
)
def test_requires_authentication(client, method, path):
    assert getattr(client, method)(f"{BASE}{path}").status_code == 401


def test_create_list_get_update_delete(client, owner, audit_events):
    h = headers(owner)

    created = client.post(
        BASE,
        json={"surface": "contracts", "title": "NDA review", "payload": {"messages": ["hi"]}},
        headers=h,
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]
    assert created.json()["surface"] == "contracts"

    listed = client.get(BASE, headers=h)
    assert listed.status_code == 200
    assert [s["id"] for s in listed.json()["sessions"]] == [session_id]
    assert "payload" not in listed.json()["sessions"][0]  # summaries only

    fetched = client.get(f"{BASE}/{session_id}", headers=h)
    assert fetched.status_code == 200
    assert fetched.json()["payload"] == {"messages": ["hi"]}

    updated = client.put(
        f"{BASE}/{session_id}",
        json={"title": "NDA review (v2)", "payload": {"messages": ["hi", "there"]}},
        headers=h,
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "NDA review (v2)"
    assert client.get(f"{BASE}/{session_id}", headers=h).json()["payload"] == {
        "messages": ["hi", "there"]
    }

    deleted = client.delete(f"{BASE}/{session_id}", headers=h)
    assert deleted.status_code == 200
    assert deleted.json() == {"status": "deleted", "id": session_id}
    assert db_count(WorkspaceSessionDB, WorkspaceSessionDB.id == session_id) == 0
    assert client.get(f"{BASE}/{session_id}", headers=h).status_code == 404

    # Two reads and the delete are audited; the autosave PUT is not.
    kinds = [(e["event_type"], e["resource_id"]) for e in audit_events]
    assert kinds == [
        (AuditEventType.DATA_ACCESS, session_id),
        (AuditEventType.DATA_ACCESS, session_id),
        (AuditEventType.DATA_DELETION, session_id),
    ]
    assert all(e["details"] == {"surface": "contracts"} for e in audit_events)


def test_oversized_payload_is_rejected(client, owner):
    resp = client.post(
        BASE,
        json={"surface": "contracts", "title": "big", "payload": {"blob": "x" * 2_000_001}},
        headers=headers(owner),
    )
    assert resp.status_code == 413
    assert db_count(WorkspaceSessionDB, WorkspaceSessionDB.user_id == owner.id) == 0


def test_title_is_required(client, owner):
    resp = client.post(BASE, json={"surface": "contracts", "title": ""}, headers=headers(owner))
    assert resp.status_code == 422


@pytest.mark.parametrize("limit", [0, 201])
def test_list_limit_is_bounded(client, owner, limit):
    assert client.get(f"{BASE}?limit={limit}", headers=headers(owner)).status_code == 422
