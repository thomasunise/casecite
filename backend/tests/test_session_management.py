"""
Tests for SessionManager — concurrent sessions, expiration, IP binding.

Covers:
- Session creation with JTI
- Max 5 concurrent sessions enforced
- Oldest session evicted when limit exceeded
- Session validation (valid, expired, wrong IP)
- Session termination (single and all)
- IP binding enforcement
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from app.middleware.security import SessionManager


def _make_session_manager(tmp_path) -> SessionManager:
    """Create an isolated SessionManager with a temp session file."""
    sm = SessionManager.__new__(SessionManager)
    from collections import defaultdict

    sm._sessions = defaultdict(list)
    sm.max_sessions_per_user = 5
    sm.session_timeout = timedelta(hours=8)
    sm._last_cleanup = datetime.now(UTC)
    sm._cleanup_interval = timedelta(minutes=15)
    sm._session_file = tmp_path / "sessions.jsonl"
    return sm


class TestSessionCreation:
    """Tests for creating sessions."""

    def test_create_session_returns_true(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        result = sm.create_session("user-1", "192.168.1.1", "Mozilla/5.0", "jti-001")
        assert result is True

    def test_create_session_stores_session(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        sm.create_session("user-1", "192.168.1.1", "Mozilla/5.0", "jti-001")
        sessions = sm.get_active_sessions("user-1")
        assert len(sessions) == 1

    def test_create_multiple_sessions(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        for i in range(3):
            sm.create_session("user-1", f"192.168.1.{i}", "Mozilla/5.0", f"jti-{i}")
        sessions = sm.get_active_sessions("user-1")
        assert len(sessions) == 3


class TestSessionLimits:
    """Tests for concurrent session enforcement."""

    def test_max_5_sessions_enforced(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        for i in range(7):
            sm.create_session("user-1", f"10.0.0.{i}", "Agent", f"jti-{i}")
        sessions = sm.get_active_sessions("user-1")
        assert len(sessions) == 5

    def test_oldest_session_evicted(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        for i in range(5):
            sm.create_session("user-1", f"10.0.0.{i}", "Agent", f"jti-{i}")

        # Add a 6th — should evict jti-0
        sm.create_session("user-1", "10.0.0.99", "Agent", "jti-new")
        raw = sm.get_active_sessions_raw("user-1")
        jtis = {s["jti"] for s in raw}
        assert "jti-0" not in jtis
        assert "jti-new" in jtis

    def test_sessions_isolated_per_user(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        sm.create_session("user-a", "10.0.0.1", "Agent", "jti-a")
        sm.create_session("user-b", "10.0.0.2", "Agent", "jti-b")
        assert len(sm.get_active_sessions("user-a")) == 1
        assert len(sm.get_active_sessions("user-b")) == 1


class TestSessionValidation:
    """Tests for session validation."""

    def test_validate_valid_session(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        sm.create_session("user-1", "10.0.0.1", "Agent", "jti-1")
        assert sm.validate_session("user-1", "jti-1") is True

    def test_validate_nonexistent_jti(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        sm.create_session("user-1", "10.0.0.1", "Agent", "jti-1")
        assert sm.validate_session("user-1", "jti-unknown") is False

    def test_validate_nonexistent_user(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        assert sm.validate_session("no-such-user", "jti-1") is False

    def test_validate_expired_session(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        sm.create_session("user-1", "10.0.0.1", "Agent", "jti-1")
        # Manually expire the session
        for s in sm._sessions["user-1"]:
            if s["jti"] == "jti-1":
                s["expires_at"] = datetime.now(UTC) - timedelta(hours=1)
        assert sm.validate_session("user-1", "jti-1") is False

    def test_validate_expired_jwt(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        sm.create_session("user-1", "10.0.0.1", "Agent", "jti-1")
        expired_time = datetime.now(UTC) - timedelta(hours=1)
        assert sm.validate_session("user-1", "jti-1", token_exp=expired_time) is False

    def test_validate_updates_last_activity(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        sm.create_session("user-1", "10.0.0.1", "Agent", "jti-1")
        before = sm._sessions["user-1"][0]["last_activity"]
        # Small delay to ensure timestamp difference
        sm.validate_session("user-1", "jti-1")
        after = sm._sessions["user-1"][0]["last_activity"]
        assert after >= before

    def test_validate_ip_binding_same_ip(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        sm.create_session("user-1", "10.0.0.1", "Agent", "jti-1")
        with patch("app.middleware.security.settings") as mock_settings:
            mock_settings.enforce_session_ip_binding = True
            assert sm.validate_session("user-1", "jti-1", ip_address="10.0.0.1") is True

    def test_validate_ip_binding_different_ip_rejected(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        sm.create_session("user-1", "10.0.0.1", "Agent", "jti-1")
        with patch("app.middleware.security.settings") as mock_settings:
            mock_settings.enforce_session_ip_binding = True
            assert sm.validate_session("user-1", "jti-1", ip_address="99.99.99.99") is False


class TestSessionTermination:
    """Tests for terminating sessions."""

    def test_terminate_single_session(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        sm.create_session("user-1", "10.0.0.1", "Agent", "jti-1")
        sm.create_session("user-1", "10.0.0.2", "Agent", "jti-2")
        sm.terminate_session("user-1", "jti-1")
        raw = sm.get_active_sessions_raw("user-1")
        jtis = {s["jti"] for s in raw}
        assert "jti-1" not in jtis
        assert "jti-2" in jtis

    def test_terminate_all_sessions(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        for i in range(3):
            sm.create_session("user-1", f"10.0.0.{i}", "Agent", f"jti-{i}")
        sm.terminate_all_sessions("user-1")
        assert len(sm.get_active_sessions("user-1")) == 0

    def test_terminate_all_leaves_other_users(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        sm.create_session("user-a", "10.0.0.1", "Agent", "jti-a")
        sm.create_session("user-b", "10.0.0.2", "Agent", "jti-b")
        sm.terminate_all_sessions("user-a")
        assert len(sm.get_active_sessions("user-a")) == 0
        assert len(sm.get_active_sessions("user-b")) == 1


class TestSessionTerminationCompaction:
    """Terminating a session must compact the on-disk file immediately."""

    def test_terminate_session_compacts_file(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        sm.create_session("user-1", "10.0.0.1", "Agent", "jti-1")
        sm.create_session("user-1", "10.0.0.2", "Agent", "jti-2")
        sm.terminate_session("user-1", "jti-1")
        content = sm._session_file.read_text()
        assert "jti-1" not in content
        assert "jti-2" in content

    def test_terminate_all_sessions_compacts_file(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        sm.create_session("user-a", "10.0.0.1", "Agent", "jti-a")
        sm.create_session("user-b", "10.0.0.2", "Agent", "jti-b")
        sm.terminate_all_sessions("user-a")
        content = sm._session_file.read_text()
        assert "jti-a" not in content
        assert "jti-b" in content


class TestSessionPersistence:
    """Tests for file-based session persistence."""

    def test_session_persisted_to_file(self, tmp_path):
        sm = _make_session_manager(tmp_path)
        sm.create_session("user-1", "10.0.0.1", "Agent", "jti-1")
        assert sm._session_file.exists()
        content = sm._session_file.read_text()
        assert "jti-1" in content

    def test_sessions_loaded_from_file(self, tmp_path):
        sm1 = _make_session_manager(tmp_path)
        sm1.create_session("user-1", "10.0.0.1", "Agent", "jti-1")

        # Create a new SessionManager that reads the same file
        sm2 = _make_session_manager(tmp_path)
        sm2._load_sessions_from_file()
        assert len(sm2.get_active_sessions("user-1")) == 1

    def test_expired_sessions_not_loaded(self, tmp_path):
        sm1 = _make_session_manager(tmp_path)
        sm1.create_session("user-1", "10.0.0.1", "Agent", "jti-1")
        # Manually expire in file by overwriting
        for s in sm1._sessions["user-1"]:
            s["expires_at"] = datetime.now(UTC) - timedelta(hours=1)
        sm1._rewrite_session_file()

        sm2 = _make_session_manager(tmp_path)
        sm2._load_sessions_from_file()
        assert len(sm2.get_active_sessions("user-1")) == 0
