"""Seed default data (users, categories, accounts) on first run."""

from sqlalchemy.orm import Session

from app.models import Account, Category, User

CATEGORY_HIERARCHY: dict[tuple[str, str], list[tuple[str, str]]] = {
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


def seed_defaults(db: Session) -> None:
    _seed_users(db)
    _seed_categories(db)
    _seed_accounts(db)
    db.commit()


def _seed_users(db: Session) -> None:
    defaults = [
        ("fazrin", "Fazrin"),
        ("wife", "Wife"),
    ]
    for uid, name in defaults:
        if not db.query(User).filter(User.id == uid).first():
            db.add(User(id=uid, display_name=name))


def _seed_categories(db: Session) -> None:
    for (parent_id, parent_name), children in CATEGORY_HIERARCHY.items():
        if not db.query(Category).filter(Category.id == parent_id).first():
            db.add(Category(id=parent_id, display_name=parent_name, parent_id=None))
        db.flush()
        for child_id, child_name in children:
            if not db.query(Category).filter(Category.id == child_id).first():
                db.add(Category(id=child_id, display_name=child_name, parent_id=parent_id))


def _seed_accounts(db: Session) -> None:
    defaults = [
        ("BCA", "BCA", "bank"),
        ("JAGO", "Jago", "bank"),
        ("CASH", "Cash", "cash"),
        ("GOPAY", "GoPay", "ewallet"),
        ("OVO", "OVO", "ewallet"),
    ]
    for aid, name, atype in defaults:
        if not db.query(Account).filter(Account.id == aid).first():
            db.add(Account(id=aid, display_name=name, type=atype))
