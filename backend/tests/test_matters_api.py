"""HTTP tests for the Matter API: create, list, get, invite/remove members,
delete — including owner-only enforcement and access scoping.
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars!")
os.environ.setdefault("ENCRYPTION_SALT", "test-salt-16chars!")
os.environ.setdefault("DEBUG", "true")

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from app.models.enums import UserRole
from app.services.auth import User


@pytest.fixture(autouse=True)
def _no_rate_limit():
    with patch(
        "app.middleware.security.RateLimiter.is_allowed",
        return_value=(True, {"limit": 100, "remaining": 99}),
    ):
        yield


def _user(uid: str, email: str) -> User:
    return User(id=uid, email=email, name=uid, roles=[UserRole.ATTORNEY], last_login=datetime.now(UTC))


def _headers(user: User) -> dict:
    from tests.conftest import make_auth_headers

    return make_auth_headers(user)


def _insert_db_user(uid: str, email: str, name: str) -> None:
    """Insert a users row via a direct synchronous SQLite write.

    The app resolves invitees by email against the users table; a direct
    file-committed write is immediately visible to the app's connection,
    avoiding cross-event-loop async-engine visibility flakiness in tests.
    """
    import json
    import sqlite3

    from app.database import async_engine

    path = async_engine.url.database
    con = sqlite3.connect(path, timeout=30)
    try:
        con.execute(
            "INSERT INTO users (id, email, name, password_hash, roles, is_active, "
            "email_verified, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, email, name, "x", json.dumps(["attorney"]), 1, 1,
             datetime.now(UTC).replace(tzinfo=None).isoformat()),
        )
        con.commit()
    finally:
        con.close()


def test_matter_lifecycle_create_invite_access_remove(client):
    suffix = uuid.uuid4().hex[:8]
    owner = _user(f"mowner-{suffix}", f"mowner-{suffix}@casecite.legal")
    # The invitee must exist in the users table for email resolution.
    colleague_id = f"mcolleague-{suffix}"
    colleague_email = f"mcolleague-{suffix}@casecite.legal"
    _insert_db_user(colleague_id, colleague_email, "Colleague")
    colleague = _user(colleague_id, colleague_email)
    stranger = _user(f"mstranger-{suffix}", f"mstranger-{suffix}@casecite.legal")

    # Create a matter.
    created = client.post(
        "/api/v1/matters",
        headers=_headers(owner),
        json={"name": "Acme v. Beta", "client_name": "Acme Corp"},
    )
    assert created.status_code == 201, created.text
    matter = created.json()
    matter_id = matter["id"]
    assert matter["role"] == "owner"
    assert matter["is_personal"] is False
    assert matter["member_count"] == 1

    # It shows in the owner's list (alongside their auto-created personal matter).
    listed = client.get("/api/v1/matters", headers=_headers(owner))
    assert listed.status_code == 200
    names = {m["id"]: m for m in listed.json()["matters"]}
    assert matter_id in names
    assert any(m["is_personal"] for m in listed.json()["matters"])

    # A stranger can't see it.
    assert client.get(f"/api/v1/matters/{matter_id}", headers=_headers(stranger)).status_code == 404

    # Invite the colleague by email.
    invited = client.post(
        f"/api/v1/matters/{matter_id}/members",
        headers=_headers(owner),
        json={"email": colleague_email},
    )
    assert invited.status_code == 200, invited.text
    member_ids = {m["user_id"] for m in invited.json()["members"]}
    assert colleague_id in member_ids
    assert invited.json()["member_count"] == 2

    # The colleague can now see the matter; the stranger still cannot.
    assert client.get(f"/api/v1/matters/{matter_id}", headers=_headers(colleague)).status_code == 200
    assert client.get(f"/api/v1/matters/{matter_id}", headers=_headers(stranger)).status_code == 404

    # Non-owner cannot invite or remove (owner-only), and it 404s (no existence leak).
    assert (
        client.post(
            f"/api/v1/matters/{matter_id}/members",
            headers=_headers(colleague),
            json={"email": colleague_email},
        ).status_code
        == 404
    )

    # Owner removes the colleague.
    removed = client.delete(
        f"/api/v1/matters/{matter_id}/members/{colleague_id}", headers=_headers(owner)
    )
    assert removed.status_code == 200
    assert colleague_id not in {m["user_id"] for m in removed.json()["members"]}
    # Access revoked.
    assert client.get(f"/api/v1/matters/{matter_id}", headers=_headers(colleague)).status_code == 404


def test_invite_unknown_email_404(client):
    owner = _user(f"mo2-{uuid.uuid4().hex[:8]}", f"mo2-{uuid.uuid4().hex[:8]}@casecite.legal")
    created = client.post("/api/v1/matters", headers=_headers(owner), json={"name": "Solo"})
    matter_id = created.json()["id"]
    r = client.post(
        f"/api/v1/matters/{matter_id}/members",
        headers=_headers(owner),
        json={"email": "nobody-here@example.com"},
    )
    assert r.status_code == 404


def test_delete_matter_owner_only(client):
    owner = _user(f"mo3-{uuid.uuid4().hex[:8]}", f"mo3-{uuid.uuid4().hex[:8]}@casecite.legal")
    stranger = _user(f"ms3-{uuid.uuid4().hex[:8]}", f"ms3-{uuid.uuid4().hex[:8]}@casecite.legal")
    matter_id = client.post("/api/v1/matters", headers=_headers(owner), json={"name": "X"}).json()["id"]

    assert client.delete(f"/api/v1/matters/{matter_id}", headers=_headers(stranger)).status_code == 404
    assert client.delete(f"/api/v1/matters/{matter_id}", headers=_headers(owner)).status_code == 200
    assert client.get(f"/api/v1/matters/{matter_id}", headers=_headers(owner)).status_code == 404
