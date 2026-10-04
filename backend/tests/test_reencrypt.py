"""
ENCRYPTION_SALT rotation: app.utils.reencrypt rewrites every store under the
current salt so ENCRYPTION_SALT_PREVIOUS can be dropped afterwards.
"""

import json
from unittest.mock import patch

import pytest
from app.config import settings
from app.services.encryption import EncryptionService
from app.utils import reencrypt


@pytest.fixture
def rotated(tmp_path):
    """An EncryptionService whose *previous* salt wrote the existing data."""
    old = EncryptionService.__new__(EncryptionService)
    old_settings = settings.model_copy(
        update={"encryption_salt": "a" * 32, "encryption_salt_previous": ""}
    )
    with patch("app.services.encryption.settings", old_settings):
        old.__init__()
    new = EncryptionService.__new__(EncryptionService)
    new_settings = settings.model_copy(
        update={"encryption_salt": "b" * 32, "encryption_salt_previous": "a" * 32}
    )
    with patch("app.services.encryption.settings", new_settings):
        new.__init__()
    return old, new


def test_key_store_and_connector_files_are_rewritten(tmp_path, rotated):
    old, new = rotated
    keys_file = tmp_path / ".user_keys.json"
    keys_file.write_text(json.dumps({"u1": old.encrypt_string(json.dumps({"openai": "sk-1"}))}))
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    cred = uploads / "credentials_google_drive_u1.json"
    cred.write_text(old.encrypt_string(json.dumps({"refresh_token": "r"})))
    legacy_plain = uploads / "credentials_box_u2.json"
    legacy_plain.write_text(json.dumps({"token": "plain"}))

    with (
        patch("app.utils.reencrypt.encryption_service", new),
        patch("app.services.key_storage._KEYS_FILE", keys_file),
        patch(
            "app.utils.reencrypt.settings", settings.model_copy(update={"upload_dir": str(uploads)})
        ),
    ):
        report = reencrypt.reencrypt_key_store(dry_run=False)
        report.merge(reencrypt.reencrypt_connector_credentials(dry_run=False))

    assert report.rewritten == 2
    assert report.unchanged == 1  # legacy plaintext file left for the connector to migrate
    assert report.failed == []

    # Rewritten values decrypt under the NEW salt alone (no previous salt configured).
    strict = EncryptionService.__new__(EncryptionService)
    with patch(
        "app.services.encryption.settings",
        settings.model_copy(update={"encryption_salt": "b" * 32, "encryption_salt_previous": ""}),
    ):
        strict.__init__()
    stored = json.loads(keys_file.read_text())
    assert json.loads(strict.decrypt_string(stored["u1"])) == {"openai": "sk-1"}
    assert json.loads(strict.decrypt_string(cred.read_text())) == {"refresh_token": "r"}
    # ...and the old service can no longer read them (InvalidTag from AES-GCM).
    with pytest.raises(Exception):  # noqa: B017 - any decrypt failure is the point
        old.decrypt_string(stored["u1"])


def test_dry_run_writes_nothing(tmp_path, rotated):
    old, new = rotated
    keys_file = tmp_path / ".user_keys.json"
    original = json.dumps({"u1": old.encrypt_string("{}")})
    keys_file.write_text(original)
    with (
        patch("app.utils.reencrypt.encryption_service", new),
        patch("app.services.key_storage._KEYS_FILE", keys_file),
    ):
        report = reencrypt.reencrypt_key_store(dry_run=True)
    assert report.rewritten == 1
    assert keys_file.read_text() == original


def test_undecryptable_values_are_reported_not_clobbered(tmp_path, rotated):
    _, new = rotated
    keys_file = tmp_path / ".user_keys.json"
    keys_file.write_text(json.dumps({"u1": "bm90LWEtcmVhbC1jaXBoZXJ0ZXh0"}))
    with (
        patch("app.utils.reencrypt.encryption_service", new),
        patch("app.services.key_storage._KEYS_FILE", keys_file),
    ):
        report = reencrypt.reencrypt_key_store(dry_run=False)
    assert report.rewritten == 0
    assert len(report.failed) == 1
    assert json.loads(keys_file.read_text())["u1"] == "bm90LWEtcmVhbC1jaXBoZXJ0ZXh0"


def test_refuses_to_run_without_previous_salt(capsys):
    with (
        patch(
            "app.utils.reencrypt.settings",
            settings.model_copy(update={"encryption_salt_previous": ""}),
        ),
        patch("sys.argv", ["reencrypt"]),
    ):
        assert reencrypt.main() == 2
    assert "ENCRYPTION_SALT_PREVIOUS is not set" in capsys.readouterr().out
