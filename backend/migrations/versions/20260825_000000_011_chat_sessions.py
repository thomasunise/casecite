"""Persistent chat sessions: the ``chat_sessions`` and ``chat_messages`` tables.

The models have existed since 2026-07-14 but no migration ever created
them — the runtime ``create_all`` backstop in ``app.main`` masked the gap on
running installs while ``alembic check`` (schema drift) reports it. Both
creates are ``checkfirst`` so installs whose backstop already built the
tables upgrade cleanly.

Revision ID: 011
Revises: 010
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: str = "010"
branch_labels = None
depends_on = None


def _metadata():
    from app.models.base import Base
    from app.models.chat_sessions import ChatMessageDB, ChatSessionDB  # noqa: F401

    return Base.metadata


def upgrade() -> None:
    bind = op.get_bind()
    metadata = _metadata()
    # Parent before child so the messages FK has its target.
    for name in ("chat_sessions", "chat_messages"):
        table = metadata.tables.get(name)
        if table is not None:
            metadata.create_all(bind=bind, tables=[table], checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    # Drop child (messages) before parent (sessions) to respect the FK.
    for name in ("chat_messages", "chat_sessions"):
        if name in existing:
            op.drop_table(name)
