"""End-to-end: documents and chat sessions filed under a shared matter are
visible over the HTTP API to matter members and to no one else.

Seeds the matter + membership rows directly (synchronously) and drives the real
/documents and /chat/sessions endpoints via the test client.
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars!")
os.environ.setdefault("ENCRYPTION_SALT", "test-salt-16chars!")
os.environ.setdefault("DEBUG", "true")

import sqlite3
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from app.database import async_engine
from app.models.enums import DocumentStatus, UserRole
from app.models.schemas import ConnectorType, Document
from app.services.auth import User
from app.services.documents import document_service


def _make_shared_matter(owner_id: str, member_id: str) -> str:
    """Create a shared matter (+ memberships) via a direct synchronous SQLite
    write, so the rows are immediately visible to the app's connection. Async
    cross-event-loop writes here are flakily invisible under load."""
    path = async_engine.url.database
    mid = uuid.uuid4().hex
    now = datetime.now(UTC).replace(tzinfo=None).isoformat()
    con = sqlite3.connect(path, timeout=30)
    try:
        con.execute(
            "INSERT INTO matters (id, name, client_name, owner_id, is_personal, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (mid, "Acme v. Beta", None, owner_id, 0, now, now),
        )
        con.execute(
            "INSERT INTO matter_members (id, matter_id, user_id, role, added_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, mid, owner_id, "owner", owner_id, now),
        )
        if member_id != owner_id:
            con.execute(
                "INSERT INTO matter_members (id, matter_id, user_id, role, added_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, mid, member_id, "member", owner_id, now),
            )
        con.commit()
    finally:
        con.close()
    return mid


def _user(uid: str) -> User:
    return User(
        id=uid,
        email=f"{uid}@casecite.legal",
        name=uid,
        roles=[UserRole.ATTORNEY],
        last_login=datetime.now(UTC),
    )


def _headers(user: User) -> dict:
    from tests.conftest import make_auth_headers

    return make_auth_headers(user)


# Bypass the per-IP rate limiter: every test client request comes from the same
# "testclient" IP, so under the full suite the 50/min document-endpoint bucket is
# already spent and requests 429 before reaching the logic under test. This
# matches the pattern used in test_security.py.
@pytest.fixture(autouse=True)
def _no_rate_limit():
    with patch(
        "app.middleware.security.RateLimiter.is_allowed",
        return_value=(True, {"limit": 100, "remaining": 99}),
    ):
        yield


def test_shared_matter_document_visible_to_member_not_stranger(client):
    owner = _user(f"owner-{uuid.uuid4().hex[:8]}")
    member = _user(f"member-{uuid.uuid4().hex[:8]}")
    stranger = _user(f"stranger-{uuid.uuid4().hex[:8]}")

    matter_id = _make_shared_matter(owner.id, member.id)

    doc_id = f"shared-{uuid.uuid4().hex[:8]}"
    document_service.documents[doc_id] = Document(
        id=doc_id,
        user_id=owner.id,
        matter_id=matter_id,
        filename="acme_msa.pdf",
        content_type="application/pdf",
        size=100,
        source=ConnectorType.LOCAL,
        status=DocumentStatus.INDEXED,
        created_at=datetime.now(UTC),
    )

    try:
        # Owner sees it.
        r = client.get(f"/api/v1/documents/{doc_id}", headers=_headers(owner))
        assert r.status_code == 200, r.text

        # Member sees it in the list AND by id.
        listed = client.get("/api/v1/documents", headers=_headers(member))
        assert listed.status_code == 200
        assert doc_id in {d["id"] for d in listed.json()["documents"]}
        assert (
            client.get(f"/api/v1/documents/{doc_id}", headers=_headers(member)).status_code == 200
        )

        # Stranger (not a member) sees neither.
        listed_s = client.get("/api/v1/documents", headers=_headers(stranger))
        assert doc_id not in {d["id"] for d in listed_s.json()["documents"]}
        assert (
            client.get(f"/api/v1/documents/{doc_id}", headers=_headers(stranger)).status_code == 404
        )
    finally:
        document_service.documents.pop(doc_id, None)


def test_shared_matter_chat_session_visible_to_member_not_stranger(client):
    owner = _user(f"cowner-{uuid.uuid4().hex[:8]}")
    member = _user(f"cmember-{uuid.uuid4().hex[:8]}")
    stranger = _user(f"cstranger-{uuid.uuid4().hex[:8]}")
    matter_id = _make_shared_matter(owner.id, member.id)

    # Owner creates a chat session filed under the shared matter (real endpoint).
    created = client.post(
        "/api/v1/chat/sessions",
        headers=_headers(owner),
        json={"title": "Acme MSA review", "matter_id": matter_id},
    )
    assert created.status_code == 200, created.text
    session_id = created.json()["id"]

    # Member sees it in their list and can open it.
    listed = client.get("/api/v1/chat/sessions", headers=_headers(member))
    assert session_id in {s["id"] for s in listed.json()["sessions"]}
    assert (
        client.get(f"/api/v1/chat/sessions/{session_id}", headers=_headers(member)).status_code
        == 200
    )

    # Stranger sees neither.
    listed_s = client.get("/api/v1/chat/sessions", headers=_headers(stranger))
    assert session_id not in {s["id"] for s in listed_s.json()["sessions"]}
    assert (
        client.get(f"/api/v1/chat/sessions/{session_id}", headers=_headers(stranger)).status_code
        == 404
    )


def test_create_chat_session_in_non_member_matter_is_forbidden(client):
    owner = _user(f"cowner2-{uuid.uuid4().hex[:8]}")
    outsider = _user(f"coutsider-{uuid.uuid4().hex[:8]}")
    matter_id = _make_shared_matter(owner.id, owner.id)
    r = client.post(
        "/api/v1/chat/sessions",
        headers=_headers(outsider),
        json={"title": "sneaky", "matter_id": matter_id},
    )
    assert r.status_code == 403


def test_upload_into_non_member_matter_is_forbidden(client):
    owner = _user(f"owner-{uuid.uuid4().hex[:8]}")
    outsider = _user(f"outsider-{uuid.uuid4().hex[:8]}")
    # A matter the outsider is NOT a member of.
    matter_id = _make_shared_matter(owner.id, owner.id)

    files = {"file": ("x.txt", b"hello world", "text/plain")}
    r = client.post(
        "/api/v1/documents",
        headers=_headers(outsider),
        files=files,
        data={"matter_id": matter_id},
    )
    assert r.status_code == 403


def test_matter_member_can_read_but_not_delete_owners_document_or_chat(client):
    """Membership shares read access. Deleting a colleague's document or chat is
    reserved for the item's owner and the matter's owner."""
    owner = _user(f"owner-{uuid.uuid4().hex[:8]}")
    member = _user(f"member-{uuid.uuid4().hex[:8]}")
    matter_id = _make_shared_matter(owner.id, member.id)

    # The MEMBER files a document and a chat under the matter.
    doc_id = f"shared-{uuid.uuid4().hex[:8]}"
    document_service.documents[doc_id] = Document(
        id=doc_id,
        user_id=member.id,
        matter_id=matter_id,
        filename="member_notes.pdf",
        content_type="application/pdf",
        size=100,
        source=ConnectorType.LOCAL,
        status=DocumentStatus.INDEXED,
        created_at=datetime.now(UTC),
    )
    owner_doc_id = f"shared-{uuid.uuid4().hex[:8]}"
    document_service.documents[owner_doc_id] = document_service.documents[doc_id].model_copy(
        update={"id": owner_doc_id, "user_id": owner.id, "filename": "owner_brief.pdf"}
    )
    owner_chat = client.post(
        "/api/v1/chat/sessions",
        headers=_headers(owner),
        json={"title": "Owner strategy", "matter_id": matter_id},
    ).json()["id"]

    try:
        # The member can read the owner's document and chat...
        assert (
            client.get(f"/api/v1/documents/{owner_doc_id}", headers=_headers(member)).status_code
            == 200
        )
        assert (
            client.get(f"/api/v1/chat/sessions/{owner_chat}", headers=_headers(member)).status_code
            == 200
        )
        # ...but cannot delete either.
        assert (
            client.delete(f"/api/v1/documents/{owner_doc_id}", headers=_headers(member)).status_code
            == 404
        )
        assert owner_doc_id in document_service.documents
        assert (
            client.delete(
                f"/api/v1/chat/sessions/{owner_chat}", headers=_headers(member)
            ).status_code
            == 404
        )
        assert (
            client.get(f"/api/v1/chat/sessions/{owner_chat}", headers=_headers(owner)).status_code
            == 200
        )

        # The matter OWNER can delete a document a member filed under their matter.
        with patch("app.services.documents.rag_service", None):
            resp = client.delete(f"/api/v1/documents/{doc_id}", headers=_headers(owner))
        assert resp.status_code == 200
        assert doc_id not in document_service.documents
    finally:
        document_service.documents.pop(doc_id, None)
        document_service.documents.pop(owner_doc_id, None)
