"""Bring the authority-map tables under migration control and add reasoning.

authority_map_runs / authority_mappings were previously created only by the
runtime create_all() backstop (their models were never imported by
migrations/env.py, so Alembic could not see them). This migration creates them
from the model metadata where missing, and adds the new
authority_mappings.reasoning JSON column (the auditable reasoning chain shown
in the citation modal) on installs whose table predates it.

Revision ID: 006
Revises: 005
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: str = "005"
branch_labels = None
depends_on = None

_TABLES = ["authority_map_runs", "authority_mappings"]


def _metadata():
    from app.models.authority_map import AuthorityMapping, AuthorityMapRun  # noqa: F401
    from app.models.base import Base

    return Base.metadata


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    metadata = _metadata()

    # Create the tables from the models where missing (fresh migration-built DBs).
    tables = [metadata.tables[name] for name in _TABLES if name in metadata.tables]
    metadata.create_all(bind=bind, tables=tables, checkfirst=True)

    # Installs whose tables came from an older create_all lack the new column.
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("authority_mappings")}
    if "reasoning" not in columns:
        op.add_column("authority_mappings", sa.Column("reasoning", sa.JSON(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {col["name"] for col in inspector.get_columns("authority_mappings")}
    if "reasoning" in columns:
        op.drop_column("authority_mappings", "reasoning")
    # The tables themselves are left in place (they may hold user data and
    # predate migration control).
