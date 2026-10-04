"""Session-control columns on ``users``: forced password change and token version.

``must_change_password`` is set when an admin invites a user (the admin has
seen the temporary password) and cleared by a successful password
change/reset; while set, the API only admits the password-change endpoints.

``token_version`` is embedded in every access/refresh token (``tv`` claim).
Bumping it — "log out everywhere", admin force sign-out, refresh-token reuse —
invalidates every outstanding token for that user on every device.

Both adds are inspector-guarded so installs whose runtime backstop already
built the columns upgrade cleanly, and both carry a server default so existing
rows are valid without a backfill.

Revision ID: 013
Revises: 012
Create Date: 2026-10-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: str = "012"
branch_labels = None
depends_on = None


def _existing_columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    existing = _existing_columns("users")
    if "must_change_password" not in existing:
        op.add_column(
            "users",
            sa.Column(
                "must_change_password",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    if "token_version" not in existing:
        op.add_column(
            "users",
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    existing = _existing_columns("users")
    with op.batch_alter_table("users") as batch:
        if "token_version" in existing:
            batch.drop_column("token_version")
        if "must_change_password" in existing:
            batch.drop_column("must_change_password")
