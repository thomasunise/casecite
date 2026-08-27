"""
Integration tests for the Branding Router (/branding).
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from unittest.mock import AsyncMock, patch

BRANDING_DEFAULTS = {
    "firm_name": "CaseCite",
    "logo_url": None,
    "primary_color": "#1a365d",
    "secondary_color": "#2d3748",
    "accent_color": "#3182ce",
    "favicon_url": None,
    "custom_css": None,
    "updated_at": None,
}


class TestBrandingRouter:
    """Tests for /branding endpoints."""

    # ------------------------------------------------------------------ #
    # GET /branding  (public — no auth required)
    # ------------------------------------------------------------------ #

    def test_get_branding_public(self, client):
        """GET /branding returns branding config without auth."""
        with patch(
            "app.routers.branding._get_branding",
            new_callable=AsyncMock,
            return_value=BRANDING_DEFAULTS,
        ):
            response = client.get("/api/v1/branding")
            assert response.status_code == 200
            data = response.json()
            assert "firm_name" in data
            assert "primary_color" in data

    def test_get_branding_with_auth(self, client, auth_headers):
        """GET /branding also works with auth."""
        with patch(
            "app.routers.branding._get_branding",
            new_callable=AsyncMock,
            return_value=BRANDING_DEFAULTS,
        ):
            response = client.get("/api/v1/branding", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert data["firm_name"] == "CaseCite"

    # ------------------------------------------------------------------ #
    # PUT /branding
    # ------------------------------------------------------------------ #

    def test_update_branding_with_auth(self, client, auth_headers):
        """PUT /branding updates branding config when authenticated."""
        updated = {**BRANDING_DEFAULTS, "firm_name": "Acme Legal"}
        with patch(
            "app.routers.branding._update_branding",
            new_callable=AsyncMock,
            return_value=updated,
        ):
            response = client.put(
                "/api/v1/branding",
                json={"firm_name": "Acme Legal"},
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["firm_name"] == "Acme Legal"

    def test_update_branding_no_auth(self, client):
        """PUT /branding without auth returns 401/403."""
        response = client.put("/api/v1/branding", json={"firm_name": "Hacker Corp"})
        assert response.status_code in [401, 403]

    def test_update_branding_service_error(self, client, auth_headers):
        """PUT /branding returns 500 when the service raises an OS-level error."""
        with patch(
            "app.routers.branding._update_branding",
            new_callable=AsyncMock,
            side_effect=OSError("disk full"),
        ):
            response = client.put(
                "/api/v1/branding",
                json={"firm_name": "Crash Corp"},
                headers=auth_headers,
            )
            assert response.status_code == 500

    # ------------------------------------------------------------------ #
    # POST /branding/logo
    # ------------------------------------------------------------------ #

    def test_upload_logo_with_auth(self, client, auth_headers):
        """POST /branding/logo uploads a valid image."""
        with patch(
            "app.routers.branding._upload_logo",
            new_callable=AsyncMock,
            return_value="/static/logos/logo_abc.png",
        ):
            response = client.post(
                "/api/v1/branding/logo",
                files={"file": ("logo.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 100, "image/png")},
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "uploaded"
            assert "logo_url" in data

    def test_upload_logo_no_auth(self, client):
        """POST /branding/logo without auth returns 401/403."""
        response = client.post(
            "/api/v1/branding/logo",
            files={"file": ("logo.png", b"\x89PNG" + b"\x00" * 10, "image/png")},
        )
        assert response.status_code in [401, 403]

    def test_upload_logo_invalid_type(self, client, auth_headers):
        """POST /branding/logo rejects non-image file types."""
        response = client.post(
            "/api/v1/branding/logo",
            files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Invalid file type" in response.json()["detail"]

    def test_upload_logo_too_large(self, client, auth_headers):
        """POST /branding/logo rejects files larger than 2 MB."""
        large_content = b"\x89PNG" + b"\x00" * (3 * 1024 * 1024)  # ~3 MB
        response = client.post(
            "/api/v1/branding/logo",
            files={"file": ("big.png", large_content, "image/png")},
            headers=auth_headers,
        )
        # 413 Payload Too Large — enforced by the shared capped chunked read.
        assert response.status_code == 413
        assert "too large" in response.json()["detail"].lower()

    # ------------------------------------------------------------------ #
    # POST /branding/reset
    # ------------------------------------------------------------------ #

    def test_reset_branding_with_auth(self, client, auth_headers):
        """POST /branding/reset restores defaults when authenticated."""
        with patch(
            "app.routers.branding._reset_branding",
            new_callable=AsyncMock,
            return_value=BRANDING_DEFAULTS,
        ):
            response = client.post("/api/v1/branding/reset", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert data["firm_name"] == "CaseCite"

    def test_reset_branding_no_auth(self, client):
        """POST /branding/reset without auth returns 401/403."""
        response = client.post("/api/v1/branding/reset")
        assert response.status_code in [401, 403]
