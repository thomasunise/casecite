"""
Reindex Service

Orchestrates document reindexing.
Extracted from the settings router so routers handle HTTP concerns only.
"""

import logging

from app.models.schemas import DocumentStatus
from app.services.embeddings import embedding_service

logger = logging.getLogger(__name__)


async def reindex_user_documents(user_id: str) -> dict:
    """
    Re-embed and re-index every document for *user_id*.

    Each document goes through ``document_service.reindex_document`` — the one
    re-index path, which keeps the document's matter, folder and metadata and
    marks it FAILED (never "indexed" with nothing behind it) when re-embedding
    fails.

    Returns a summary dict with counts of reindexed docs and any errors.
    """
    from app.services.documents import document_service
    from app.services.user_keys import UserAPIKeys

    reindexed = 0
    errors: list[str] = []

    # Re-embedding must use the user's stored BYOK keys — with only the server
    # key, reindex fails on BYOK-only instances.
    user_keys = UserAPIKeys.for_user(user_id)

    user_docs = document_service._get_user_documents(user_id)
    for doc_id, doc in list(user_docs.items()):
        try:
            result = await document_service.reindex_document(doc_id, user_id, user_keys)
        except FileNotFoundError:
            errors.append(f"{doc.filename}: file not found")
            continue
        except Exception as e:  # provider SDK / store errors share no base class
            # Raised before the existing vectors were touched (unreadable file,
            # no text, store unavailable): the document keeps its index.
            logger.warning(f"Reindex of {doc_id} failed: {type(e).__name__}: {e}")
            errors.append(f"{doc.filename}: {e}")
            continue

        if result is None:
            errors.append(f"{doc.filename}: document not found")
        elif result.status == DocumentStatus.INDEXED:
            reindexed += 1
        else:
            reason = (result.metadata or {}).get("error") or "re-indexing failed"
            errors.append(f"{doc.filename}: {reason}")

    document_service._save_index()

    return {
        "status": "completed",
        "reindexed": reindexed,
        "errors": errors,
        "embedding_model": embedding_service.model,
        "message": f"Reindexed {reindexed} documents with {embedding_service.model}",
    }
