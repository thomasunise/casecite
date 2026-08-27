"""RAG Service package - re-exports for backwards compatibility.

All existing imports like `from app.services.rag import rag_service` continue to work.
"""

import logging

from app.services.rag.service import RAGService

logger = logging.getLogger(__name__)

try:
    rag_service = RAGService()
except (ValueError, KeyError, ConnectionError, TimeoutError, OSError, RuntimeError) as e:
    logger.error(f"RAGService initialization failed: {e}")
    rag_service = None

__all__ = ["RAGService", "rag_service"]
