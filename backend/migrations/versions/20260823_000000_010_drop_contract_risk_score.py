"""Drop the contract risk score and the rule-based risk-findings table.

The product rule is that contract review lists issues, it does not grade them.
The numeric ``overall_risk_score`` column and the ``contract_risk_findings``
table (whose rule engine was never wired into the pipeline) are removed.
Both drops are idempotent so a re-upgrade after a partial run is safe.

Revision ID: 010
Revises: 009
Create Date: 2026-08-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: str = "009"
branch_labels = None
depends_on = None

_RUNS = "contract_analysis_runs"
_RISK = "contract_risk_findings"


def _has_column(bind, table: str, column: str) -> bool:
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    cascade = " CASCADE" if bind.dialect.name == "postgresql" else ""
    op.execute(f'DROP TABLE IF EXISTS "{_RISK}"{cascade}')

    if _has_column(bind, _RUNS, "overall_risk_score"):
        with op.batch_alter_table(_RUNS) as batch:
            batch.drop_column("overall_risk_score")


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, _RUNS, "overall_risk_score"):
        with op.batch_alter_table(_RUNS) as batch:
            batch.add_column(sa.Column("overall_risk_score", sa.Integer(), nullable=True))

    if _RISK not in inspect(bind).get_table_names():
        op.create_table(
            _RISK,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("analysis_id", sa.String(length=64), nullable=False),
            sa.Column("rule_slug", sa.String(length=80), nullable=False),
            sa.Column("rule_name", sa.String(length=200), nullable=False),
            sa.Column("category", sa.String(length=40), nullable=False),
            sa.Column("weight", sa.Integer(), nullable=False),
            sa.Column("severity", sa.String(length=20), nullable=False),
            sa.Column("matched_text", sa.Text(), nullable=True),
            sa.Column("span_start", sa.Integer(), nullable=True),
            sa.Column("span_end", sa.Integer(), nullable=True),
            sa.Column("detail", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index(f"ix_{_RISK}_analysis_id", _RISK, ["analysis_id"])
        op.create_index("idx_contract_risk_analysis", _RISK, ["analysis_id"])
