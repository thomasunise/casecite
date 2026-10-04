"""
Legal Tools - Oral argument search methods.
"""

from typing import Any

from app.services.courtlistener_gate import cl_client

from ._helpers import strip_marks, url_from_relative

_STORAGE = "https://storage.courtlistener.com/"


class OralArgumentsMixin:
    """Mixin providing oral argument search functionality."""

    async def search_oral_arguments(
        self, query: str, court: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """
        Search oral argument recordings.
        """
        self._check_token()
        params = {
            "q": query,
            "type": "oa",  # oral arguments
            "page_size": min(limit, 100),
            "highlight": "on",
        }

        if court:
            params["court"] = court

        async with cl_client(timeout=180.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/search/", params=params, headers=self.headers
            )
            response.raise_for_status()
            data = response.json()

        arguments = []
        for result in data.get("results", []):
            # Prefer CourtListener's own MP3 copy: it is served over https, so
            # the in-app player works on an https site. Courts' original
            # download_url is often plain http (blocked as mixed content).
            local = result.get("local_path_mp3") or result.get("local_path")
            download_url = result.get("download_url") or None
            if local:
                audio_url = local if local.startswith("http") else _STORAGE + local.lstrip("/")
            elif download_url and download_url.startswith("https://"):
                audio_url = download_url
            else:
                audio_url = None

            duration = result.get("duration")
            arguments.append(
                {
                    "id": result.get("id"),
                    "case_name": strip_marks(result.get("caseName")) or "Unknown",
                    "case_name_full": strip_marks(result.get("case_name_full")) or None,
                    "court": result.get("court", ""),
                    "court_id": result.get("court_id"),
                    "date_argued": result.get("dateArgued"),
                    "docket_number": strip_marks(result.get("docketNumber")) or None,
                    "judges": strip_marks(result.get("judge")) or None,
                    "duration": duration,
                    "duration_label": _fmt_duration(duration),
                    "audio_url": audio_url,
                    "download_url": download_url,
                    "snippet": strip_marks(result.get("snippet")) or None,
                    "url": url_from_relative(result.get("absolute_url"))
                    or "https://www.courtlistener.com",
                    "docket_id": result.get("docket_id"),
                }
            )

        return arguments


def _fmt_duration(seconds: Any) -> str | None:
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return None
    if total <= 0:
        return None
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
