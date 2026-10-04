"""
Integration tests for the Authentication router (/auth).
"""

import os
from datetime import UTC

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from app.routers.auth import DEV_ACCOUNT_EMAIL


class TestAuthRouter:
    """Tests for /auth endpoints."""

    def test_dev_login_success(self, client, auth_headers):
        """POST /auth/demo/login (dev login, DEBUG=true) with valid credentials returns 200."""
        response = client.post(
            "/api/v1/auth/demo/login",
            json={"email": DEV_ACCOUNT_EMAIL, "password": "demo"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        # Refresh token is delivered exclusively via httpOnly cookie.
        assert "refresh_token" not in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data
        assert data["user"]["email"] == DEV_ACCOUNT_EMAIL
        assert "refresh_token" in response.cookies

    def test_dev_login_wrong_password(self, client):
        """POST /auth/demo/login with wrong password returns 401."""
        response = client.post(
            "/api/v1/auth/demo/login",
            json={"email": DEV_ACCOUNT_EMAIL, "password": "wrong"},
        )
        assert response.status_code == 401

    def test_dev_login_wrong_email(self, client):
        """POST /auth/demo/login with unknown email returns 401."""
        response = client.post(
            "/api/v1/auth/demo/login",
            json={"email": "unknown@example.com", "password": "demo"},
        )
        assert response.status_code == 401

    async def test_refresh_token(self, client):
        """POST /auth/refresh with a valid refresh-token COOKIE returns a new
        access token. The user must exist and be active in the database, and
        the token must belong to a live sign-in session."""
        import uuid
        from datetime import datetime

        from app.database import AsyncSessionLocal
        from app.middleware.security import session_manager
        from app.models.db_models import User as DBUser
        from app.services.auth import User, UserRole, auth_service
        from app.services.passwords import hash_password

        uid = f"refresh-user-{uuid.uuid4().hex[:8]}"
        email = f"{uid}@test.local"
        async with AsyncSessionLocal() as session:
            session.add(
                DBUser(
                    id=uid,
                    email=email,
                    name="Refresh Test",
                    password_hash=hash_password("Xy7!longenoughpass"),
                    roles=["attorney"],
                    email_verified=True,
                    is_active=True,
                )
            )
            await session.commit()

        try:
            test_user = User(
                id=uid,
                email=email,
                name="Refresh Test",
                roles=[UserRole.ATTORNEY],
                last_login=datetime.now(UTC),
            )
            # A refresh token with no session behind it mints nothing.
            orphan = auth_service.create_refresh_token(test_user, session_id="no-such-session")
            client.cookies.set("refresh_token", orphan)
            assert client.post("/api/v1/auth/refresh").status_code == 401
            client.cookies.clear()

            session_manager.create_session(
                uid, "testclient", "pytest", "jti-old", session_id="sid-1"
            )
            refresh_token = auth_service.create_refresh_token(test_user, session_id="sid-1")
            client.cookies.set("refresh_token", refresh_token)

            response = client.post("/api/v1/auth/refresh")
            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"
        finally:
            client.cookies.clear()
            session_manager.terminate_all_sessions(uid)
            async with AsyncSessionLocal() as session:
                row = await session.get(DBUser, uid)
                if row is not None:
                    await session.delete(row)
                    await session.commit()

    def test_refresh_token_not_accepted_from_body(self, client):
        """POST /auth/refresh ignores body tokens — cookie only (no cookie → 401)."""
        from datetime import datetime

        from app.services.auth import User, UserRole, auth_service

        test_user = User(
            id="dev-user-1",
            email=DEV_ACCOUNT_EMAIL,
            name="Dev User",
            roles=[UserRole.VIEWER],
            last_login=datetime.now(UTC),
        )
        refresh_token = auth_service.create_refresh_token(test_user)
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 401

    def test_refresh_token_invalid(self, client):
        """POST /auth/refresh with an invalid cookie token returns 401."""
        client.cookies.set("refresh_token", "invalid.token.value")
        try:
            response = client.post("/api/v1/auth/refresh")
            assert response.status_code == 401
        finally:
            client.cookies.delete("refresh_token")

    def test_logout(self, client, auth_headers):
        """POST /auth/logout with auth returns 200."""
        response = client.post("/api/v1/auth/logout", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "logged_out"

    def test_get_current_user(self, client, auth_headers):
        """GET /auth/me with auth returns user info."""
        response = client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "email" in data
        assert "roles" in data

    def test_get_current_user_no_auth(self, client):
        """GET /auth/me without auth returns 401 or 403."""
        response = client.get("/api/v1/auth/me")
        assert response.status_code in [401, 403]

    def test_get_sessions(self, client, auth_headers):
        """GET /auth/sessions with auth returns session list."""
        response = client.get("/api/v1/auth/sessions", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data

    def test_logout_all_sessions(self, client, auth_headers):
        """POST /auth/logout/all with auth terminates all sessions."""
        response = client.post("/api/v1/auth/logout/all", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "all_sessions_terminated"

    def test_forgot_password(self, client):
        """POST /auth/forgot-password always returns success to prevent email enumeration."""
        response = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "test@casecite.legal"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
