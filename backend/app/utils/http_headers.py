"""HTTP header helpers."""

from urllib.parse import quote


def content_disposition(disposition: str, filename: str) -> str:
    """Build a Content-Disposition value that is safe for any filename.

    Starlette encodes headers as latin-1, so a raw filename containing an en
    dash, curly quotes or CJK characters raises UnicodeEncodeError (a 500).
    Emit an ASCII ``filename=`` fallback plus the RFC 5987 ``filename*=``
    form carrying the real UTF-8 name; browsers prefer the latter.
    """
    cleaned = "".join(ch for ch in (filename or "") if ch >= " " and ch != "\x7f") or "download"
    fallback = "".join(ch if ch.isascii() and ch not in '"\\;' else "_" for ch in cleaned)
    encoded = quote(cleaned, safe="")
    return f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"
