"""
Audit chain integrity — the HMAC must cover the whole stored entry.

v1 signed seven scalar fields, so action details, IP, user agent and error
text could be edited on disk without breaking the chain. v2 signs the full
entry; legacy v1 entries keep verifying via their recorded hash_version, and
a rotated key stays verifiable through AUDIT_HMAC_KEY_PREVIOUS.
"""

import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from app.config import settings
from app.services.audit import (
    AuditEventType,
    AuditLog,
    compute_entry_hash,
    verify_entry_hash,
)


def _entries(n: int = 3) -> list[dict]:
    AuditLog._last_hash = None
    out = []
    for i in range(n):
        entry = AuditLog(
            event_type=AuditEventType.DOCUMENT_DELETE,
            user_id=f"user-{i}",
            user_email=f"person{i}@example.com",
            resource_type="document",
            resource_id=f"doc-{i}",
            action_details={"filename": f"contract-{i}.pdf", "size": 1024 * i},
            ip_address="10.20.30.40",
            user_agent="pytest/1.0",
            success=True,
        )
        # Round-trip through JSON exactly as the JSONL file would.
        out.append(json.loads(entry.to_json()))
    return out


class TestFullEntryCoverage:
    def setup_method(self):
        AuditLog._last_hash = None

    def test_new_entries_are_version_2(self):
        (entry,) = _entries(1)
        assert entry["integrity"]["hash_version"] == 2
        assert verify_entry_hash(entry)

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda e: e["action"].__setitem__("filename", "something-else.pdf"),
            lambda e: e["action"].__setitem__("size", 999),
            lambda e: e["context"].__setitem__("ip_address", "192.168.0.***"),
            lambda e: e["context"].__setitem__("user_agent", "curl/8.0"),
            lambda e: e["outcome"].__setitem__("error", "fabricated"),
            lambda e: e["user"].__setitem__("email", "x***@example.com"),
            lambda e: e.__setitem__("correlation_id", "00000000-0000-0000-0000-000000000000"),
        ],
        ids=["details", "details-number", "ip", "user_agent", "error", "email", "correlation"],
    )
    def test_editing_any_field_breaks_the_signature(self, mutate):
        (entry,) = _entries(1)
        assert verify_entry_hash(entry)
        mutate(entry)
        assert not verify_entry_hash(entry)

    @pytest.mark.asyncio
    async def test_chain_verification_flags_edited_details(self, audit_service_isolated):
        logs = _entries(3)
        logs[1]["action"]["filename"] = "renamed-after-the-fact.pdf"
        is_valid, invalid_id = await audit_service_isolated.verify_chain_integrity(logs)
        assert is_valid is False
        assert invalid_id == logs[1]["id"]

    @pytest.mark.asyncio
    async def test_untouched_chain_verifies_after_json_roundtrip(self, audit_service_isolated):
        logs = _entries(5)
        is_valid, invalid_id = await audit_service_isolated.verify_chain_integrity(logs)
        assert is_valid is True
        assert invalid_id is None


class TestLegacyEntries:
    def _legacy_entry(self, previous_hash: str | None) -> dict:
        entry = {
            "id": "legacy-1",
            "timestamp": "2026-01-01T00:00:00+00:00Z",
            "event_type": "login_success",
            "user": {"id": "u1", "email": "a***@example.com"},
            "resource": {"type": None, "id": None},
            "action": {"note": "original"},
            "context": {"ip_address": "10.0.0.***", "user_agent": "x", "environment": "production"},
            "outcome": {"success": True, "error": None},
            "integrity": {"previous_hash": previous_hash, "entry_hash": None},
        }
        message = (
            f"{previous_hash or 'GENESIS'}:legacy-1:{entry['timestamp']}:login_success:u1:None:True"
        )
        entry["integrity"]["entry_hash"] = hmac.new(
            AuditLog._hmac_key, message.encode(), hashlib.sha256
        ).hexdigest()
        return entry

    def test_v1_entry_without_version_still_verifies(self):
        entry = self._legacy_entry(None)
        assert "hash_version" not in entry["integrity"]
        assert verify_entry_hash(entry)
        assert compute_entry_hash(entry, AuditLog._hmac_key) == entry["integrity"]["entry_hash"]

    @pytest.mark.asyncio
    async def test_mixed_chain_v1_then_v2(self, audit_service_isolated):
        legacy = self._legacy_entry(None)
        AuditLog._last_hash = legacy["integrity"]["entry_hash"]
        new = json.loads(AuditLog(event_type=AuditEventType.LOGIN_SUCCESS, user_id="u2").to_json())
        is_valid, invalid_id = await audit_service_isolated.verify_chain_integrity([legacy, new])
        assert is_valid is True
        assert invalid_id is None


