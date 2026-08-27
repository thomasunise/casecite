"""
Legal-document support endpoints still used by the live UI.

Only the endpoints the source-available build actually calls are kept here:
- GET  /legal-docs/courts        — court list for jurisdiction pickers (Contracts)
- POST /legal-docs/extract-text  — text extraction from an uploaded file
- POST /legal-docs/convert-to-pdf — render an uploaded doc to PDF for the viewer

(The former drafting/templates/discovery routers were removed; these three are
the only pieces live features — Contracts and Case Citations — depend on.)
"""

import io
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.config import settings
from app.services.auth import TokenData, get_current_user
from app.services.courts import get_all_courts
from app.utils.upload_validation import read_upload_capped, validate_import_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/legal-docs", tags=["legal-documents"])


@router.get("/courts")
async def get_courts(
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Get the static list of courts used by jurisdiction pickers.

    Requires authentication (same policy as the /tools research endpoints).
    """
    courts = get_all_courts()
    return {"courts": courts, "count": len(courts)}


@router.post("/extract-text")
async def extract_text_from_file(
    request: Request,
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Extract text content from an uploaded file (PDF, DOCX, DOC, TXT, RTF, MD).

    Requires authentication. The upload is run through the shared allowlist +
    per-type size cap + magic-byte check before it reaches the (expensive,
    OCR-capable) extraction pipeline.
    """
    from app.services.text_extraction import text_extraction_service

    try:
        # Chunked read with a hard cap — an oversized body is rejected before
        # it is buffered into memory (413), then validated per-type below.
        content = await read_upload_capped(file, settings.max_upload_size, request=request)
        # Reject oversized / disallowed / spoofed files before any parsing.
        safe_name, _ = validate_import_file(content, file.content_type, file.filename or "")
        result = text_extraction_service.extract(
            file_content=content,
            filename=safe_name,
        )
        return {
            "success": True,
            "filename": file.filename,
            "text": result.text,
            "char_count": result.char_count,
            "word_count": result.word_count,
            "page_count": result.page_count,
            "tables_found": len(result.tables),
            "ocr_used": result.ocr_used,
        }
    except (ValueError, OSError, UnicodeDecodeError) as e:
        logger.error(f"Failed to extract text: {e}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="Failed to extract text. Please upload a valid PDF, DOCX, TXT, or Markdown file.",
        )


@router.post("/convert-to-pdf")
async def convert_to_pdf(
    request: Request,
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
):
    """Convert an uploaded document to PDF for the visual viewer.

    Requires authentication. PDFs pass through; DOCX and text/markdown are
    rendered with reportlab. The upload is validated (allowlist + per-type size
    cap + magic bytes) before any parsing/rendering.
    """
    try:
        # Chunked read with a hard cap — an oversized body is rejected before
        # it is buffered into memory (413), then validated per-type below.
        content = await read_upload_capped(file, settings.max_upload_size, request=request)
        # Reject oversized / disallowed / spoofed files before any parsing.
        validate_import_file(content, file.content_type, file.filename or "")
        filename = (file.filename or "").lower()

        # PDF — pass through unchanged.
        if filename.endswith(".pdf") or content[:4] == b"%PDF":
            buffer = io.BytesIO(content)
            buffer.seek(0)
            return StreamingResponse(
                buffer,
                media_type="application/pdf",
                headers={"Content-Disposition": "inline; filename=document.pdf"},
            )

        # DOCX — convert via python-docx + reportlab.
        if filename.endswith(".docx") or content[:4] == b"PK\x03\x04":
            try:
                from docx import Document as DocxDocument
                from reportlab.lib.pagesizes import letter
                from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
                from reportlab.lib.units import inch
                from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

                doc = DocxDocument(io.BytesIO(content))
                pdf_buffer = io.BytesIO()
                styles = getSampleStyleSheet()
                body_style = ParagraphStyle(
                    "DocBody", parent=styles["Normal"], fontSize=12, leading=16, spaceAfter=6
                )
                heading_style = ParagraphStyle(
                    "DocHeading",
                    parent=styles["Heading2"],
                    fontSize=14,
                    leading=18,
                    spaceBefore=12,
                    spaceAfter=6,
                )
                pdf_doc = SimpleDocTemplate(
                    pdf_buffer,
                    pagesize=letter,
                    leftMargin=1 * inch,
                    rightMargin=1 * inch,
                    topMargin=1 * inch,
                    bottomMargin=1 * inch,
                )
                flowables = []
                for para in doc.paragraphs:
                    text = para.text.strip()
                    if not text:
                        flowables.append(Spacer(1, 6))
                        continue
                    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    style_name = (para.style.name or "").lower()
                    flowables.append(
                        Paragraph(
                            safe,
                            heading_style
                            if ("heading" in style_name or "title" in style_name)
                            else body_style,
                        )
                    )
                if not flowables:
                    flowables.append(Paragraph("(empty document)", body_style))
                pdf_doc.build(flowables)
                pdf_buffer.seek(0)
                return StreamingResponse(
                    pdf_buffer,
                    media_type="application/pdf",
                    headers={"Content-Disposition": "inline; filename=document.pdf"},
                )
            except ImportError as ie:
                logger.warning(f"DOCX-to-PDF conversion unavailable: {ie}")
                raise HTTPException(
                    status_code=501,
                    detail="DOCX-to-PDF conversion requires reportlab.",
                )

        # TXT / RTF / Markdown / other text — render as a simple PDF.
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import inch
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

            from app.services.text_extraction import text_extraction_service

            text = text_extraction_service.extract(file_content=content, filename=filename).text
            pdf_buffer = io.BytesIO()
            styles = getSampleStyleSheet()
            body_style = styles["Normal"]
            body_style.fontSize = 12
            body_style.leading = 16
            pdf_doc = SimpleDocTemplate(
                pdf_buffer,
                pagesize=letter,
                leftMargin=1 * inch,
                rightMargin=1 * inch,
                topMargin=1 * inch,
                bottomMargin=1 * inch,
            )
            flowables = []
            for line in text.split("\n"):
                if not line.strip():
                    flowables.append(Spacer(1, 6))
                else:
                    safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    flowables.append(Paragraph(safe, body_style))
            if not flowables:
                flowables.append(Paragraph("(empty document)", body_style))
            pdf_doc.build(flowables)
            pdf_buffer.seek(0)
            return StreamingResponse(
                pdf_buffer,
                media_type="application/pdf",
                headers={"Content-Disposition": "inline; filename=document.pdf"},
            )
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="Text-to-PDF conversion requires reportlab.",
            )

    except HTTPException:
        raise
    except (ValueError, OSError, UnicodeDecodeError) as e:
        logger.error(f"Failed to convert to PDF: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Failed to convert file to PDF.")
