"""
Judge Intelligence Service

Comprehensive judge research system that pulls and stores ALL available data:
- Biographical information
- Education history
- Career/position history
- Every opinion they've ever written
- Full text for semantic search and analysis

Stores in the main PostgreSQL database via async SQLAlchemy as a JSON cache table.
"""

from app.config import settings

from ._cache import CacheMixin
from ._courtlistener import CourtListenerMixin
from ._metrics import MetricsMixin
from ._models import JudgeCacheDB
from ._queries import QueriesMixin
from ._wikipedia import WikipediaMixin


class JudgeIntelService(CacheMixin, CourtListenerMixin, WikipediaMixin, MetricsMixin, QueriesMixin):
    """
    Complete judge intelligence system.
    Pulls ALL available data and stores in main database for unlimited querying.
    """

    BASE_URL = "https://www.courtlistener.com/api/rest/v4"

    def __init__(self):
        token = getattr(settings, "courtlistener_api_token", None)
        self.api_token = token if token and token.strip() else None
        self.headers = {"Accept": "application/json"}
        if self.api_token:
            self.headers["Authorization"] = f"Token {self.api_token}"

    def set_token(self, token: str | None) -> None:
        """Update the active CourtListener token at runtime (see integrations router)."""
        self.api_token = token if token and token.strip() else None
        self.headers = {"Accept": "application/json"}
        if self.api_token:
            self.headers["Authorization"] = f"Token {self.api_token}"


# Singleton instance
judge_intel = JudgeIntelService()

__all__ = ["JudgeIntelService", "JudgeCacheDB", "judge_intel"]
