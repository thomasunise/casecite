"""
Test configuration and fixtures for CaseCite RAG Platform.
"""

import datetime as _dt
import sys

# Shim datetime.UTC for Python < 3.11 (project targets 3.11, but test env may be 3.10)
if sys.version_info < (3, 11) and not hasattr(_dt, "UTC"):
    _dt.UTC = _dt.timezone.utc  # noqa: UP017

import os
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Set test environment before importing app
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"
# CSRF middleware is now ALWAYS registered; skipping validation requires the
# explicit debug+csrf_disabled pair (see app/middleware/csrf.py).
os.environ["CSRF_DISABLED"] = "true"


@pytest.fixture(scope="session")
def app():
    """Create FastAPI app instance for testing."""
    from app.main import app

    return app


@pytest.fixture
def client(app) -> Generator:
    """Create test client."""
    with TestClient(app) as client:
        yield client


def make_auth_headers(user) -> dict:
    """Mint an access token AND register its session.

    get_current_user enforces session validation (session_manager.validate_session
    by JTI), so a bare token 401s — every test token must have a matching session.
    TestClient requests arrive with client host "testclient".
    """
    from app.middleware.security import session_manager
    from app.services.auth import auth_service

    token = auth_service.create_access_token(user)
    token_data = auth_service.verify_token(token)
    session_manager.create_session(
        user_id=user.id,
        ip_address="testclient",
        user_agent="pytest",
        jti=token_data.jti,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers() -> dict:
    """Create authentication headers with a valid test token."""
    from datetime import datetime

    from app.services.auth import User, UserRole

    # Create a test user
    test_user = User(
        id="test-user-123",
        email="test@casecite.legal",
        name="Test User",
        roles=[UserRole.ATTORNEY, UserRole.ADMIN],
        last_login=datetime.now(_dt.UTC),
    )

    return make_auth_headers(test_user)


@pytest.fixture
def non_admin_headers() -> dict:
    """Create authentication headers for a non-admin user."""
    from datetime import datetime

    from app.services.auth import User, UserRole

    test_user = User(
        id="test-viewer-456",
        email="viewer@casecite.legal",
        name="Test Viewer",
        roles=[UserRole.VIEWER],
        last_login=datetime.now(_dt.UTC),
    )

    return make_auth_headers(test_user)


@pytest.fixture
def mock_openai():
    """Mock OpenAI client for testing."""
    with patch("openai.OpenAI") as mock:
        mock_client = MagicMock()
        mock.return_value = mock_client

        # Mock chat completion
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response from AI"
        mock_client.chat.completions.create.return_value = mock_response

        # Mock embeddings
        mock_embedding_response = MagicMock()
        mock_embedding_response.data = [MagicMock()]
        mock_embedding_response.data[0].embedding = [0.1] * 1536  # OpenAI embedding dimension
        mock_client.embeddings.create.return_value = mock_embedding_response

        yield mock_client


@pytest.fixture
def mock_vector_db():
    """Mock vector database for testing."""
    with patch("app.services.vectordb.get_vector_db") as mock:
        mock_db = MagicMock()
        mock_db.get_stats.return_value = {
            "total_chunks": 100,
            "stored_embedding_dimensions": 1536,
        }
        mock_db.search.return_value = []
        mock.return_value = mock_db
        yield mock_db


@pytest.fixture
def sample_document():
    """Create a sample document for testing."""
    from datetime import datetime

    return {
        "id": "doc-123",
        "filename": "test_contract.pdf",
        "content_type": "application/pdf",
        "size": 1024,
        "source": "local",
        "status": "indexed",
        "chunk_count": 5,
        "folder_path": "/Clients/Smith/",
        "created_at": datetime.now(_dt.UTC).isoformat(),
    }


@pytest.fixture
def sample_chunks():
    """Create sample document chunks for testing."""
    return [
        {
            "text": "This Agreement is entered into as of January 1, 2024.",
            "chunk_index": 0,
            "token_count": 12,
            "metadata": {"document_id": "doc-123", "source": "test_contract.pdf"},
        },
        {
            "text": "The parties agree to the following terms and conditions.",
            "chunk_index": 1,
            "token_count": 10,
            "metadata": {"document_id": "doc-123", "source": "test_contract.pdf"},
        },
    ]


@pytest.fixture
def sample_case_law():
    """Create sample case law results for testing."""
    return [
        {
            "id": 12345,
            "case_name": "Smith v. Jones",
            "citation": ["123 F.3d 456 (9th Cir. 2023)"],
            "court": "ca9",
            "date_filed": "2023-06-15",
            "snippet": "The court held that the plaintiff must demonstrate...",
            "url": "https://www.courtlistener.com/opinion/12345/smith-v-jones/",
        }
    ]


@pytest.fixture(scope="session")
def test_data_dir(tmp_path_factory):
    """Create a temporary data directory for tests."""
    return tmp_path_factory.mktemp("test_data")


@pytest.fixture
def mock_courtlistener():
    """Mock CourtListener API for testing."""
    with patch("httpx.AsyncClient") as mock:
        mock_client = MagicMock()
        mock.return_value.__aenter__.return_value = mock_client

        # Mock search response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "count": 1,
            "results": [{"id": 123, "case_name": "Test v. Case", "citation": ["123 F.3d 456"]}],
        }
        mock_client.get.return_value = mock_response

        yield mock_client


@pytest.fixture
def fingerprinting_service(tmp_path):
    """Create an isolated FingerprintingService with a temp SQLite database."""
    from app.services.fingerprinting import FingerprintingService

    service = FingerprintingService.__new__(FingerprintingService)
    service.db_path = tmp_path / "fingerprints.db"
    service.similarity_threshold = 0.85
    service.ip_velocity_limit = 3
    service.asn_velocity_limit = 10
    service.fingerprint_velocity_hours = 24
    service._init_db()
    return service


@pytest.fixture
def audit_service_isolated(tmp_path):
    """Create an isolated AuditService with a temp log directory."""
    from app.services.audit import AuditLog, AuditService

    # Reset the chain hash for isolation
    original_hash = AuditLog._last_hash
    AuditLog._last_hash = None

    service = AuditService.__new__(AuditService)
    service.log_dir = tmp_path / "audit_logs"
    service.log_dir.mkdir(parents=True, exist_ok=True)
    service._current_log_file = None
    service._current_date = None

    yield service

    # Restore original hash
    AuditLog._last_hash = original_hash


@pytest.fixture
def chroma_db(tmp_path):
    """Create an isolated ChromaDB instance with a temp directory."""
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    chroma_path = str(tmp_path / "chroma")
    os.makedirs(chroma_path, exist_ok=True)

    client = chromadb.PersistentClient(
        path=chroma_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(
        name="test_legal_documents",
        metadata={"hnsw:space": "cosine"},
    )

    # Create a minimal ChromaDB-like object
    class TestChromaDB:
        pass

    db = TestChromaDB()
    db.client = client
    db.collection = collection

    # Bind ChromaDB methods
    from app.services.vectordb import ChromaDB

    db.add_documents = ChromaDB.add_documents.__get__(db, TestChromaDB)
    db.search = ChromaDB.search.__get__(db, TestChromaDB)
    db.delete = ChromaDB.delete.__get__(db, TestChromaDB)
    db.delete_by_document = ChromaDB.delete_by_document.__get__(db, TestChromaDB)
    db.clear_all = ChromaDB.clear_all.__get__(db, TestChromaDB)
    db.get_stats = ChromaDB.get_stats.__get__(db, TestChromaDB)
    yield db
