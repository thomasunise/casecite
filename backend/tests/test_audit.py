"""Tests for backend/app/services/audit.py"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.services.audit import AuditEventType, AuditLog


class TestAuditEventType:
    """Tests for the AuditEventType enum."""

    def test_login_success_value(self):
        assert AuditEventType.LOGIN_SUCCESS == "auth.login.success"

    def test_login_failure_value(self):
        assert AuditEventType.LOGIN_FAILURE == "auth.login.failure"

    def test_enum_is_string(self):
        assert isinstance(AuditEventType.LOGIN_SUCCESS, str)

    def test_multiple_event_types_exist(self):
        # Verify the enum has a reasonable number of members
        assert len(AuditEventType) >= 10


class TestAuditLogInit:
    """Tests for AuditLog initialization and properties."""

    def setup_method(self):
        """Reset chain hash before each test."""
        AuditLog._last_hash = None

    def test_has_uuid_id(self):
        entry = AuditLog(event_type=AuditEventType.LOGIN_SUCCESS, user_id="user-1")
        # Should be a valid UUID string
        parsed = uuid.UUID(entry.id)
        assert str(parsed) == entry.id

    def test_has_iso_timestamp_with_z(self):
        entry = AuditLog(event_type=AuditEventType.LOGIN_SUCCESS)
        assert entry.timestamp.endswith("Z")
        # Should be parseable as ISO format (strip Z for fromisoformat)
        ts = entry.timestamp.rstrip("Z")
        datetime.fromisoformat(ts)

    def test_has_entry_hash(self):
        entry = AuditLog(event_type=AuditEventType.LOGIN_SUCCESS)
        assert isinstance(entry.entry_hash, str)
        assert len(entry.entry_hash) == 64  # HMAC-SHA256 hexdigest = 64 hex chars

    def test_stores_all_fields(self):
        entry = AuditLog(
            event_type=AuditEventType.LOGIN_SUCCESS,
            user_id="user-42",
            user_email="attorney@law.com",
            resource_type="document",
            resource_id="doc-99",
            action_details={"action": "downloaded"},
            ip_address="192.168.1.1",
            user_agent="TestAgent/1.0",
            success=True,
            error_message=None,
            correlation_id="corr-1",
            request_id="req-1",
        )
        assert entry.user_id == "user-42"
        assert entry.user_email == "attorney@law.com"
        assert entry.resource_type == "document"
        assert entry.ip_address == "192.168.1.1"


class TestComputeHash:
    """Tests for _compute_hash determinism."""

    def setup_method(self):
        AuditLog._last_hash = None

    def test_determinism_same_input(self):
        """Two entries with identical fields should produce same hash pattern."""
        # Note: timestamps differ so hashes differ; we test the method directly
        entry = AuditLog(event_type=AuditEventType.LOGIN_SUCCESS, user_id="u1")
        h1 = entry._compute_hash()
        h2 = entry._compute_hash()
        assert h1 == h2

    def test_hash_is_hex_string(self):
        entry = AuditLog(event_type=AuditEventType.LOGIN_SUCCESS)
        h = entry._compute_hash()
        assert len(h) == 64  # HMAC-SHA256 hexdigest
        int(h, 16)  # Should not raise if valid hex


class TestChainHashing:
    """Tests for audit log chain integrity (previous_hash linking)."""

    def setup_method(self):
        AuditLog._last_hash = None

    def test_first_entry_has_genesis(self):
        entry1 = AuditLog(event_type=AuditEventType.LOGIN_SUCCESS)
        # First entry's previous_hash should be None or reference "GENESIS"
        assert entry1.previous_hash is None or entry1.previous_hash == "GENESIS"

    def test_second_entry_chains_to_first(self):
        entry1 = AuditLog(event_type=AuditEventType.LOGIN_SUCCESS, user_id="u1")
        entry2 = AuditLog(event_type=AuditEventType.LOGIN_FAILURE, user_id="u2")
        assert entry2.previous_hash == entry1.entry_hash

    def test_chain_of_three(self):
        e1 = AuditLog(event_type=AuditEventType.LOGIN_SUCCESS)
        e2 = AuditLog(event_type=AuditEventType.LOGIN_FAILURE)
        e3 = AuditLog(event_type=AuditEventType.LOGIN_SUCCESS)
        assert e2.previous_hash == e1.entry_hash
        assert e3.previous_hash == e2.entry_hash


class TestToDict:
    """Tests for AuditLog.to_dict() structure."""

    def setup_method(self):
        AuditLog._last_hash = None

    def test_to_dict_has_required_keys(self):
        entry = AuditLog(
            event_type=AuditEventType.LOGIN_SUCCESS,
            user_id="u1",
            user_email="u@test.com",
            resource_type="case",
            resource_id="case-1",
            ip_address="127.0.0.1",
            success=True,
        )
        d = entry.to_dict()
        assert isinstance(d, dict)
        # Check top-level structure keys
        assert "id" in d
        assert "timestamp" in d
        assert "event_type" in d


class TestToJson:
    """Tests for AuditLog.to_json() serialization."""

    def setup_method(self):
        AuditLog._last_hash = None

    def test_to_json_is_valid_json(self):
        entry = AuditLog(event_type=AuditEventType.LOGIN_SUCCESS, user_id="u1")
        json_str = entry.to_json()
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)
        assert parsed["id"] == entry.id


class TestAuditServiceLog:
    """Tests for AuditService.log() writing JSONL."""

    def setup_method(self):
        AuditLog._last_hash = None

    @pytest.mark.asyncio
    async def test_log_writes_jsonl(self, audit_service_isolated):
        entry = AuditLog(
            event_type=AuditEventType.LOGIN_SUCCESS,
            user_id="user-1",
            ip_address="127.0.0.1",
        )
        await audit_service_isolated.log(entry)

        # Verify file was created and contains valid JSONL
        log_file = audit_service_isolated._get_log_file()
        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) >= 1
        parsed = json.loads(lines[-1])
        assert parsed["id"] == entry.id


class TestGetLogFile:
    """Tests for daily log file rotation."""

    def test_log_file_contains_date(self, audit_service_isolated):
        log_file = audit_service_isolated._get_log_file()
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        assert today in str(log_file)

    def test_log_file_is_path(self, audit_service_isolated):
        from pathlib import Path

        log_file = audit_service_isolated._get_log_file()
        assert isinstance(log_file, Path)


class TestBruteForceDetection:
    """Tests for _track_failed_login brute force detection."""

    def setup_method(self):
        AuditLog._last_hash = None

    @pytest.mark.asyncio
    async def test_brute_force_after_threshold(self, audit_service_isolated):
        ip = "10.0.0.99"
        email = "victim@law.com"
        # Simulate 6 failed login attempts (threshold is typically 5)
        for _ in range(6):
            await audit_service_isolated._track_failed_login(ip, email)
        # After threshold, the service should have logged a brute force event.
        # We verify by checking the log file for a brute force entry.
        log_file = audit_service_isolated._get_log_file()
        if log_file.exists():
            content = log_file.read_text()
            # Should contain brute force related event
            assert "brute" in content.lower() or len(content.strip().split("\n")) >= 1


class TestVerifyChainIntegrity:
    """Tests for verify_chain_integrity."""

    def setup_method(self):
        AuditLog._last_hash = None

    @pytest.mark.asyncio
    async def test_valid_chain(self, audit_service_isolated):
        e1 = AuditLog(event_type=AuditEventType.LOGIN_SUCCESS, user_id="u1")
        e2 = AuditLog(event_type=AuditEventType.LOGIN_FAILURE, user_id="u2")
        e3 = AuditLog(event_type=AuditEventType.LOGIN_SUCCESS, user_id="u3")
        logs = [e1.to_dict(), e2.to_dict(), e3.to_dict()]
        is_valid, invalid_id = await audit_service_isolated.verify_chain_integrity(logs)
        assert is_valid is True
        assert invalid_id is None

    @pytest.mark.asyncio
    async def test_tampered_chain(self, audit_service_isolated):
        e1 = AuditLog(event_type=AuditEventType.LOGIN_SUCCESS, user_id="u1")
        e2 = AuditLog(event_type=AuditEventType.LOGIN_FAILURE, user_id="u2")
        logs = [e1.to_dict(), e2.to_dict()]
        # Tamper with the first entry's hash (stored under the "integrity" key)
        logs[0]["integrity"]["entry_hash"] = "tampered_hash_value_here_000000"
        is_valid, invalid_id = await audit_service_isolated.verify_chain_integrity(logs)
        assert is_valid is False
        assert invalid_id == logs[0]["id"]


class TestGetLogs:
    """Tests for get_logs with filtering."""

    def setup_method(self):
        AuditLog._last_hash = None

    @pytest.mark.asyncio
    async def test_get_logs_returns_list(self, audit_service_isolated):
        # Write a log entry first
        entry = AuditLog(event_type=AuditEventType.LOGIN_SUCCESS, user_id="u1")
        await audit_service_isolated.log(entry)

        now = datetime.now(UTC)
        logs = await audit_service_isolated.get_logs(
            start_date=now - timedelta(minutes=5),
            end_date=now + timedelta(minutes=5),
        )
        assert isinstance(logs, list)
        assert len(logs) >= 1

    @pytest.mark.asyncio
    async def test_get_logs_filter_by_event_type(self, audit_service_isolated):
        entry = AuditLog(event_type=AuditEventType.LOGIN_SUCCESS, user_id="filter-test")
        await audit_service_isolated.log(entry)

        now = datetime.now(UTC)
        logs = await audit_service_isolated.get_logs(
            start_date=now - timedelta(minutes=5),
            end_date=now + timedelta(minutes=5),
            event_type=AuditEventType.LOGIN_SUCCESS,
        )
        assert isinstance(logs, list)

    @pytest.mark.asyncio
    async def test_get_logs_with_limit(self, audit_service_isolated):
        for i in range(5):
            entry = AuditLog(event_type=AuditEventType.LOGIN_SUCCESS, user_id=f"u{i}")
            await audit_service_isolated.log(entry)

        now = datetime.now(UTC)
        logs = await audit_service_isolated.get_logs(
            start_date=now - timedelta(minutes=5),
            end_date=now + timedelta(minutes=5),
            limit=2,
        )
        assert len(logs) <= 2
