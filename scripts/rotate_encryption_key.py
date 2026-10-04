#!/usr/bin/env python3
"""
Encryption Key Rotation for CaseCite

Generates a new ENCRYPTION_SALT and prints the exact .env changes needed.
Does NOT modify any files — you review and apply the changes yourself.

Usage:
    python scripts/rotate_encryption_key.py

After running:
    1. Update your .env with the printed values
    2. Restart the application
    3. (Optional) Run with --re-encrypt to migrate old ciphertexts
"""

import argparse
import secrets
from pathlib import Path


def generate_new_salt() -> str:
    """Generate a cryptographically secure encryption salt (32 hex chars = 16 bytes)."""
    return secrets.token_hex(16)


def read_current_env(env_path: Path) -> dict[str, str]:
    """Read current .env values (ignores comments and blank lines)."""
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def rotate(env_path: Path) -> None:
    """Generate a new salt and print the .env update instructions."""
    env = read_current_env(env_path)

    current_salt = env.get("ENCRYPTION_SALT", "")
    previous_salts = env.get("ENCRYPTION_SALT_PREVIOUS", "")
    new_salt = generate_new_salt()

    # Build the new previous-salts list: prepend current salt to existing list
    if current_salt:
        if previous_salts:
            new_previous = f"{current_salt},{previous_salts}"
        else:
            new_previous = current_salt
    else:
        new_previous = previous_salts

    print()
    print("=" * 64)
    print("  ENCRYPTION KEY ROTATION")
    print("=" * 64)

    if not current_salt:
        print()
        print("  WARNING: No current ENCRYPTION_SALT found in .env")
        print("  This appears to be a fresh deployment.")
        print(f"  Set ENCRYPTION_SALT={new_salt} and you're done.")
        print()
        print("=" * 64)
        return

    print()
    print("  Update your .env file with these values:")
    print()
    print(f"  ENCRYPTION_SALT={new_salt}")
    print(f"  ENCRYPTION_SALT_PREVIOUS={new_previous}")
    print()
    print("-" * 64)
    print("  The current salt moves to the front of ENCRYPTION_SALT_PREVIOUS so")
    print("  existing ciphertexts stay readable. Treat this output like the .env")
    print("  itself: do not paste it into tickets, chat or shell history.")
    print("-" * 64)
    print()
    print("  Steps:")
    print("    1. Copy the two lines above into your .env file")
    print("    2. Restart the application")
    print("    3. Verify the app starts without errors")
    print("    4. All new encryptions will use the new key")
    print("    5. Old data is still readable via previous keys")
    print()
    print("  To migrate old ciphertexts to the new key (optional):")
    print("    python scripts/rotate_encryption_key.py --re-encrypt")
    print()
    print("=" * 64)
    print()


def re_encrypt_guide() -> None:
    """Print how to rewrite existing ciphertexts under the new salt."""
    print()
    print("=" * 64)
    print("  RE-ENCRYPTION")
    print("=" * 64)
    print()
    print("  After rotating and restarting, existing ciphertexts still decrypt")
    print("  via ENCRYPTION_SALT_PREVIOUS but are not rewritten until saved")
    print("  again. Rewrite all of them under the new salt in one pass:")
    print()
    print("    docker compose -f docker-compose.prod.yml exec backend \\")
    print("        python -m app.utils.reencrypt --dry-run   # report only")
    print("    docker compose -f docker-compose.prod.yml exec backend \\")
    print("        python -m app.utils.reencrypt             # rewrite")
    print()
    print("  Covers: the BYOK key store (data/.user_keys.json), connector")
    print("  OAuth credential files, users.mfa_secret, and instance_secrets.")
    print("  Uploaded documents are keyed from SECRET_KEY, not the salt, and")
    print("  are unaffected by this rotation.")
    print()
    print("  When it reports 0 failures, remove ENCRYPTION_SALT_PREVIOUS from")
    print("  .env and run `docker compose -f docker-compose.prod.yml up -d backend`.")
    print()
    print("=" * 64)
    print()


def main():
    parser = argparse.ArgumentParser(description="Encryption key rotation for CaseCite")
    parser.add_argument(
        "--env-file",
        type=str,
        default=".env",
        help="Path to .env file (default: .env in project root)",
    )
    parser.add_argument(
        "--re-encrypt",
        action="store_true",
        help="Show guide for re-encrypting existing data after rotation",
    )

    args = parser.parse_args()

    if args.re_encrypt:
        re_encrypt_guide()
        return

    # Find project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    env_path = project_root / args.env_file

    rotate(env_path)


if __name__ == "__main__":
    main()
