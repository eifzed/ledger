"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-02-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "accounts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("currency", sa.String(), server_default="IDR", nullable=False),
        sa.Column("is_active", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "categories",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("parent_id", sa.String(), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("is_active", sa.Integer(), server_default="1", nullable=False),
    )

    op.create_table(
        "budgets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("month", sa.String(), nullable=False),
        sa.Column("category_id", sa.String(), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("limit_amount", sa.Integer(), nullable=False),
        sa.Column("scope_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("effective_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("transaction_type", sa.String(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(), server_default="IDR", nullable=False),
        sa.Column("category_id", sa.String(), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("merchant", sa.String(), nullable=True),
        sa.Column("payment_method", sa.String(), nullable=True),
        sa.Column("from_account_id", sa.String(), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("to_account_id", sa.String(), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("external_ref", sa.String(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), server_default="posted", nullable=False),
        sa.Column("correction_of", sa.String(), sa.ForeignKey("transactions.id"), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
    )
    op.create_index("ix_transactions_effective_at", "transactions", ["effective_at"])
    op.create_index("ix_transactions_user_id", "transactions", ["user_id"])
    op.create_index("ix_transactions_category_id", "transactions", ["category_id"])
    op.create_index("ix_transactions_type_status", "transactions", ["transaction_type", "status"])

    op.create_table(
        "category_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rule_type", sa.String(), nullable=False),
        sa.Column("pattern", sa.String(), nullable=False),
        sa.Column("category_id", sa.String(), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Integer(), server_default="1", nullable=False),
    )


def downgrade() -> None:
    op.drop_table("category_rules")
    op.drop_index("ix_transactions_type_status", table_name="transactions")
    op.drop_index("ix_transactions_category_id", table_name="transactions")
    op.drop_index("ix_transactions_user_id", table_name="transactions")
    op.drop_index("ix_transactions_effective_at", table_name="transactions")
    op.drop_table("transactions")
    op.drop_table("budgets")
    op.drop_table("categories")
    op.drop_table("accounts")
    op.drop_table("users")
