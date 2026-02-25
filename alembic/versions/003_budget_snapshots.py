"""Add budget_snapshots table for change history.

Revision ID: 003
Revises: 002
Create Date: 2026-02-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "budget_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("month", sa.String(), nullable=False),
        sa.Column("changed_category_id", sa.String(), nullable=True),
        sa.Column("previous_amount", sa.Integer(), nullable=True),
        sa.Column("new_amount", sa.Integer(), nullable=True),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("source", sa.String(), server_default="api", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_budget_snapshots_month", "budget_snapshots", ["month"])


def downgrade() -> None:
    op.drop_index("ix_budget_snapshots_month", table_name="budget_snapshots")
    op.drop_table("budget_snapshots")
