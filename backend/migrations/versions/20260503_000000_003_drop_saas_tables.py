"""Drop SaaS-only tables (subscriptions, purchases, fingerprints, etag_tracking, ip_velocity, blocked_fingerprints)

Revision ID: 003
Revises: 002
Create Date: 2026-05-03 00:00:00.000000

Strips Stripe billing and trial-abuse-prevention tables from the source-available
build. The SaaS version retains them in a separate repo.

Sanitized 2026-08: migration 001 no longer creates these tables, so the drops
here are inspector-guarded (same pattern as migrations 005/009/010) — a fresh
install passes through as a no-op, while brownfield databases built by the
pre-sanitization chain still get the tables dropped.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_tables() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def upgrade() -> None:
    # Children before parents (purchases has an FK to subscriptions).
    for name in (
        "purchases",
        "subscriptions",
        "blocked_fingerprints",
        "ip_velocity",
        "etag_tracking",
        "fingerprints",
    ):
        if name in _existing_tables():
            op.drop_table(name)


def downgrade() -> None:
    # Deliberate no-op: the Stripe billing / fingerprinting schema is not part
    # of the source-available product and is never recreated on downgrade.
    # Migration 001 no longer creates (or drops) these tables either, so the
    # downgrade path stays consistent end to end.
    pass
