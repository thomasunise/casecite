"""Drop the tables of removed products that the app never read.

``templates``, ``template_versions``, ``clauses``, ``clause_variants``,
``court_rules`` and ``generated_documents`` (created in 001, aligned in 005)
belonged to the removed document-assembly / pleadings products;
``saved_searches``, ``ai_usage_logs`` and ``matter_ai_exclusions`` (created in
004) to the removed saved-search and AI-disclosure features. No router or
service ever read from or wrote to any of them — only the ORM models existed,
and those are deleted in the same change — so every one of these tables is
empty on every install and the drop is data-free by construction.

Each drop is inspector-guarded (skipped when the table is absent) so installs
whose ``create_all`` backstop never built a given table upgrade cleanly.
``downgrade()`` recreates the tables as migration 011 left them, so the CI gate
(``upgrade head`` → ``downgrade -1`` → ``upgrade head`` → ``alembic check``)
round-trips.

Revision ID: 012
Revises: 011
Create Date: 2026-08-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: str = "011"
branch_labels = None
depends_on = None

# Children before parents so the drops satisfy FK constraints on PostgreSQL
# (template_versions → templates, clause_variants → clauses; the other tables
# only reference users or themselves).
_DROPPED_TABLES = [
    "template_versions",
    "templates",
    "clause_variants",
    "clauses",
    "court_rules",
    "generated_documents",
    "saved_searches",
    "ai_usage_logs",
    "matter_ai_exclusions",
]


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    existing = _existing_tables()
    for name in _DROPPED_TABLES:
        if name in existing:
            op.drop_table(name)


def _recreate_templates() -> None:
    op.create_table(
        "templates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("document_type", sa.String(100), nullable=False),
        sa.Column("jurisdiction", sa.String(100), nullable=True),
        sa.Column("court_id", sa.String(100), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("merge_fields", sa.JSON, nullable=True),
        sa.Column("is_system", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, onupdate=sa.func.now()),
    )
    op.create_index("idx_template_type", "templates", ["document_type"])
    op.create_index("idx_template_jurisdiction", "templates", ["jurisdiction"])


def _recreate_template_versions() -> None:
    op.create_table(
        "template_versions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "template_id",
            sa.Integer,
            sa.ForeignKey("templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("merge_fields", sa.JSON, nullable=True),
        sa.Column("change_summary", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("template_id", "version_number", name="uq_template_version"),
    )


def _recreate_clauses() -> None:
    op.create_table(
        "clauses",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("subcategory", sa.String(100), nullable=True),
        sa.Column("jurisdiction", sa.String(100), nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("tags", sa.JSON, nullable=True),
        sa.Column("usage_count", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, onupdate=sa.func.now()),
    )
    op.create_index("idx_clause_category", "clauses", ["category"])


def _recreate_clause_variants() -> None:
    op.create_table(
        "clause_variants",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "clause_id", sa.Integer, sa.ForeignKey("clauses.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("jurisdiction", sa.String(100), nullable=False),
        sa.Column("variant_content", sa.Text, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("effective_date", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, onupdate=sa.func.now()),
        sa.UniqueConstraint("clause_id", "jurisdiction", name="uq_clause_jurisdiction"),
    )


def _recreate_court_rules() -> None:
    op.create_table(
        "court_rules",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("court_id", sa.String(100), nullable=False),
        sa.Column("court_name", sa.String(255), nullable=False),
        sa.Column("jurisdiction_type", sa.String(50), nullable=False),
        sa.Column("rule_type", sa.String(100), nullable=False),
        sa.Column("document_type", sa.String(100), nullable=True),
        sa.Column("rule_key", sa.String(100), nullable=False),
        sa.Column("rule_value", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, onupdate=sa.func.now()),
        sa.UniqueConstraint(
            "court_id", "rule_type", "document_type", "rule_key", name="uq_court_rule"
        ),
    )
    op.create_index("idx_court_rules_court", "court_rules", ["court_id"])


def _recreate_generated_documents() -> None:
    op.create_table(
        "generated_documents",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("document_type", sa.String(100), nullable=False),
        sa.Column("case_name", sa.String(255), nullable=True),
        sa.Column("case_number", sa.String(100), nullable=True),
        sa.Column("court", sa.String(255), nullable=True),
        sa.Column("jurisdiction", sa.String(100), nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("file_format", sa.String(20), nullable=True),
        sa.Column("version", sa.Integer, default=1),
        sa.Column(
            "parent_id",
            sa.Integer,
            sa.ForeignKey("generated_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("metadata", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def _recreate_saved_searches() -> None:
    op.create_table(
        "saved_searches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("filters", sa.JSON, nullable=True),
        sa.Column("search_type", sa.String(50), nullable=True),
        sa.Column("alert_enabled", sa.Boolean, nullable=True),
        sa.Column("last_run_at", sa.DateTime, nullable=True),
        sa.Column("result_count", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("idx_saved_search_user", "saved_searches", ["user_id"])


def _recreate_ai_usage_logs() -> None:
    op.create_table(
        "ai_usage_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("matter_id", sa.String(36), nullable=True),
        sa.Column("document_id", sa.String(255), nullable=True),
        sa.Column("ai_provider", sa.String(50), nullable=False),
        sa.Column("ai_model", sa.String(100), nullable=False),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("input_summary", sa.Text, nullable=True),
        sa.Column("output_summary", sa.Text, nullable=True),
        sa.Column("tokens_used", sa.Integer, nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("idx_ai_usage_user", "ai_usage_logs", ["user_id"])
    op.create_index("idx_ai_usage_matter", "ai_usage_logs", ["matter_id"])


def _recreate_matter_ai_exclusions() -> None:
    op.create_table(
        "matter_ai_exclusions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("matter_id", sa.String(36), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("excluded_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("user_id", "matter_id", name="uq_matter_ai_exclusion"),
    )
    op.create_index("idx_ai_exclusion_user", "matter_ai_exclusions", ["user_id"])
    op.create_index("idx_ai_exclusion_matter", "matter_ai_exclusions", ["matter_id"])


# Parents before children so the FK targets exist when a child is created.
_RECREATE = {
    "templates": _recreate_templates,
    "template_versions": _recreate_template_versions,
    "clauses": _recreate_clauses,
    "clause_variants": _recreate_clause_variants,
    "court_rules": _recreate_court_rules,
    "generated_documents": _recreate_generated_documents,
    "saved_searches": _recreate_saved_searches,
    "ai_usage_logs": _recreate_ai_usage_logs,
    "matter_ai_exclusions": _recreate_matter_ai_exclusions,
}


def downgrade() -> None:
    existing = _existing_tables()
    for name, recreate in _RECREATE.items():
        if name not in existing:
            recreate()
