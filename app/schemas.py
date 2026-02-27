"""Pydantic models for request/response validation."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enumerations ──────────────────────────────────────────────────────────────

class TransactionType(str, Enum):
    expense = "expense"
    income = "income"
    transfer = "transfer"
    adjustment = "adjustment"


class PaymentMethod(str, Enum):
    cash = "cash"
    qris = "qris"
    debit = "debit"
    credit = "credit"
    bank_transfer = "bank_transfer"
    ewallet = "ewallet"
    other = "other"


class AccountType(str, Enum):
    bank = "bank"
    cash = "cash"
    ewallet = "ewallet"
    credit_card = "credit_card"
    other = "other"


class BudgetWarningSeverity(str, Enum):
    info = "info"
    warn = "warn"
    error = "error"


# ── Error schemas ─────────────────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    field: str | None = None
    issue: str | None = None
    question: str | None = None


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = []


class ErrorEnvelope(BaseModel):
    error: ErrorResponse


# ── User ──────────────────────────────────────────────────────────────────────

class UserOut(BaseModel):
    id: str
    display_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Account ───────────────────────────────────────────────────────────────────

class AccountCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=50)
    display_name: str = Field(..., min_length=1)
    type: AccountType
    currency: str = "IDR"
    owner_id: str | None = None


class AccountOut(BaseModel):
    id: str
    display_name: str
    type: str
    currency: str
    owner_id: str | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AccountBalance(BaseModel):
    account_id: str
    display_name: str
    owner_id: str | None = None
    balance: int


class AdjustRequest(BaseModel):
    amount: int
    user_id: str
    note: str | None = None


# ── Category ──────────────────────────────────────────────────────────────────

class CategoryChild(BaseModel):
    id: str
    display_name: str
    is_active: bool

    model_config = {"from_attributes": True}


class CategoryOut(BaseModel):
    id: str
    display_name: str
    parent_id: str | None = None
    is_active: bool
    children: list[CategoryChild] = []

    model_config = {"from_attributes": True}


# ── Transaction ───────────────────────────────────────────────────────────────

class TransactionCreate(BaseModel):
    effective_at: datetime | None = None
    user_id: str
    transaction_type: TransactionType
    amount: int = Field(..., gt=0)
    currency: str = "IDR"
    category_id: str | None = None
    description: str | None = None
    merchant: str | None = None
    payment_method: PaymentMethod | None = None
    from_account_id: str | None = None
    to_account_id: str | None = None
    note: str | None = None
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_type_fields(self) -> TransactionCreate:
        t = self.transaction_type
        missing: list[ErrorDetail] = []

        if t == TransactionType.expense:
            if not self.from_account_id:
                missing.append(ErrorDetail(
                    field="from_account_id",
                    question="Which account did you pay from?",
                ))
            if not self.category_id:
                missing.append(ErrorDetail(
                    field="category_id",
                    question="What category does this belong to?",
                ))
            if self.to_account_id:
                raise ValueError("to_account_id must be null for expenses")

        elif t == TransactionType.income:
            if not self.to_account_id:
                missing.append(ErrorDetail(
                    field="to_account_id",
                    question="Which account received this income?",
                ))

        elif t == TransactionType.transfer:
            if not self.from_account_id:
                missing.append(ErrorDetail(
                    field="from_account_id",
                    question="Which account are you transferring from?",
                ))
            if not self.to_account_id:
                missing.append(ErrorDetail(
                    field="to_account_id",
                    question="Which account are you transferring to?",
                ))

        if missing:
            from app.errors import NeedsClarificationError
            raise NeedsClarificationError(
                message="Missing required fields to log transaction",
                details=missing,
            )
        return self

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("amount must be a positive integer")
        return v


class TransactionOut(BaseModel):
    id: int
    created_at: datetime
    effective_at: datetime
    user_id: str
    transaction_type: str
    amount: int
    currency: str
    category_id: str | None = None
    description: str | None = None
    merchant: str | None = None
    payment_method: str | None = None
    from_account_id: str | None = None
    to_account_id: str | None = None
    note: str | None = None
    status: str
    correction_of: int | None = None
    metadata_json: dict[str, Any] | None = Field(None, alias="metadata_json")

    model_config = {"from_attributes": True, "populate_by_name": True}

    @field_validator("metadata_json", mode="before")
    @classmethod
    def parse_metadata(cls, v: Any) -> dict[str, Any] | None:
        if v is None:
            return None
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return None
        return v


class TransactionCreateResponse(BaseModel):
    transaction: TransactionOut
    balances: list[AccountBalance]
    budget_status: list[BudgetStatusItem]
    warnings: list[WarningItem]


class TransactionListResponse(BaseModel):
    transactions: list[TransactionOut]
    total: int
    limit: int
    offset: int


# ── Budget ────────────────────────────────────────────────────────────────────

class BudgetPut(BaseModel):
    limit_amount: int = Field(..., gt=0)
    scope_user_id: str | None = None


class BudgetOut(BaseModel):
    id: int
    month: str
    category_id: str
    limit_amount: int
    scope_user_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BudgetSnapshotOut(BaseModel):
    id: int
    month: str
    changed_category_id: str | None = None
    previous_amount: int | None = None
    new_amount: int | None = None
    snapshot_json: dict[str, Any] | None = None
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("snapshot_json", mode="before")
    @classmethod
    def parse_snapshot(cls, v: Any) -> dict[str, Any] | None:
        if v is None:
            return None
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return None
        return v


class BudgetStatusItem(BaseModel):
    category_id: str
    category_name: str
    month: str
    limit: int
    used: int
    remaining: int
    percent: float
    warning: str | None = None
    severity: BudgetWarningSeverity | None = None


class BudgetStatusResponse(BaseModel):
    month: str
    budgets: list[BudgetStatusItem]
    warnings: list[WarningItem]


# ── Warnings ──────────────────────────────────────────────────────────────────

class WarningItem(BaseModel):
    type: str = "budget"
    severity: BudgetWarningSeverity
    message: str


# ── Summary ───────────────────────────────────────────────────────────────────

class CategorySpend(BaseModel):
    category_id: str
    category_name: str
    total: int


class ParentCategorySpend(BaseModel):
    category_id: str
    category_name: str
    total: int
    children: list[CategorySpend]


class UserSpend(BaseModel):
    user_id: str
    display_name: str
    total: int


class DailyTotal(BaseModel):
    date: str
    total: int


class MonthlySummary(BaseModel):
    month: str
    total_expenses: int
    total_income: int
    net: int
    by_category: list[CategorySpend]
    by_parent_category: list[ParentCategorySpend]
    by_user: list[UserSpend]
    daily_totals: list[DailyTotal]
    top_merchants: list[dict[str, Any]]
    budget_status: list[BudgetStatusItem]
    warnings: list[WarningItem]


# ── Meta ──────────────────────────────────────────────────────────────────────

class MetaResponse(BaseModel):
    categories: list[CategoryOut]
    accounts: list[AccountOut]
    users: list[UserOut]
    payment_methods: list[str]
    transaction_types: list[str]
    server_time: datetime
