"""
Spending Limit Enforcement Service.

Enforces server-side per-transaction limits and daily spending limits.
All monetary calculations are authoritative, derived from database-persisted orders.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Order


class SpendingLimitExceededError(ValueError):
    """Raised when a transaction exceeds the per-transaction or daily spending limit."""
    pass


def check_transaction_limit(amount_inr: int) -> None:
    """
    Verify that the given transaction amount (in INR) does not exceed the configured maximum.
    """
    if amount_inr <= 0:
        raise ValueError(f"Invalid transaction amount: {amount_inr}. Must be > 0.")

    settings = get_settings()
    max_limit = settings.max_transaction_inr

    if max_limit > 0 and amount_inr > max_limit:
        raise SpendingLimitExceededError(
            f"Transaction amount of ₹{amount_inr:,} exceeds the maximum allowed transaction limit of ₹{max_limit:,}."
        )


def get_customer_daily_spend_paise(customer_id: str, db: Session) -> int:
    """
    Calculate the total spent by a customer for the current UTC day in paise.
    Excludes cancelled orders and refunded payments.
    """
    now = datetime.now(timezone.utc)
    start_of_day = datetime.combine(now.date(), time.min)

    # Query sum of total (stored in INR) for authoritative placed/confirmed/packed/shipped/delivered orders
    result = (
        db.query(func.coalesce(func.sum(Order.total), 0))
        .filter(
            Order.customer_id == customer_id,
            Order.created_at >= start_of_day,
            Order.status != "cancelled",
            Order.payment_status != "refunded",
        )
        .scalar()
    )

    total_inr = int(result or 0)
    return total_inr * 100


def get_customer_daily_spend_inr(customer_id: str, db: Session) -> int:
    """
    Returns customer daily spend in INR.
    """
    return get_customer_daily_spend_paise(customer_id, db) // 100


def check_daily_spend_limit(customer_id: str, amount_inr: int, db: Session) -> None:
    """
    Verify that adding amount_inr to the customer's current daily spend does not exceed
    the configured daily spending limit.
    """
    if amount_inr <= 0:
        raise ValueError(f"Invalid transaction amount: {amount_inr}. Must be > 0.")

    settings = get_settings()
    daily_limit = settings.daily_spend_limit_inr

    if daily_limit <= 0:
        return

    current_spend_paise = get_customer_daily_spend_paise(customer_id, db)
    current_spend_inr = current_spend_paise // 100
    incoming_paise = amount_inr * 100
    daily_limit_paise = daily_limit * 100

    if current_spend_paise + incoming_paise > daily_limit_paise:
        raise SpendingLimitExceededError(
            f"Transaction of ₹{amount_inr:,} exceeds your daily spending limit of ₹{daily_limit:,}. "
            f"Current daily spending: ₹{current_spend_inr:,}."
        )
