"""
Azure AD SSO login — roles come from the local account, never from the token.

The identity provider proves who the caller is. What they may do is the
local ``users.roles`` row: an admin's demotion or promotion applies on the
next SSO login, a first-time user gets the configured default (viewer), and
auto-provisioning can be switched off so only invited accounts can sign in.

DB seeding runs on the TestClient's own event loop (``client.portal``): the
dev SQLite engine uses a StaticPool — one shared connection — so touching it
from pytest's loop while the app loop is mid-request corrupts transactions.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.db_models import User as DBUser
from app.services.auth import auth_service
from fastapi import HTTPException


def _identity(uid: str, email: str) -> dict:
    return {
        "id": uid,
        "email": email,
        "name": "SSO Person",
        "azure_oid": uid,
        "tenant_id": "tenant-1",
    }


async def _seed_coro(uid: str, email: str, roles: list[str], active: bool) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            DBUser(
                id=uid,
                email=email,
                name="Seeded",
                password_hash=None,
                roles=roles,
                email_verified=True,
                is_active=active,
            )
        )
        await session.commit()


async def _roles_coro(uid: str) -> list[str] | None:
    async with AsyncSessionLocal() as session:
        row = await session.get(DBUser, uid)
        return None if row is None else list(row.roles or [])


async def _set_roles_coro(uid: str, roles: list[str]) -> None:
    async with AsyncSessionLocal() as session:
        row = await session.get(DBUser, uid)
        row.roles = roles
        await session.commit()


async def _cleanup_coro(uids: tuple[str, ...]) -> None:
    async with AsyncSessionLocal() as session:
        for uid in uids:
            row = await session.get(DBUser, uid)
            if row is not None:
                await session.delete(row)
        await session.commit()


class _Db:
    """Run DB coroutines on the app's loop, serialized with request handling."""

    def __init__(self, client):
        self._portal = client.portal
        self._created: list[str] = []

    def seed(self, uid: str, email: str, roles: list[str], active: bool = True) -> None:
        self._created.append(uid)
        self._portal.call(_seed_coro, uid, email, roles, active)

    def track(self, *uids: str) -> None:
        self._created.extend(uids)

    def roles(self, uid: str) -> list[str] | None:
        return self._portal.call(_roles_coro, uid)

    def set_roles(self, uid: str, roles: list[str]) -> None:
        self._portal.call(_set_roles_coro, uid, roles)

    def cleanup(self) -> None:
        self._portal.call(_cleanup_coro, tuple(self._created))


@pytest.fixture
def db(client):
    handle = _Db(client)
    yield handle
    handle.cleanup()


@pytest.fixture
def sso(client):
    """Patch Azure token verification; yields a function that logs in as `identity`."""

    def login(identity: dict):
        with patch.object(auth_service, "verify_azure_identity", AsyncMock(return_value=identity)):
            return client.post("/api/v1/auth/azure/login", json={"token": "azure-token"})

    return login


def _token_roles(access_token: str) -> list[str]:
    return auth_service.verify_token(access_token).roles


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class TestRolesComeFromTheDatabase:
    def test_first_time_user_is_provisioned_as_viewer_not_attorney(self, sso, db):
        uid = _uid("sso-new")
        db.track(uid)
        resp = sso(_identity(uid, f"{uid}@firm.example"))
        assert resp.status_code == 200, resp.text
        assert _token_roles(resp.json()["access_token"]) == ["viewer"]
        assert resp.json()["user"]["roles"] == ["viewer"]
        assert db.roles(uid) == ["viewer"]

    def test_existing_admin_gets_admin_token(self, sso, db):
        uid = _uid("sso-admin")
        db.seed(uid, f"{uid}@firm.example", ["admin"])
        resp = sso(_identity(uid, f"{uid}@firm.example"))
        assert resp.status_code == 200, resp.text
        assert _token_roles(resp.json()["access_token"]) == ["admin"]

    def test_demoted_user_gets_demoted_token_on_next_login(self, sso, db):
        uid = _uid("sso-demoted")
        db.seed(uid, f"{uid}@firm.example", ["attorney"])
        first = sso(_identity(uid, f"{uid}@firm.example"))
        assert _token_roles(first.json()["access_token"]) == ["attorney"]

        db.set_roles(uid, ["viewer"])

        second = sso(_identity(uid, f"{uid}@firm.example"))
        assert second.status_code == 200
        assert _token_roles(second.json()["access_token"]) == ["viewer"]

    def test_token_never_carries_a_role_absent_from_the_row(self, sso, db):
        uid = _uid("sso-para")
        db.seed(uid, f"{uid}@firm.example", ["paralegal"])
        resp = sso(_identity(uid, f"{uid}@firm.example"))
        roles = _token_roles(resp.json()["access_token"])
        assert "attorney" not in roles
        assert roles == ["paralegal"]

    def test_invited_by_email_row_is_adopted_not_duplicated(self, sso, db):
        """An admin invited this person by email; their first SSO login (with a
        different Azure object id) must attach to that row and its roles."""
        invited_id = _uid("invited")
        email = f"{invited_id}@firm.example"
        db.seed(invited_id, email, ["attorney"])
        azure_oid = _uid("oid")
        db.track(azure_oid)

        resp = sso(_identity(azure_oid, email.upper()))
        assert resp.status_code == 200, resp.text
        assert resp.json()["user"]["id"] == invited_id
        assert _token_roles(resp.json()["access_token"]) == ["attorney"]
        assert db.roles(azure_oid) is None