class TestKeyRotation:
    def setup_method(self):
        AuditLog._last_hash = None

    def test_previous_key_keeps_old_entries_verifiable(self):
        old_key, new_key = b"old-audit-key-0123456789abcdef", b"new-audit-key-0123456789abcdef"
        with patch.object(AuditLog, "_hmac_key", old_key):
            (entry,) = _entries(1)
        with patch.object(AuditLog, "_hmac_key", new_key):
            with patch.object(AuditLog, "_hmac_key_previous", None):
                assert not verify_entry_hash(entry)
            with patch.object(AuditLog, "_hmac_key_previous", old_key):
                assert verify_entry_hash(entry)

    def test_previous_key_does_not_accept_tampering(self):
        old_key, new_key = b"old-audit-key-0123456789abcdef", b"new-audit-key-0123456789abcdef"
        with patch.object(AuditLog, "_hmac_key", old_key):
            (entry,) = _entries(1)
        entry["action"]["filename"] = "edited.pdf"
        with (
            patch.object(AuditLog, "_hmac_key", new_key),
            patch.object(AuditLog, "_hmac_key_previous", old_key),
        ):
            assert not verify_entry_hash(entry)


class TestStartupVerification:
    def setup_method(self):
        AuditLog._last_hash = None

    def _write(self, service, entries: list[dict]) -> None:
        path = service.log_dir / "audit_2026-08-26.jsonl"
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

    @staticmethod
    def _production():
        # Settings is frozen; swap the module-level reference for a copy.
        prod = settings.model_copy(
            update={"debug": False, "audit_halt_on_tampering": True}
        )
        return patch("app.services.audit.settings", prod)

    def test_clean_chain_passes(self, audit_service_isolated):
        self._write(audit_service_isolated, _entries(4))
        with self._production():
            audit_service_isolated._verify_chain_on_startup()  # no raise

    def test_edited_details_halt_startup_in_production(self, audit_service_isolated):
        entries = _entries(4)
        entries[2]["action"]["filename"] = "edited-on-disk.pdf"
        self._write(audit_service_isolated, entries)
        with self._production(), pytest.raises(RuntimeError, match="HMAC MISMATCH"):
            audit_service_isolated._verify_chain_on_startup()

    def test_rewritten_chain_without_key_halts_startup(self, audit_service_isolated):
        """An attacker who rewrites entries and re-links previous_hash pointers
        consistently used to pass the linkage-only check."""
        entries = _entries(3)
        forged_key = b"attacker-does-not-know-the-key"
        entries[1]["action"]["filename"] = "forged.pdf"
        entries[1]["integrity"]["entry_hash"] = compute_entry_hash(entries[1], forged_key)
        entries[2]["integrity"]["previous_hash"] = entries[1]["integrity"]["entry_hash"]
        entries[2]["integrity"]["entry_hash"] = compute_entry_hash(entries[2], forged_key)
        self._write(audit_service_isolated, entries)
        with self._production(), pytest.raises(RuntimeError, match="HMAC MISMATCH"):
            audit_service_isolated._verify_chain_on_startup()

    def test_broken_linkage_still_halts(self, audit_service_isolated):
        entries = _entries(3)
        entries[2]["integrity"]["previous_hash"] = "not-the-previous-hash"
        self._write(audit_service_isolated, entries)
        with self._production(), pytest.raises(RuntimeError, match="CHAIN INTEGRITY BROKEN"):
            audit_service_isolated._verify_chain_on_startup()

    def test_debug_mode_logs_but_does_not_halt(self, audit_service_isolated):
        entries = _entries(2)
        entries[0]["action"]["filename"] = "edited.pdf"
        self._write(audit_service_isolated, entries)
        dev = settings.model_copy(update={"debug": True, "audit_halt_on_tampering": True})
        with patch("app.services.audit.settings", dev):
            audit_service_isolated._verify_chain_on_startup()  # no raise
