"""
Integration tests for the Branding Router (/branding).
"""

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.usefixtures("no_rate_limit")

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
            return_value="/api/v1/branding/assets/brand_logo_0123abcd.png",
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


class TestBrandingAssetRoute:
    """GET /branding/assets/{name} — public, serves uploaded logos only."""

    def test_uploaded_logo_is_served_without_auth(self, client, auth_headers, tmp_path):
        from app.services import branding

        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
        with (
            patch.object(branding, "BRANDING_ASSET_DIR", tmp_path / "branding"),
            patch("app.services.branding._remove_uploaded_asset"),
        ):
            uploaded = client.post(
                "/api/v1/branding/logo",
                files={"file": ("logo.png", png, "image/png")},
                headers=auth_headers,
            )
            assert uploaded.status_code == 200, uploaded.text
            logo_url = uploaded.json()["logo_url"]
            assert logo_url.startswith("/api/v1/branding/assets/brand_logo_")

            # The URL the API hands out actually resolves — no auth (login page).
            served = client.get(logo_url)
            assert served.status_code == 200
            assert served.content == png
            assert served.headers["content-type"] == "image/png"
            assert served.headers["x-content-type-options"] == "nosniff"

            # ...and GET /branding reports the same URL.
            assert client.get("/api/v1/branding").json()["logo_url"] == logo_url

        client.post("/api/v1/branding/reset", headers=auth_headers)

    @pytest.mark.parametrize(
        "name",
        ["index.json", "brand_logo_nothex.png", "brand_logo_0123abcd.svg", "..%2F.user_keys.json"],
    )
    def test_other_files_are_not_served(self, client, name, tmp_path):
        from app.services import branding

        with patch.object(branding, "BRANDING_ASSET_DIR", tmp_path):
            assert client.get(f"/api/v1/branding/assets/{name}").status_code == 404


class TestBrandingValidation:
    """PUT /branding rejects values that would be unsafe on the public login page."""

    @pytest.mark.parametrize(
        "body",
        [
            {"logo_url": "javascript:alert(1)"},
            {"logo_url": "data:image/svg+xml;base64,PHN2Zz4="},
            {"logo_url": "http://insecure.example.com/logo.png"},
            {"logo_url": "//evil.example.com/logo.png"},
            {"favicon_url": "https://example.com/a b.ico"},
            {"primary_color": "red; background: url(https://evil.example.com)"},
            {"accent_color": "#12"},
            {"secondary_color": "rgb(0,0,0)"},
            {"custom_css": "a" * 50_001},
        ],
    )
    def test_unsafe_values_are_rejected(self, client, auth_headers, body):
        with patch("app.routers.branding._update_branding", new_callable=AsyncMock) as update:
            response = client.put("/api/v1/branding", json=body, headers=auth_headers)
        assert response.status_code == 422
        update.assert_not_awaited()

    def test_safe_values_are_accepted_and_audited(self, client, auth_headers, audit_events):
        body = {
            "logo_url": "https://cdn.example.com/logo.png",
            "favicon_url": "/api/v1/branding/assets/brand_logo_0123abcd.png",
            "primary_color": "#1A2B3C",
            "accent_color": "#abc",
        }
        with patch(
            "app.routers.branding._update_branding",
            new_callable=AsyncMock,
            return_value={**BRANDING_DEFAULTS, **body},
        ) as update:
            response = client.put("/api/v1/branding", json=body, headers=auth_headers)
        assert response.status_code == 200
        assert update.await_args.kwargs["logo_url"] == body["logo_url"]
        assert [e["details"]["action"] for e in audit_events] == ["branding_updated"]
        assert audit_events[0]["resource_type"] == "branding"

    def test_reset_and_logo_upload_are_audited(self, client, auth_headers, audit_events):
        with (
            patch(
                "app.routers.branding._reset_branding",
                new_callable=AsyncMock,
                return_value=BRANDING_DEFAULTS,
            ),
            patch(
                "app.routers.branding._upload_logo",
                new_callable=AsyncMock,
                return_value="/api/v1/branding/assets/brand_logo_0123abcd.png",
            ),
        ):
            client.post("/api/v1/branding/reset", headers=auth_headers)
            client.post(
                "/api/v1/branding/logo",
                files={"file": ("logo.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, "image/png")},
                headers=auth_headers,
            )
        assert [e["details"]["action"] for e in audit_events] == [
            "branding_reset",
            "branding_logo_uploaded",
        ]


class TestCustomCssSanitizer:
    """custom_css is served to the unauthenticated login page."""

    @pytest.mark.parametrize(
        "css",
        [
            "body { background: url(https://evil.example.com/t.gif) }",
            'body { background: url("//evil.example.com/t.gif") }',
            "body { background: URL( 'http://evil.example.com/t.gif' ) }",
            r"body { background: url(\68ttps://evil.example.com/t.gif) }",
            'input[value^="a"] { background: image-set("https://evil.example.com/a" 1x) }',
            "@import url(https://evil.example.com/x.css);",
            "body { background: url(data:image/svg+xml;base64,PHN2Zz4=) }",
        ],
    )
    def test_external_and_active_resources_are_removed(self, css):
        from app.routers.branding import _sanitize_custom_css

        cleaned = _sanitize_custom_css(css)
        assert "evil.example.com" not in cleaned or "url" not in cleaned.lower()
        assert "url(" not in cleaned.lower().replace(" ", "")
        assert "image-set" not in cleaned.lower()
        assert "@import" not in cleaned.lower()

    @pytest.mark.parametrize(
        "css",
        [
            "body { background: url(/api/v1/branding/assets/brand_logo_0123abcd.png) }",
            'body { background: url("/static/bg.png") no-repeat }',
            "i { background: url(data:image/png;base64,iVBORw0KGgo=) }",
            ".btn { color: #fff; border-radius: 4px }",
        ],
    )
    def test_same_origin_and_inline_raster_images_survive(self, css):
        from app.routers.branding import _sanitize_custom_css

        assert _sanitize_custom_css(css) == css

    def test_style_breakout_is_neutralised(self):
        from app.routers.branding import _sanitize_custom_css

        cleaned = _sanitize_custom_css("</style><script>alert(1)</script>")
        assert "<" not in cleaned and ">" not in cleaned
