"""Align the live schema with the models.

The migration-built schema had drifted from the models in ways create_all can
never repair (it only creates whole tables, never adds columns):

- users was missing mfa_secret / mfa_recovery_codes / password_changed_at —
  on a fresh migration-built database, TOTP MFA and password-change token
  invalidation would fail at runtime (get_current_user selects
  password_changed_at on every request).
- audit_logs was missing entry_hash / previous_hash / correlation_id — the
  tamper-evident chain columns of the DB copy of the audit trail.
- Index/constraint/server-default definitions differed from the models, which
  keeps `alembic check` (the CI drift gate) permanently red.

Column additions are guarded with an inspector so installs whose tables were
created by the create_all backstop (which already includes these columns)
upgrade cleanly. Migrations run on PostgreSQL only (see start.sh).

Revision ID: 005
Revises: 004
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: str = "004"
branch_labels = None
depends_on = None


def _existing_columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {col["name"] for col in inspector.get_columns(table)}


def _existing_indexes(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {ix["name"] for ix in inspector.get_indexes(table)}


def _existing_uniques(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {uc["name"] for uc in inspector.get_unique_constraints(table)}


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in _existing_columns(table):
        op.add_column(table, column)


def upgrade() -> None:
    # --- Missing columns (functional fixes) ---
    _add_column_if_missing("audit_logs", sa.Column("entry_hash", sa.String(length=64)))
    _add_column_if_missing("audit_logs", sa.Column("previous_hash", sa.String(length=64)))
    _add_column_if_missing("audit_logs", sa.Column("correlation_id", sa.String(length=36)))
    _add_column_if_missing("users", sa.Column("mfa_secret", sa.String(length=255)))
    _add_column_if_missing("users", sa.Column("mfa_recovery_codes", sa.JSON()))
    _add_column_if_missing("users", sa.Column("password_changed_at", sa.DateTime()))

    # --- Server-default alignment (models use client-side defaults) ---
    for table, column in [
        ("audit_logs", "timestamp"),
        ("clause_variants", "created_at"),
        ("clauses", "created_at"),
        ("court_rules", "created_at"),
        ("generated_documents", "created_at"),
        ("template_versions", "created_at"),
        ("templates", "created_at"),
        ("users", "created_at"),
    ]:
        op.alter_column(
            table,
            column,
            existing_type=sa.TIMESTAMP(),
            server_default=None,
            existing_nullable=False,
        )

    # --- Index / constraint alignment with the model definitions ---
    audit_indexes = _existing_indexes("audit_logs")
    if "idx_audit_event_type" in audit_indexes:
        op.drop_index("idx_audit_event_type", table_name="audit_logs")
    if "idx_audit_timestamp" in audit_indexes:
        op.drop_index("idx_audit_timestamp", table_name="audit_logs")
    if "idx_audit_resource" not in audit_indexes:
        op.create_index("idx_audit_resource", "audit_logs", ["resource_type", "resource_id"])
    if "ix_audit_logs_event_type" not in audit_indexes:
        op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"])
    if "ix_audit_logs_timestamp" not in audit_indexes:
        op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])

    # generated_documents.parent_id FK gains ON DELETE SET NULL (matches model).
    op.drop_constraint(
        "generated_documents_parent_id_fkey", "generated_documents", type_="foreignkey"
    )
    op.create_foreign_key(
        "generated_documents_parent_id_fkey",
        "generated_documents",
        "generated_documents",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # users: plain indexes + table-level uniques become the models' unique indexes.
    user_indexes = _existing_indexes("users")
    if "idx_user_azure_oid" in user_indexes:
        op.drop_index("idx_user_azure_oid", table_name="users")
    if "idx_user_email" in user_indexes:
        op.drop_index("idx_user_email", table_name="users")
    user_uniques = _existing_uniques("users")
    if "users_azure_oid_key" in user_uniques:
        op.drop_constraint("users_azure_oid_key", "users", type_="unique")
    if "users_email_key" in user_uniques:
        op.drop_constraint("users_email_key", "users", type_="unique")
    user_indexes = _existing_indexes("users")
    if "ix_users_azure_oid" not in user_indexes:
        op.create_index("ix_users_azure_oid", "users", ["azure_oid"], unique=True)
    if "ix_users_email" not in user_indexes:
        op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_azure_oid", table_name="users")
    op.create_unique_constraint("users_email_key", "users", ["email"])
    op.create_unique_constraint("users_azure_oid_key", "users", ["azure_oid"])
    op.create_index("idx_user_email", "users", ["email"])
    op.create_index("idx_user_azure_oid", "users", ["azure_oid"])

    op.drop_constraint(
        "generated_documents_parent_id_fkey", "generated_documents", type_="foreignkey"
    )
    op.create_foreign_key(
        "generated_documents_parent_id_fkey",
        "generated_documents",
        "generated_documents",
        ["parent_id"],
        ["id"],
    )

    op.drop_index("ix_audit_logs_timestamp", table_name="audit_logs")
    op.drop_index("ix_audit_logs_event_type", table_name="audit_logs")
    op.drop_index("idx_audit_resource", table_name="audit_logs")
    op.create_index("idx_audit_timestamp", "audit_logs", ["timestamp"])
    op.create_index("idx_audit_event_type", "audit_logs", ["event_type"])

    for table, column in [
        ("audit_logs", "timestamp"),
        ("clause_variants", "created_at"),
        ("clauses", "created_at"),
        ("court_rules", "created_at"),
        ("generated_documents", "created_at"),
        ("template_versions", "created_at"),
        ("templates", "created_at"),
        ("users", "created_at"),
    ]:
        op.alter_column(
            table,
            column,
            existing_type=sa.TIMESTAMP(),
            server_default=sa.text("now()"),
            existing_nullable=False,
        )

    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "mfa_recovery_codes")
    op.drop_column("users", "mfa_secret")
    op.drop_column("audit_logs", "correlation_id")
    op.drop_column("audit_logs", "previous_hash")
    op.drop_column("audit_logs", "entry_hash")