class TestLifecycle:
    def test_disabled_account_is_refused(self, sso, db):
        uid = _uid("sso-off")
        db.seed(uid, f"{uid}@firm.example", ["attorney"], active=False)
        resp = sso(_identity(uid, f"{uid}@firm.example"))
        assert resp.status_code == 403

    def test_auto_provision_off_refuses_unknown_identity(self, sso, db):
        uid = _uid("sso-stranger")
        db.track(uid)
        locked = settings.model_copy(update={"azure_sso_auto_provision": False})
        with patch("app.routers.auth.settings", locked):
            resp = sso(_identity(uid, f"{uid}@firm.example"))
        assert resp.status_code == 403
        assert "invite" in resp.json()["detail"].lower()
        assert db.roles(uid) is None

    def test_auto_provision_off_still_admits_invited_user(self, sso, db):
        uid = _uid("sso-invited")
        db.seed(uid, f"{uid}@firm.example", ["viewer"])
        locked = settings.model_copy(update={"azure_sso_auto_provision": False})
        with patch("app.routers.auth.settings", locked):
            resp = sso(_identity(uid, f"{uid}@firm.example"))
        assert resp.status_code == 200

    def test_invalid_azure_token_is_401(self, client):
        with patch.object(
            auth_service,
            "verify_azure_identity",
            AsyncMock(side_effect=HTTPException(status_code=401, detail="bad")),
        ):
            resp = client.post("/api/v1/auth/azure/login", json={"token": "nope"})
        assert resp.status_code == 401


class TestDefaultRoleConfig:
    @pytest.mark.parametrize(
        "configured,expected",
        [
            ("viewer", "viewer"),
            ("paralegal", "paralegal"),
            ("attorney", "attorney"),
            ("Attorney ", "attorney"),
            ("admin", "viewer"),  # never hand out admin on first login
            ("wizard", "viewer"),  # unknown → fail safe
            ("", "viewer"),
        ],
    )
    def test_default_role_resolution(self, configured, expected):
        from app.routers.auth import _azure_default_role

        cfg = settings.model_copy(update={"azure_sso_default_role": configured})
        with patch("app.routers.auth.settings", cfg):
            assert _azure_default_role().value == expected

    def test_configured_default_role_is_applied(self, sso, db):
        uid = _uid("sso-cfg")
        db.track(uid)
        cfg = settings.model_copy(update={"azure_sso_default_role": "paralegal"})
        with patch("app.routers.auth.settings", cfg):
            resp = sso(_identity(uid, f"{uid}@firm.example"))
        assert resp.status_code == 200, resp.text
        assert _token_roles(resp.json()["access_token"]) == ["paralegal"]


class TestIdentityService:
    async def test_identity_carries_no_roles(self):
        with patch.object(
            auth_service,
            "verify_azure_token",
            AsyncMock(
                return_value={
                    "oid": "oid-1",
                    "sub": "sub-1",
                    "email": "a@b.c",
                    "name": "A",
                    "tid": "t",
                    "roles": ["Admin"],  # app-role claims are ignored on purpose
                }
            ),
        ):
            identity = await auth_service.verify_azure_identity("tok")
        assert identity == {
            "id": "oid-1",
            "email": "a@b.c",
            "name": "A",
            "azure_oid": "oid-1",
            "tenant_id": "t",
        }
        assert "roles" not in identity
