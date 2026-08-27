"""Matters & membership: the collaboration/isolation spine.

Creates the ``matters`` and ``matter_members`` tables. Personal matters and
resource backfill are handled lazily by the matter service and a later
migration, so this revision is purely additive and changes no existing
behavior.

Revision ID: 008
Revises: 007
Create Date: 2026-08-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: str = "007"
branch_labels = None
depends_on = None


def _metadata():
    from app.models.base import Base
    from app.models.matters import Matter, MatterMember  # noqa: F401

    return Base.metadata


def upgrade() -> None:
    bind = op.get_bind()
    metadata = _metadata()
    for name in ("matters", "matter_members"):
        table = metadata.tables.get(name)
        if table is not None:
            metadata.create_all(bind=bind, tables=[table], checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    # Drop child (membership) before parent (matters) to respect the FK.
    for name in ("matter_members", "matters"):
        if name in existing:
            op.drop_table(name)
