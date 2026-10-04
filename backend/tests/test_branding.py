"""
Unit tests for the Branding service.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest


class TestBrandingService:
    """Tests for the branding service module-level functions."""

    # ------------------------------------------------------------------ #
    # _serialize helper
    # ------------------------------------------------------------------ #

    def test_serialize_uses_defaults_for_none_fields(self):
        """_serialize should fall back to DEFAULT_BRANDING when row fields are None."""
        from app.services.branding import DEFAULT_BRANDING, _serialize

        row = MagicMock()
        row.firm_name = None
        row.logo_url = None
        row.primary_color = None
        row.secondary_color = None
        row.accent_color = None
        row.favicon_url = None
        row.custom_css = None
        row.updated_at = None

        result = _serialize(row)

        assert result["firm_name"] == DEFAULT_BRANDING["firm_name"]
        assert result["primary_color"] == DEFAULT_BRANDING["primary_color"]
        assert result["secondary_color"] == DEFAULT_BRANDING["secondary_color"]
        assert result["accent_color"] == DEFAULT_BRANDING["accent_color"]
        assert result["updated_at"] is None

    def test_serialize_uses_row_values_when_present(self):
        """_serialize should use the row's own values when they are not None."""
        from app.services.branding import _serialize

        now = datetime(2024, 6, 1, 12, 0, 0)
        row = MagicMock()
        row.firm_name = "Smith & Co"
        row.logo_url = "/logo.png"
        row.primary_color = "#FF0000"
        row.secondary_color = "#00FF00"
        row.accent_color = "#0000FF"
        row.favicon_url = "/fav.ico"
        row.custom_css = "body{}"
        row.updated_at = now

        result = _serialize(row)

        assert result["firm_name"] == "Smith & Co"
        assert result["logo_url"] == "/logo.png"
        assert result["primary_color"] == "#FF0000"
        assert result["custom_css"] == "body{}"
        assert result["updated_at"] == now.isoformat()

    # ------------------------------------------------------------------ #
    # get_branding
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_get_branding_no_row_returns_defaults(self):
        """get_branding with no DB row returns DEFAULT_BRANDING."""
        from app.services.branding import DEFAULT_BRANDING, get_branding

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.branding.get_db_context", return_value=mock_ctx):
            result = await get_branding()

        assert result["firm_name"] == DEFAULT_BRANDING["firm_name"]
        assert result["updated_at"] is None

    @pytest.mark.asyncio
    async def test_get_branding_db_error_returns_defaults(self):
        """get_branding should return defaults on database error."""
        from app.services.branding import DEFAULT_BRANDING, get_branding

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=OSError("DB connection failed"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.branding.get_db_context", return_value=mock_ctx):
            result = await get_branding()

        assert result["firm_name"] == DEFAULT_BRANDING["firm_name"]
        assert result["updated_at"] is None

    @pytest.mark.asyncio
    async def test_get_branding_with_existing_row(self):
        """get_branding should return serialized row data when a row exists."""
        from app.services.branding import get_branding

        row = MagicMock()
        row.firm_name = "My Firm"
        row.logo_url = "/logo.png"
        row.primary_color = "#123456"
        row.secondary_color = "#654321"
        row.accent_color = "#ABCDEF"
        row.favicon_url = None
        row.custom_css = None
        row.updated_at = datetime(2024, 3, 1, 10, 0, 0)

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = row

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.branding.get_db_context", return_value=mock_ctx):
            result = await get_branding()

        assert result["firm_name"] == "My Firm"
        assert result["primary_color"] == "#123456"

    # ------------------------------------------------------------------ #
    # update_branding
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_update_branding_applies_changes(self):
        """update_branding should update only the provided fields."""
        from app.services.branding import update_branding

        row = MagicMock()
        row.firm_name = "Old Firm"
        row.logo_url = None
        row.primary_color = "#000000"
        row.secondary_color = "#111111"
        row.accent_color = "#222222"
        row.favicon_url = None
        row.custom_css = None
        row.updated_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = row

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.flush = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.branding.get_db_context", return_value=mock_ctx):
            _result = await update_branding(firm_name="New Firm", primary_color="#FF0000")

        assert row.firm_name == "New Firm"
        assert row.primary_color == "#FF0000"
        # secondary_color should not have changed
        assert row.secondary_color == "#111111"

    # ------------------------------------------------------------------ #
    # upload_logo
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_upload_logo_saves_file_and_updates_config(self):
        """upload_logo should write file and update branding row."""
        from app.services.branding import upload_logo

        row = MagicMock()
        row.logo_url = None
        row.updated_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = row

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.flush = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        m_open = mock_open()
        with (
            patch("app.services.branding.get_db_context", return_value=mock_ctx),
            patch("os.makedirs"),
            patch("builtins.open", m_open),
        ):
            url = await upload_logo(b"PNG_DATA", "image/png")

        # Served by GET /api/v1/branding/assets/<name> — a route that exists.
        assert url.startswith("/api/v1/branding/assets/brand_logo_")
        assert url.endswith(".png")
        m_open.assert_called_once()
        assert row.logo_url == url

    @pytest.mark.asyncio
    async def test_upload_logo_jpeg_extension(self):
        """upload_logo should use .jpg extension for JPEG content type."""
        from app.services.branding import upload_logo

        row = MagicMock()
        row.logo_url = None
        row.updated_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = row

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.flush = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        m_open = mock_open()
        with (
            patch("app.services.branding.get_db_context", return_value=mock_ctx),
            patch("os.makedirs"),
            patch("builtins.open", m_open),
            patch("app.services.branding.settings") as mock_settings,
        ):
            mock_settings.upload_dir = "/tmp/uploads"
            url = await upload_logo(b"JPEG_DATA", "image/jpeg")

        assert url.endswith(".jpg")

    # ------------------------------------------------------------------ #
    # reset_branding
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_reset_branding_restores_defaults(self):
        """reset_branding should set all fields back to DEFAULT_BRANDING."""
        from app.services.branding import DEFAULT_BRANDING, reset_branding

        row = MagicMock()
        row.firm_name = "Custom Firm"
        row.logo_url = "/custom.png"
        row.primary_color = "#FFFFFF"
        row.secondary_color = "#FFFFFF"
        row.accent_color = "#FFFFFF"
        row.favicon_url = "/fav.ico"
        row.custom_css = "h1{color:red}"
        row.updated_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = row

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.flush = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.branding.get_db_context", return_value=mock_ctx):
            await reset_branding()

        assert row.firm_name == DEFAULT_BRANDING["firm_name"]
        assert row.logo_url == DEFAULT_BRANDING["logo_url"]
        assert row.primary_color == DEFAULT_BRANDING["primary_color"]
        assert row.secondary_color == DEFAULT_BRANDING["secondary_color"]
        assert row.accent_color == DEFAULT_BRANDING["accent_color"]
        assert row.favicon_url == DEFAULT_BRANDING["favicon_url"]
        assert row.custom_css == DEFAULT_BRANDING["custom_css"]


class TestBrandingAssets:
    """Uploaded logos live in their own directory and are resolvable by name."""

    @pytest.mark.asyncio
    async def test_upload_writes_outside_the_document_upload_dir(self, tmp_path):
        from app.services import branding

        row = MagicMock()
        row.logo_url = None
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = row
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        asset_dir = tmp_path / "branding"
        with (
            patch.object(branding, "BRANDING_ASSET_DIR", asset_dir),
            patch.object(branding, "get_db_context", return_value=mock_ctx),
        ):
            first = await branding.upload_logo(b"first", "image/png")
            name = first.rsplit("/", 1)[1]
            assert (asset_dir / name).read_bytes() == b"first"
            assert branding.resolve_asset_path(name) == asset_dir / name

            # Replacing the logo removes the previous file.
            second = await branding.upload_logo(b"second", "image/webp")
            assert not (asset_dir / name).exists()
            assert (asset_dir / second.rsplit("/", 1)[1]).read_bytes() == b"second"

    @pytest.mark.parametrize(
        "name",
        [
            "../.user_keys.json",
            "..%2f.instance_secrets.json",
            "index.json",
            "brand_logo_zzzzzzzz.png",
            "brand_logo_0123abcd.exe",
            "brand_logo_0123abcd.png/../../x",
            "",
        ],
    )
    def test_resolve_rejects_anything_but_generated_names(self, name, tmp_path):
        from app.services import branding

        with patch.object(branding, "BRANDING_ASSET_DIR", tmp_path):
            assert branding.resolve_asset_path(name) is None

    def test_legacy_logo_url_is_mapped_to_the_served_route(self, tmp_path):
        """Logos saved under the old, never-served /static/uploads/ URL still load."""
        from app.services import branding

        (tmp_path / "brand_logo_0123abcd.png").write_bytes(b"x")
        with patch.object(branding, "BRANDING_ASSET_DIR", tmp_path):
            assert (
                branding._public_logo_url("/static/uploads/brand_logo_0123abcd.png")
                == "/api/v1/branding/assets/brand_logo_0123abcd.png"
            )
            # A legacy URL whose file is gone is dropped rather than left broken.
            assert branding._public_logo_url("/static/uploads/brand_logo_ffffffff.png") is None
        assert branding._public_logo_url("https://cdn.example.com/logo.png") == (
            "https://cdn.example.com/logo.png"
        )
        assert branding._public_logo_url(None) is None
