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
from app.services.courtlistener_client import CourtListenerClientBase

from ._cache import CacheMixin
from ._courtlistener import CourtListenerMixin
from ._metrics import MetricsMixin
from ._models import JudgeCacheDB
from ._queries import QueriesMixin
from ._wikipedia import WikipediaMixin


class JudgeIntelService(
    CourtListenerClientBase,
    CacheMixin,
    CourtListenerMixin,
    WikipediaMixin,
    MetricsMixin,
    QueriesMixin,
):
    """
    Complete judge intelligence system.
    Pulls ALL available data and stores in main database for unlimited querying.
    """

    def __init__(self):
        self.set_token(getattr(settings, "courtlistener_api_token", None))


# Singleton instance
judge_intel = JudgeIntelService()

__all__ = ["JudgeIntelService", "JudgeCacheDB", "judge_intel"]
