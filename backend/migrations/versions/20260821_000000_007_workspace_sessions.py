"""Universal History: the workspace_sessions table.

Restorable snapshots of every surface's working session — contracts
conversations (including the drafting workspace), each legal tool's search and
result-chat, judge-intel Q&A, and case pages. Created from the model metadata
so fresh and brownfield installs land on the same shape.

Revision ID: 007
Revises: 006
Create Date: 2026-08-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: str = "006"
branch_labels = None
depends_on = None


def _metadata():
    from app.models.base import Base
    from app.models.tracking import WorkspaceSessionDB  # noqa: F401

    return Base.metadata


def upgrade() -> None:
    bind = op.get_bind()
    metadata = _metadata()
    table = metadata.tables.get("workspace_sessions")
    if table is not None:
        metadata.create_all(bind=bind, tables=[table], checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "workspace_sessions" in inspector.get_table_names():
        op.drop_table("workspace_sessions")
