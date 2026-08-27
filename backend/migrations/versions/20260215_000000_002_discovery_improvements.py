"""Discovery improvements: user_id, workflow statuses, Bates persistence

Revision ID: 002
Revises: 001
Create Date: 2026-02-15 00:00:00.000000

Changes:
- Add user_id to discovery_sets for tenant isolation
- Add bates_productions table for persistent production tracking
- Add bates_production_documents table for document-level tracking
- Add bates_endorsement_templates table for persistent templates
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add user_id to discovery_sets for tenant isolation
    with op.batch_alter_table("discovery_sets") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.String(36), nullable=True))
        batch_op.create_index("idx_discovery_user", ["user_id"])
        batch_op.create_foreign_key(
            "fk_discovery_sets_user_id", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )

    # Bates productions table
    op.create_table(
        "bates_productions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("matter_id", sa.String(100), nullable=False),
        sa.Column("matter_name", sa.String(255), nullable=False),
        sa.Column("producing_party", sa.String(255), nullable=False),
        sa.Column("receiving_party", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), default="created"),
        sa.Column("total_documents", sa.Integer, default=0),
        sa.Column("total_pages", sa.Integer, default=0),
        sa.Column("bates_ranges", sa.JSON, nullable=True),
        sa.Column("metadata_json", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("finalized_at", sa.DateTime, nullable=True),
    )
    op.create_index("idx_bates_prod_matter", "bates_productions", ["matter_id"])
    op.create_index("idx_bates_prod_user", "bates_productions", ["user_id"])

    # Bates production documents table
    op.create_table(
        "bates_production_documents",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "production_id",
            sa.String(36),
            sa.ForeignKey("bates_productions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("batch_id", sa.String(100), nullable=True),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("stamped_filename", sa.String(500), nullable=True),
        sa.Column("pages", sa.Integer, default=0),
        sa.Column("bates_start", sa.String(100), nullable=True),
        sa.Column("bates_end", sa.String(100), nullable=True),
        sa.Column("md5_hash", sa.String(32), nullable=True),
        sa.Column("file_size", sa.Integer, nullable=True),
        sa.Column("converted_from", sa.String(50), nullable=True),
        sa.Column("ocr_applied", sa.Boolean, default=False),
        sa.Column("qc_passed", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_bates_doc_production", "bates_production_documents", ["production_id"])

    # Bates endorsement templates table
    op.create_table(
        "bates_endorsement_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("matter_id", sa.String(100), nullable=True),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("idx_bates_tmpl_user", "bates_endorsement_templates", ["user_id"])


def downgrade() -> None:
    op.drop_table("bates_endorsement_templates")
    op.drop_table("bates_production_documents")
    op.drop_table("bates_productions")

    with op.batch_alter_table("discovery_sets") as batch_op:
        batch_op.drop_constraint("fk_discovery_sets_user_id", type_="foreignkey")
        batch_op.drop_index("idx_discovery_user")
        batch_op.drop_column("user_id")
