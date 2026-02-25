"""SQLAlchemy ORM models matching the spec schema."""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    display_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    transactions = relationship("Transaction", back_populates="user")


class Account(Base):
    __tablename__ = "accounts"

    id = Column(String, primary_key=True)
    display_name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # bank, cash, ewallet
    currency = Column(String, default="IDR", nullable=False)
    is_active = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)


class Category(Base):
    __tablename__ = "categories"

    id = Column(String, primary_key=True)
    display_name = Column(String, nullable=False)
    parent_id = Column(String, ForeignKey("categories.id"), nullable=True)
    is_active = Column(Integer, default=1, nullable=False)

    parent = relationship("Category", remote_side=[id])


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    month = Column(String, nullable=False)  # YYYY-MM
    category_id = Column(String, ForeignKey("categories.id"), nullable=False)
    limit_amount = Column(Integer, nullable=False)
    scope_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    category = relationship("Category")
    scope_user = relationship("User")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    effective_at = Column(DateTime, nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    transaction_type = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)
    currency = Column(String, default="IDR", nullable=False)
    category_id = Column(String, ForeignKey("categories.id"), nullable=True)
    description = Column(Text, nullable=True)
    merchant = Column(String, nullable=True)
    payment_method = Column(String, nullable=True)
    from_account_id = Column(String, ForeignKey("accounts.id"), nullable=True)
    to_account_id = Column(String, ForeignKey("accounts.id"), nullable=True)
    external_ref = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    status = Column(String, default="posted", nullable=False)
    correction_of = Column(String, ForeignKey("transactions.id"), nullable=True)
    metadata_json = Column(Text, nullable=True)

    user = relationship("User", back_populates="transactions")
    category = relationship("Category")
    from_account = relationship("Account", foreign_keys=[from_account_id])
    to_account = relationship("Account", foreign_keys=[to_account_id])
    original = relationship("Transaction", remote_side=[id], foreign_keys=[correction_of])


class BudgetSnapshot(Base):
    __tablename__ = "budget_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    month = Column(String, nullable=False)
    changed_category_id = Column(String, nullable=True)
    previous_amount = Column(Integer, nullable=True)
    new_amount = Column(Integer, nullable=True)
    snapshot_json = Column(Text, nullable=False)  # full budget state as JSON
    source = Column(String, default="api", nullable=False)  # "api" or "dashboard"
    created_at = Column(DateTime, default=func.now(), nullable=False)


class CategoryRule(Base):
    __tablename__ = "category_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_type = Column(String, nullable=False)  # keyword, merchant
    pattern = Column(String, nullable=False)
    category_id = Column(String, ForeignKey("categories.id"), nullable=False)
    priority = Column(Integer, default=0, nullable=False)
    is_active = Column(Integer, default=1, nullable=False)

    category = relationship("Category")
