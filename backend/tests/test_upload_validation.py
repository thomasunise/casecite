"""
Tests for shared upload validation (app/utils/upload_validation.py) as used by
the cloud picker imports, and for the branding custom-CSS sanitizer fixpoint.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

import pytest
from app.utils.upload_validation import (
    read_upload_capped,
    sanitize_filename,
    validate_import_file,
)

PDF = b"%PDF-1.7 fake pdf body"
HTML = b"<html><script>alert(1)</script></html>"


class TestValidateImportFile:
    def test_accepts_valid_pdf(self):
        name, ctype = validate_import_file(PDF, "application/pdf", "brief.pdf")
        assert name == "brief.pdf"
        assert ctype == "application/pdf"

    def test_resolves_type_from_extension(self):
        _, ctype = validate_import_file(PDF, None, "brief.pdf")
        assert ctype == "application/pdf"

    def test_rejects_unknown_type(self):
        with pytest.raises(ValueError, match="Unsupported file type"):
            validate_import_file(b"MZ\x90\x00", "application/x-msdownload", "evil.exe")

    def test_rejects_html_masquerading_as_pdf(self):
        with pytest.raises(ValueError):
            validate_import_file(HTML, "application/pdf", "evil.pdf")

    def test_rejects_oversized_file(self):
        big = b"a" * (10 * 1024 * 1024 + 1)  # over the 10MB text/plain cap
        with pytest.raises(ValueError, match="too large"):
            validate_import_file(big, "text/plain", "big.txt")

    def test_sanitizes_traversal_filename(self):
        name, _ = validate_import_file(PDF, "application/pdf", "../../etc/passwd.pdf")
        assert "/" not in name and ".." not in name

    def test_accepts_google_export_xlsx(self):
        # OOXML zip container claimed as xlsx (Google Sheets export)
        xlsx = b"PK\x03\x04" + b"\x00" * 32
        _, ctype = validate_import_file(
            xlsx,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "ledger.xlsx",
        )
        assert ctype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class TestSanitizeFilename:
    def test_strips_path_components(self):
        assert sanitize_filename("..\\..\\boot.ini") == "boot.ini"

    def test_empty_becomes_placeholder(self):
        assert sanitize_filename("") == "unnamed_file"


class TestCustomCssSanitizerFixpoint:
    def test_spliced_javascript_url_removed(self):
        from app.routers.branding import _sanitize_custom_css

        # Single-pass removal of "javascript:" would leave "javascript:" behind.
        result = _sanitize_custom_css("a{background:url(javajavascript:script:alert(1))}")
        assert "javascript:" not in result.lower()

    def test_cross_pattern_splice_removed(self):
        from app.routers.branding import _sanitize_custom_css

        # Removing "expression(" splices the fragments into "@import url(...)" —
        # only a repeated pass catches what the first pass created.
        result = _sanitize_custom_css("@imexpression(port url(https://evil.example/x.css);")
        assert "@import" not in result.lower()
        assert "expression(" not in result.lower()

    def test_benign_css_unchanged(self):
        from app.routers.branding import _sanitize_custom_css

        css = ".header { color: #123456; font-weight: bold; }"
        assert _sanitize_custom_css(css) == css


class TestReadUploadCapped:
    """Chunked upload reads enforce the byte cap without full buffering."""

    async def test_under_cap_returns_bytes(self):
        import io as _io

        from starlette.datastructures import UploadFile as StarletteUploadFile

        f = StarletteUploadFile(file=_io.BytesIO(b"x" * 100), filename="a.txt")
        data = await read_upload_capped(f, 1024)
        assert data == b"x" * 100

    async def test_over_cap_raises_413(self):
        import io as _io

        from fastapi import HTTPException
        from starlette.datastructures import UploadFile as StarletteUploadFile

        f = StarletteUploadFile(file=_io.BytesIO(b"x" * 2048), filename="a.txt")
        with pytest.raises(HTTPException) as exc:
            await read_upload_capped(f, 1024, chunk_size=256)
        assert exc.value.status_code == 413

    async def test_content_length_header_rejected_before_read(self):
        import io as _io

        from fastapi import HTTPException
        from starlette.datastructures import UploadFile as StarletteUploadFile
        from starlette.requests import Request as StarletteRequest

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [(b"content-length", b"999999")],
            "query_string": b"",
        }
        request = StarletteRequest(scope)
        f = StarletteUploadFile(file=_io.BytesIO(b""), filename="a.txt")
        with pytest.raises(HTTPException) as exc:
            await read_upload_capped(f, 1024, request=request)
        assert exc.value.status_code == 413
