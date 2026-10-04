"""Initial database schema

Revision ID: 001
Revises:
Create Date: 2026-01-31 00:00:00.000000

This migration creates all initial tables for the CaseCite platform:
- Users and authentication
- Documents and templates
- Discovery management
- Audit logging
- Deadline rules and holidays

Note (2026-08 sanitization): the SaaS-era tables this migration originally
created (subscriptions, purchases, fingerprints, etag_tracking, ip_velocity,
blocked_fingerprints) were removed from it — the source-available product never
uses them. Migration 003 drops them with inspector guards, so brownfield
databases built by the pre-sanitization chain are still cleaned up.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ==========================================================================
    # Users Table
    # ==========================================================================
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("roles", sa.JSON, default=["attorney"]),
        sa.Column("azure_oid", sa.String(255), unique=True, nullable=True),
        sa.Column("tenant_id", sa.String(255), nullable=True),
        sa.Column("mfa_enabled", sa.Boolean, default=False),
        sa.Column("email_verified", sa.Boolean, default=False),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("last_login", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, onupdate=sa.func.now()),
    )
    op.create_index("idx_user_email", "users", ["email"])
    op.create_index("idx_user_azure_oid", "users", ["azure_oid"])
    op.create_index("idx_user_email_active", "users", ["email", "is_active"])

    # ==========================================================================
    # Templates Table
    # ==========================================================================
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
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, onupdate=sa.func.now()),
    )
    op.create_index("idx_template_type", "templates", ["document_type"])
    op.create_index("idx_template_jurisdiction", "templates", ["jurisdiction"])

    # ==========================================================================
    # Template Versions Table
    # ==========================================================================
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
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_template_version", "template_versions", ["template_id", "version_number"]
    )

    # ==========================================================================
    # Clauses Table
    # ==========================================================================
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
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, onupdate=sa.func.now()),
    )
    op.create_index("idx_clause_category", "clauses", ["category"])

    # ==========================================================================
    # Clause Variants Table
    # ==========================================================================
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
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, onupdate=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_clause_jurisdiction", "clause_variants", ["clause_id", "jurisdiction"]
    )

    # ==========================================================================
    # Court Rules Table
    # ==========================================================================
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
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, onupdate=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_court_rule", "court_rules", ["court_id", "rule_type", "document_type", "rule_key"]
    )
    op.create_index("idx_court_rules_court", "court_rules", ["court_id"])

    # ==========================================================================
    # Generated Documents Table
    # ==========================================================================
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
        sa.Column("parent_id", sa.Integer, sa.ForeignKey("generated_documents.id"), nullable=True),
        sa.Column("metadata", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ==========================================================================
    # Discovery Sets Table
    # ==========================================================================
    op.create_table(
        "discovery_sets",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("case_name", sa.String(255), nullable=False),
        sa.Column("case_number", sa.String(100), nullable=True),
        sa.Column("court", sa.String(255), nullable=True),
        sa.Column("propounding_party", sa.String(255), nullable=True),
        sa.Column("responding_party", sa.String(255), nullable=True),
        sa.Column("discovery_type", sa.String(50), nullable=False),
        sa.Column("set_number", sa.Integer, default=1),
        sa.Column("date_served", sa.Date, nullable=True),
        sa.Column("date_due", sa.Date, nullable=True),
        sa.Column("date_extended", sa.Date, nullable=True),
        sa.Column("status", sa.String(50), default="pending"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, onupdate=sa.func.now()),
    )
    op.create_index("idx_discovery_case", "discovery_sets", ["case_number"])

    # ==========================================================================
    # Discovery Requests Table
    # ==========================================================================
    op.create_table(
        "discovery_requests",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "set_id",
            sa.Integer,
            sa.ForeignKey("discovery_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_number", sa.Integer, nullable=False),
        sa.Column("request_text", sa.Text, nullable=False),
        sa.Column("response_text", sa.Text, nullable=True),
        sa.Column("objections", sa.Text, nullable=True),
        sa.Column("supplemental_response", sa.Text, nullable=True),
        sa.Column("status", sa.String(50), default="pending"),
        sa.Column("privilege_claimed", sa.Boolean, default=False),
        sa.Column("documents_responsive", sa.JSON, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, onupdate=sa.func.now()),
    )

    # ==========================================================================
    # Privilege Log Table
    # ==========================================================================
    op.create_table(
        "privilege_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "set_id",
            sa.Integer,
            sa.ForeignKey("discovery_sets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("case_id", sa.String(100), nullable=True),
        sa.Column("bates_start", sa.String(50), nullable=True),
        sa.Column("bates_end", sa.String(50), nullable=True),
        sa.Column("document_date", sa.Date, nullable=True),
        sa.Column("document_type", sa.String(100), nullable=True),
        sa.Column("document_description", sa.Text, nullable=True),
        sa.Column("author", sa.String(255), nullable=True),
        sa.Column("recipients", sa.Text, nullable=True),
        sa.Column("privilege_type", sa.String(50), nullable=False),
        sa.Column("privilege_basis", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ==========================================================================
    # Bates Sequences Table
    # ==========================================================================
    op.create_table(
        "bates_sequences",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.String(100), nullable=False),
        sa.Column("prefix", sa.String(50), nullable=False),
        sa.Column("current_number", sa.Integer, default=0),
        sa.Column("pad_length", sa.Integer, default=6),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_bates_sequence", "bates_sequences", ["case_id", "prefix"])

    # ==========================================================================
    # Audit Logs Table
    # ==========================================================================
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("user_email", sa.String(255), nullable=True),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("action_details", sa.JSON, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("success", sa.Boolean, default=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("environment", sa.String(50), nullable=True),
    )
    op.create_index("idx_audit_timestamp", "audit_logs", ["timestamp"])
    op.create_index("idx_audit_event_type", "audit_logs", ["event_type"])
    op.create_index("idx_audit_user", "audit_logs", ["user_id"])
    op.create_index("idx_audit_timestamp_type", "audit_logs", ["timestamp", "event_type"])

    # ==========================================================================
    # Deadline Rules Table
    # ==========================================================================
    op.create_table(
        "deadline_rules",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("jurisdiction", sa.String(100), nullable=False),
        sa.Column("court_type", sa.String(50), nullable=False),
        sa.Column("discovery_type", sa.String(50), nullable=False),
        sa.Column("base_days", sa.Integer, nullable=False),
        sa.Column("service_method", sa.String(50), nullable=True),
        sa.Column("additional_days", sa.Integer, default=0),
        sa.Column("exclude_weekends", sa.Boolean, default=True),
        sa.Column("exclude_holidays", sa.Boolean, default=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("rule_citation", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_deadline_rule",
        "deadline_rules",
        ["jurisdiction", "court_type", "discovery_type", "service_method"],
    )

    # ==========================================================================
    # Jurisdiction Holidays Table
    # ==========================================================================
    op.create_table(
        "jurisdiction_holidays",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("jurisdiction", sa.String(100), nullable=False),
        sa.Column("holiday_date", sa.Date, nullable=False),
        sa.Column("holiday_name", sa.String(255), nullable=False),
        sa.Column("is_court_closed", sa.Boolean, default=True),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_jurisdiction_holiday", "jurisdiction_holidays", ["jurisdiction", "holiday_date"]
    )
    op.create_index(
        "idx_holiday_jurisdiction_year", "jurisdiction_holidays", ["jurisdiction", "year"]
    )


def downgrade() -> None:
    # Drop tables in reverse order of creation (respecting foreign keys)
    op.drop_table("jurisdiction_holidays")
    op.drop_table("deadline_rules")
    op.drop_table("audit_logs")
    op.drop_table("bates_sequences")
    op.drop_table("privilege_log")
    op.drop_table("discovery_requests")
    op.drop_table("discovery_sets")
    op.drop_table("generated_documents")
    op.drop_table("court_rules")
    op.drop_table("clause_variants")
    op.drop_table("clauses")
    op.drop_table("template_versions")
    op.drop_table("templates")
    op.drop_table("users")
