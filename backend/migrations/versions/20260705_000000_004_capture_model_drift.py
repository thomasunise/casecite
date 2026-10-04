"""Capture model drift: add tables present in the models but missing from
migrations, and drop orphaned tables from removed features.

The 17 added tables were previously only created by the runtime create_all()
backstop (never by a migration), so a fresh `alembic upgrade head` produced an
incomplete schema. They are created here directly from the model metadata so the
column types, defaults, and foreign keys exactly match the models (and this works
on both PostgreSQL and SQLite). The 9 dropped tables belong to SaaS/discovery
features that were removed from the models; dropping them is a one-way cleanup
(downgrade does not recreate them).

Revision ID: 004
Revises: 003
Create Date: 2026-07-05
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: str = "003"
branch_labels = None
depends_on = None

# Tables defined by the models but not created by any prior migration.
_ADDED_TABLES = [
    "instance_secrets",
    "branding_config",
    "saved_searches",
    "ai_usage_logs",
    "matter_ai_exclusions",
    "judge_cache",
    "clause_canonicals",
    "clause_deviations",
    "clause_jurisdiction_rules",
    "clause_tag_findings",
    "contract_type_requirements",
    "contract_analysis_runs",
    "contract_parties",
    "contract_obligations",
    "contract_deadlines",
    "contract_defined_terms",
    "contract_risk_findings",
]

# Orphaned tables from removed features (not in the current models).
# Ordered children-before-parents so the drops satisfy FK constraints on
# PostgreSQL (privilege_log/discovery_requests reference discovery_sets;
# bates_production_documents references bates_productions).
_DROPPED_TABLES = [
    "privilege_log",
    "discovery_requests",
    "discovery_sets",
    "deadline_rules",
    "jurisdiction_holidays",
    "bates_production_documents",
    "bates_endorsement_templates",
    "bates_productions",
    "bates_sequences",
]


def _model_metadata():
    # Import both the primary models and the judge-intel model so every drift
    # table is registered on the shared metadata.
    from app.models.db_models import Base
    from app.services import judge_intel  # noqa: F401 - registers JudgeCacheDB

    return Base.metadata


def upgrade() -> None:
    bind = op.get_bind()
    metadata = _model_metadata()

    # Create the missing tables from the model definitions (dependency-ordered,
    # idempotent — skips any that already exist from the create_all backstop).
    tables = [metadata.tables[name] for name in _ADDED_TABLES if name in metadata.tables]
    metadata.create_all(bind=bind, tables=tables, checkfirst=True)

    # Drop orphaned tables from removed features. CASCADE covers any FK from a
    # table outside this list; SQLite doesn't support it (and doesn't need it —
    # FKs are off during migrations there).
    cascade = " CASCADE" if bind.dialect.name == "postgresql" else ""
    for name in _DROPPED_TABLES:
        op.execute(f'DROP TABLE IF EXISTS "{name}"{cascade}')


def downgrade() -> None:
    bind = op.get_bind()
    metadata = _model_metadata()

    tables = [metadata.tables[name] for name in reversed(_ADDED_TABLES) if name in metadata.tables]
    metadata.drop_all(bind=bind, tables=tables, checkfirst=True)
    # Note: the removed-feature tables in _DROPPED_TABLES are not recreated.
