"""
Reindex Service

Orchestrates document reindexing.
Extracted from the settings router so routers handle HTTP concerns only.
"""

import logging
import os

from app.config import settings
from app.models.schemas import DocumentStatus
from app.services.embeddings import embedding_service

logger = logging.getLogger(__name__)


async def reindex_user_documents(user_id: str) -> dict:
    """
    Re-embed and re-index every document for *user_id*.

    Returns a summary dict with counts of reindexed docs and any errors.
    """
    from app.services.documents import document_service
    from app.services.rag import rag_service
    from app.services.user_keys import UserAPIKeys

    reindexed = 0
    errors: list[str] = []

    # Re-embedding must use the user's stored BYOK keys — with only the server
    # key, reindex fails on BYOK-only instances.
    user_keys = UserAPIKeys.for_user(user_id)

    user_docs = document_service._get_user_documents(user_id)
    for doc_id, doc in list(user_docs.items()):
        try:
            file_ext = os.path.splitext(doc.filename)[1]
            user_file_path = os.path.join(
                document_service._get_user_upload_dir(user_id), f"{doc_id}{file_ext}"
            )
            legacy_file_path = os.path.join(settings.upload_dir, f"{doc_id}{file_ext}")

            file_path = user_file_path if os.path.exists(user_file_path) else legacy_file_path
            if not os.path.exists(file_path):
                errors.append(f"{doc.filename}: file not found")
                continue

            text = await document_service.extract_text(file_path, doc.content_type)
            if not text.strip():
                errors.append(f"{doc.filename}: no text extracted")
                continue

            await rag_service.delete_document(doc_id)

            doc_type = document_service._classify_document(doc.filename, text)
            chunk_count = await rag_service.index_document(
                document_id=doc_id,
                text=text,
                filename=doc.filename,
                source=doc.source.value,
                doc_type=doc_type,
                user_keys=user_keys,
                user_id=user_id,
            )

            doc.chunk_count = chunk_count
            doc.status = DocumentStatus.INDEXED
            doc.metadata.pop("error", None)
            reindexed += 1

        except (ValueError, KeyError, ConnectionError, TimeoutError, OSError, RuntimeError) as e:
            errors.append(f"{doc.filename}: {str(e)}")

    document_service._save_index()

    return {
        "status": "completed",
        "reindexed": reindexed,
        "errors": errors,
        "embedding_model": embedding_service.model,
        "message": f"Reindexed {reindexed} documents with {embedding_service.model}",
    }
