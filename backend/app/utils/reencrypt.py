"""
Re-encrypt everything protected by ENCRYPTION_SALT under the current salt.

After rotating ENCRYPTION_SALT (moving the old value into
ENCRYPTION_SALT_PREVIOUS), existing ciphertexts still decrypt via the previous
salt but are not rewritten until they are next saved. This walks every store
that uses ``encryption_service`` and rewrites each value with the current key,
so ENCRYPTION_SALT_PREVIOUS can then be dropped:

  - the BYOK key store          data/.user_keys.json
  - connector OAuth credentials  <upload_dir>/credentials_*.json
  - TOTP secrets                 users.mfa_secret
  - instance secrets             instance_secrets.value_encrypted

Run inside the backend container, with the NEW salt in ENCRYPTION_SALT and the
OLD one in ENCRYPTION_SALT_PREVIOUS:

    docker compose -f docker-compose.prod.yml exec backend python -m app.utils.reencrypt [--dry-run]

Values that cannot be decrypted with any configured salt are left untouched and
reported; they were already unreadable and rotating cannot recover them.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.services.encryption import encryption_service

logger = logging.getLogger(__name__)


@dataclass
class Report:
    rewritten: int = 0
    unchanged: int = 0
    failed: list[str] = field(default_factory=list)

    def merge(self, other: Report) -> None:
        self.rewritten += other.rewritten
        self.unchanged += other.unchanged
        self.failed.extend(other.failed)


def _rewrite(ciphertext: str) -> tuple[str, bool]:
    """Return (new_ciphertext, changed). Raises ValueError if undecryptable."""
    try:
        plaintext = encryption_service.decrypt_string(ciphertext)
    except Exception as e:  # InvalidTag / bad base64 / not our format — all mean "unreadable"
        raise ValueError(
            f"undecryptable with current or previous salts ({type(e).__name__})"
        ) from e
    fresh = encryption_service.encrypt_string(plaintext)
    # Round-trip check: never write something we cannot read back.
    if encryption_service.decrypt_string(fresh) != plaintext:
        raise ValueError("round-trip verification failed")
    return fresh, True


def reencrypt_key_store(dry_run: bool) -> Report:
    from app.services import key_storage

    report = Report()
    store = key_storage._load_store()
    if not store:
        return report
    updated: dict[str, str] = {}
    for user_id, blob in store.items():
        try:
            fresh, _ = _rewrite(blob)
        except ValueError as e:
            report.failed.append(f"user key store: user {user_id}: {e}")
            updated[user_id] = blob
            continue
        updated[user_id] = fresh
        report.rewritten += 1
    if not dry_run and report.rewritten:
        key_storage._write_store(updated)
    return report


def reencrypt_connector_credentials(dry_run: bool) -> Report:
    report = Report()
    upload_dir = Path(settings.upload_dir)
    if not upload_dir.exists():
        return report
    for path in sorted(upload_dir.glob("credentials_*.json")):
        raw = path.read_text().strip()
        if not raw:
            report.unchanged += 1
            continue
        try:
            fresh, _ = _rewrite(raw)
        except ValueError:
            # Legacy plaintext JSON files are migrated by the connector on next
            # read; anything else is unreadable with every configured salt.
            try:
                json.loads(raw)
                report.unchanged += 1
            except json.JSONDecodeError:
                report.failed.append(f"connector credentials: {path.name}: undecryptable")
            continue
        if not dry_run:
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(fresh)
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, path)
        report.rewritten += 1
    return report


async def reencrypt_database(dry_run: bool) -> Report:
    from app.database import AsyncSessionLocal
    from app.models.auth import User
    from app.models.tracking import InstanceSecretDB

    report = Report()
    async with AsyncSessionLocal() as session:
        users = (await session.execute(select(User).where(User.mfa_secret.isnot(None)))).scalars()
        for user in users:
            try:
                fresh, _ = _rewrite(user.mfa_secret)
            except ValueError as e:
                report.failed.append(f"users.mfa_secret: {user.id}: {e}")
                continue
            user.mfa_secret = fresh
            report.rewritten += 1
        secrets_rows = (await session.execute(select(InstanceSecretDB))).scalars()
        for row in secrets_rows:
            try:
                fresh, _ = _rewrite(row.value_encrypted)
            except ValueError as e:
                report.failed.append(f"instance_secrets: {row.name}: {e}")
                continue
            row.value_encrypted = fresh
            report.rewritten += 1
        if dry_run:
            await session.rollback()
        else:
            await session.commit()
    return report


async def run(dry_run: bool = False) -> Report:
    total = Report()
    total.merge(reencrypt_key_store(dry_run))
    total.merge(reencrypt_connector_credentials(dry_run))
    total.merge(await reencrypt_database(dry_run))
    return total


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would change; write nothing"
    )
    args = parser.parse_args()

    if not settings.encryption_salt_previous:
        print(
            "ENCRYPTION_SALT_PREVIOUS is not set. Nothing was written: without the old salt, "
            "existing ciphertexts cannot be read, let alone re-encrypted. Put the previous "
            "ENCRYPTION_SALT value in ENCRYPTION_SALT_PREVIOUS and run again."
        )
        return 2

    report = asyncio.run(run(dry_run=args.dry_run))
    verb = "would rewrite" if args.dry_run else "rewrote"
    print(f"Re-encryption {verb} {report.rewritten} value(s); {report.unchanged} left as-is.")
    for line in report.failed:
        print(f"  FAILED: {line}")
    if report.failed:
        print(
            f"{len(report.failed)} value(s) could not be decrypted with the current or previous "
            "salt and were not modified. Keep ENCRYPTION_SALT_PREVIOUS until they are re-entered."
        )
        return 1
    if not args.dry_run:
        print(
            "All values now use the current ENCRYPTION_SALT; ENCRYPTION_SALT_PREVIOUS can be removed."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
