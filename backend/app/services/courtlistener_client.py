"""Shared CourtListener client plumbing.

Three services talk to CourtListener — ``courtlistener_service`` (opinions and
the citation check), ``legal_tools`` (case lookup, precedents, dockets, oral
arguments, trends) and ``judge_intel`` (judge profiles). Each keeps its own
instance, but the base URL, auth headers, token handling, date parsing and
jurisdiction-to-court mapping live here so they cannot drift apart.

Requests themselves go through ``courtlistener_gate.cl_client``.
"""

from datetime import date, datetime

BASE_URL = "https://www.courtlistener.com/api/rest/v4"

TOKEN_REQUIRED_MESSAGE = (
    "CourtListener API token required. "
    "Get a FREE token at https://www.courtlistener.com/help/api/rest/#permissions "
    "(1) Create account at courtlistener.com, "
    "(2) Go to Profile > API section, "
    "(3) Create token and add COURTLISTENER_API_TOKEN=your_token to .env file, "
    "(4) Restart the backend server."
)

_FEDERAL_APPELLATE = [
    "scotus",
    "ca1",
    "ca2",
    "ca3",
    "ca4",
    "ca5",
    "ca6",
    "ca7",
    "ca8",
    "ca9",
    "ca10",
    "ca11",
    "cadc",
    "cafc",
]

# Jurisdiction name → CourtListener court ids. State entries list that state's
# own courts; federal district courts sitting in a state are not included.
JURISDICTION_COURTS: dict[str, list[str]] = {
    "federal": _FEDERAL_APPELLATE,
    "scotus": ["scotus"],
    "supreme_court": ["scotus"],
    "ninth_circuit": ["ca9"],
    "ca9": ["ca9"],
    "second_circuit": ["ca2"],
    "ca2": ["ca2"],
    "dc_circuit": ["cadc"],
    "cadc": ["cadc"],
    "federal_circuit": ["cafc"],
    "california": ["cal", "calctapp"],
    "new_york": ["ny", "nyappdiv", "nysupct"],
    "texas": ["tex", "texapp", "texcrimapp"],
    "florida": ["fla", "flaapp"],
    "immigration": ["bia"],  # Board of Immigration Appeals
}


def courts_for_jurisdiction(jurisdiction: str) -> list[str]:
    """Map a jurisdiction name to CourtListener court ids ([] when unknown)."""
    return list(JURISDICTION_COURTS.get(jurisdiction.lower(), []))


def parse_date(date_str: str | None) -> date | None:
    """Parse a CourtListener date or datetime string."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        try:
            return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError, AttributeError):
            return None


def auth_headers(token: str | None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Token {token}"
    return headers


class CourtListenerClientBase:
    """Token state and helpers shared by every CourtListener-backed service."""

    BASE_URL = BASE_URL

    api_token: str | None
    headers: dict[str, str]

    def set_token(self, token: str | None) -> None:
        """Update the active CourtListener token at runtime.

        Called at startup and by the admin integrations endpoint so the
        instance-wide token (DB) overrides the .env fallback without a restart.
        Passing a falsy token reverts to anonymous (lower rate limit).
        """
        self.api_token = token if token and token.strip() else None
        self.headers = auth_headers(self.api_token)

    def _check_token(self):
        """Raise error if no API token configured."""
        if not self.api_token:
            raise ValueError(TOKEN_REQUIRED_MESSAGE)

    def _parse_date(self, date_str: str | None) -> date | None:
        """Parse date string from API."""
        return parse_date(date_str)

    def _get_courts_for_jurisdiction(self, jurisdiction: str) -> list[str]:
        """Map jurisdiction to CourtListener court IDs."""
        return courts_for_jurisdiction(jurisdiction)
