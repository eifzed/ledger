"""Restructure categories into parent/child hierarchy.

Revision ID: 002
Revises: 001
Create Date: 2026-02-24

Data-only migration: no schema changes needed since parent_id column
already exists on the categories table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

HIERARCHY: dict[tuple[str, str], list[tuple[str, str]]] = {
    ("food", "Food"): [
        ("groceries", "Groceries"),
        ("eating_out", "Eating Out"),
        ("coffee", "Coffee"),
        ("delivery", "Delivery"),
    ],
    ("transport", "Transport"): [
        ("fuel", "Fuel"),
        ("parking", "Parking"),
        ("toll", "Toll"),
        ("public_transport", "Public Transport"),
        ("ride_hailing", "Ride Hailing"),
    ],
    ("bills", "Bills"): [
        ("electricity", "Electricity"),
        ("water", "Water"),
        ("internet", "Internet"),
        ("phone", "Phone"),
        ("gas_lpg", "Gas LPG"),
        ("subscriptions", "Subscriptions"),
    ],
    ("housing", "Housing"): [
        ("rent", "Rent"),
        ("furnishing", "Furnishing"),
        ("maintenance", "Maintenance"),
        ("cleaning", "Cleaning"),
    ],
    ("shopping", "Shopping"): [
        ("clothing", "Clothing"),
        ("electronics", "Electronics"),
        ("household_items", "Household Items"),
    ],
    ("health", "Health"): [
        ("medical", "Medical"),
        ("pharmacy", "Pharmacy"),
        ("gym", "Gym"),
    ],
    ("entertainment", "Entertainment"): [
        ("movies", "Movies"),
        ("games", "Games"),
        ("hobbies", "Hobbies"),
        ("outings", "Outings"),
    ],
    ("vehicle", "Vehicle"): [
        ("car_service", "Car Service"),
        ("car_insurance", "Car Insurance"),
        ("car_tax", "Car Tax"),
    ],
    ("personal", "Personal"): [
        ("haircut", "Haircut"),
        ("skincare", "Skincare"),
    ],
    ("education", "Education"): [
        ("courses", "Courses"),
        ("books", "Books"),
    ],
    ("gifts", "Gifts & Donations"): [
        ("gifts_items", "Gifts"),
        ("charity", "Charity"),
        ("zakat", "Zakat"),
    ],
    ("investment", "Investment"): [
        ("gold", "Gold"),
        ("stock", "Stock"),
        ("bond", "Bond"),
        ("saving", "Saving"),
    ],
    ("income", "Income"): [
        ("salary", "Salary"),
        ("freelance", "Freelance"),
        ("other_income", "Other Income"),
    ],
}


def upgrade() -> None:
    conn = op.get_bind()
    categories = sa.table(
        "categories",
        sa.column("id", sa.String),
        sa.column("display_name", sa.String),
        sa.column("parent_id", sa.String),
        sa.column("is_active", sa.Integer),
    )

    existing = {row.id for row in conn.execute(sa.select(categories.c.id))}

    for (parent_id, parent_name), children in HIERARCHY.items():
        if parent_id not in existing:
            conn.execute(categories.insert().values(
                id=parent_id, display_name=parent_name, parent_id=None, is_active=1,
            ))
            existing.add(parent_id)
        else:
            conn.execute(
                categories.update()
                .where(categories.c.id == parent_id)
                .values(parent_id=None, display_name=parent_name)
            )

        for child_id, child_name in children:
            if child_id not in existing:
                conn.execute(categories.insert().values(
                    id=child_id, display_name=child_name, parent_id=parent_id, is_active=1,
                ))
                existing.add(child_id)
            else:
                conn.execute(
                    categories.update()
                    .where(categories.c.id == child_id)
                    .values(parent_id=parent_id, display_name=child_name)
                )

    new_ids = set()
    for (pid, _), children in HIERARCHY.items():
        new_ids.add(pid)
        for cid, _ in children:
            new_ids.add(cid)
    orphans = existing - new_ids
    if orphans:
        conn.execute(
            categories.update()
            .where(categories.c.id.in_(orphans))
            .values(is_active=0)
        )


def downgrade() -> None:
    conn = op.get_bind()
    categories = sa.table(
        "categories",
        sa.column("id", sa.String),
        sa.column("parent_id", sa.String),
        sa.column("is_active", sa.Integer),
    )
    conn.execute(
        categories.update().values(parent_id=None, is_active=1)
    )
