"""
Unit tests for the TextExtraction service.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from unittest.mock import patch

import pytest
from app.services.text_extraction import (
    ExtractionResult,
    TextExtractionService,
    text_extraction_service,
)


@pytest.fixture
def service():
    """Create a fresh TextExtractionService."""
    return TextExtractionService()


# =============================================================================
# ExtractionResult Tests
# =============================================================================


class TestExtractionResult:
    """Tests for ExtractionResult dataclass."""

    def test_default_values(self):
        result = ExtractionResult()
        assert result.text == ""
        assert result.tables == []
        assert result.page_count == 0
        assert result.ocr_used is False
        assert result.char_count == 0
        assert result.word_count == 0

    def test_custom_values(self):
        result = ExtractionResult(
            text="Hello world",
            tables=["| A | B |"],
            page_count=5,
            ocr_used=True,
            char_count=11,
            word_count=2,
        )
        assert result.text == "Hello world"
        assert len(result.tables) == 1
        assert result.page_count == 5
        assert result.ocr_used is True


# =============================================================================
# Format Detection Tests
# =============================================================================


class TestDetectFormat:
    """Tests for _detect_format."""

    def test_detect_pdf_by_content_type(self, service):
        fmt = service._detect_format(b"", "application/pdf", "")
        assert fmt == "pdf"

    def test_detect_pdf_by_filename(self, service):
        fmt = service._detect_format(b"", "", "document.pdf")
        assert fmt == "pdf"

    def test_detect_pdf_by_magic_bytes(self, service):
        fmt = service._detect_format(b"%PDF-1.7", "", "")
        assert fmt == "pdf"

    def test_detect_docx_by_content_type(self, service):
        fmt = service._detect_format(
            b"",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "",
        )
        assert fmt == "docx"

    def test_detect_docx_by_filename(self, service):
        fmt = service._detect_format(b"", "", "contract.docx")
        assert fmt == "docx"

    def test_detect_docx_by_magic_bytes(self, service):
        fmt = service._detect_format(b"PK\x03\x04", "", "")
        assert fmt == "docx"

    def test_detect_txt_by_content_type(self, service):
        fmt = service._detect_format(b"", "text/plain", "")
        assert fmt == "txt"

    def test_detect_txt_by_filename(self, service):
        fmt = service._detect_format(b"", "", "notes.txt")
        assert fmt == "txt"

    def test_detect_rtf(self, service):
        # RTF gets its own converter now (striprtf) instead of raw-text decode.
        fmt = service._detect_format(b"", "", "document.rtf")
        assert fmt == "rtf"

    def test_detect_doc_as_docx(self, service):
        fmt = service._detect_format(b"", "", "old_document.doc")
        assert fmt == "docx"

    def test_unknown_defaults_to_txt(self, service):
        fmt = service._detect_format(b"\x00\x01\x02", "", "unknown.xyz")
        assert fmt == "txt"

    def test_case_insensitive_filename(self, service):
        fmt = service._detect_format(b"", "", "Contract.PDF")
        assert fmt == "pdf"


# =============================================================================
# TXT Extraction Tests
# =============================================================================


class TestExtractTxt:
    """Tests for _extract_txt."""

    def test_utf8_text(self, service):
        content = b"Hello, World!"
        result = service._extract_txt(content)
        assert result.text == "Hello, World!"

    def test_latin1_text(self, service):
        # Use a string with multiple latin-1 chars that break utf-8 decoding
        text = "R\xe9sum\xe9 of the caf\xe9"
        content = text.encode("latin-1")
        result = service._extract_txt(content)
        # Should successfully decode (either as utf-8 with errors or latin-1 fallback)
        assert isinstance(result.text, str)
        assert len(result.text) > 0

    def test_empty_content(self, service):
        result = service._extract_txt(b"")
        assert result.text == ""

    def test_utf16_text(self, service):
        content = "Unicode text".encode("utf-16")
        result = service._extract_txt(content)
        assert "Unicode" in result.text

    def test_binary_garbage_falls_back(self, service):
        # Random bytes that can't be decoded cleanly
        content = bytes(range(128, 256))
        result = service._extract_txt(content)
        # Should not raise, falls back to latin-1 or errors='ignore'
        assert isinstance(result.text, str)


# =============================================================================
# Full Extract Method Tests
# =============================================================================


class TestExtract:
    """Tests for the main extract method."""

    def test_extract_txt_from_content(self, service):
        content = b"This is a test document with some text."
        result = service.extract(file_content=content, filename="test.txt")

        assert "test document" in result.text
        assert result.char_count > 0
        assert result.word_count > 0

    def test_extract_with_no_content_and_no_path(self, service):
        result = service.extract()
        assert result.text == ""
        assert result.char_count == 0
        assert result.word_count == 0

    def test_extract_counts_words_correctly(self, service):
        content = b"one two three four five"
        result = service.extract(file_content=content, filename="test.txt")
        assert result.word_count == 5

    def test_extract_empty_text_word_count_zero(self, service):
        content = b"   "
        result = service.extract(file_content=content, filename="test.txt")
        assert result.word_count == 0

    def test_extract_from_file_path(self, service, tmp_path):
        file = tmp_path / "test.txt"
        file.write_bytes(b"File content from disk.")

        result = service.extract(file_path=str(file))
        assert "File content from disk." in result.text

    def test_extract_pdf_without_libraries(self, service):
        with (
            patch("app.services.text_extraction.PDFPLUMBER_AVAILABLE", False),
            patch("app.services.text_extraction.PYPDF_AVAILABLE", False),
        ):
            result = service._extract_pdf(b"%PDF-1.7 fake pdf content")
            assert result.text == ""


# =============================================================================
# Rows to Markdown Tests
# =============================================================================


class TestRowsToMarkdown:
    """Tests for _rows_to_markdown."""

    def test_basic_table(self, service):
        rows = [
            ["Name", "Age", "Role"],
            ["Alice", "30", "Attorney"],
            ["Bob", "45", "Partner"],
        ]
        md = service._rows_to_markdown(rows)
        assert "| Name | Age | Role |" in md
        assert "| --- | --- | --- |" in md
        assert "| Alice | 30 | Attorney |" in md

    def test_empty_rows(self, service):
        md = service._rows_to_markdown([])
        assert md == ""

    def test_none_cells_converted_to_empty(self, service):
        rows = [
            ["Header", None],
            [None, "Data"],
        ]
        md = service._rows_to_markdown(rows)
        assert "| Header |  |" in md

    def test_uneven_rows_padded(self, service):
        rows = [
            ["A", "B", "C"],
            ["1"],
        ]
        md = service._rows_to_markdown(rows)
        # Row should be padded to 3 columns
        lines = md.split("\n")
        assert len(lines) == 3  # header + separator + data

    def test_newlines_in_cells_removed(self, service):
        rows = [
            ["Header"],
            ["Line1\nLine2"],
        ]
        md = service._rows_to_markdown(rows)
        assert "\n" not in md.split("\n")[2]  # data row should not have embedded newline


# =============================================================================
# Singleton Tests
# =============================================================================


class TestSingleton:
    """Tests for the module-level singleton."""

    def test_singleton_exists(self):
        assert text_extraction_service is not None
        assert isinstance(text_extraction_service, TextExtractionService)

    def test_ocr_threshold_default(self):
        assert TextExtractionService.OCR_THRESHOLD == 50
