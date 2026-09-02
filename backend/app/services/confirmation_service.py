"""
Human Confirmation Gate Service.

Ensures that every checkout has an explicit, unexpired, and tamper-proof human approval
bound to the exact cart contents, total amount, and customer identity.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Cart, OrderConfirmation
from app.services import spending_limit_service


class ConfirmationError(ValueError):
    """Raised when confirmation is missing, expired, mismatched, or invalidated."""
    pass


def compute_cart_hash(cart: Cart) -> str:
    """
    Generate a deterministic SHA-256 fingerprint of the cart items, quantities, and prices.
    """
    items_repr = sorted(
        [
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price_inr": item.unit_price_inr,
            }
            for item in cart.items
        ],
        key=lambda x: x["product_id"],
    )

    data = {
        "cart_id": cart.id,
        "customer_id": cart.customer_id,
        "total_inr": cart.total_inr,
        "items": items_repr,
    }

    serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def request_cart_confirmation(
    cart: Cart,
    customer_id: str,
    db: Session,
) -> OrderConfirmation:
    """
    Validate cart, evaluate spending limits, and issue an explicit human confirmation token.
    """
    if cart.customer_id != customer_id:
        raise PermissionError("Access denied: Cart belongs to another customer")

    if not cart.items:
        raise ValueError("Cannot confirm an empty cart")

    # Recalculate cart server-side
    from app.services.cart_service import recalculate_cart
    recalculate_cart(cart)
    db.flush()

    if cart.total_inr <= 0:
        raise ValueError("Cart total must be greater than zero for confirmation")

    # Enforce spending limits before issuing confirmation
    spending_limit_service.check_transaction_limit(cart.total_inr)
    spending_limit_service.check_daily_spend_limit(customer_id, cart.total_inr, db)

    settings = get_settings()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = now + timedelta(seconds=settings.confirmation_expiry_seconds)

    cart_hash = compute_cart_hash(cart)
    confirmation_id = f"conf_{uuid.uuid4().hex[:16]}"

    confirmation = OrderConfirmation(
        confirmation_id=confirmation_id,
        cart_id=cart.id,
        customer_id=customer_id,
        cart_hash=cart_hash,
        amount_paise=cart.total_inr * 100,
        status="approved",
        expires_at=expires_at,
        created_at=now,
    )

    db.add(confirmation)
    db.commit()
    db.refresh(confirmation)

    return confirmation


def verify_order_confirmation(
    confirmation_id: str | None,
    cart: Cart,
    customer_id: str,
    db: Session,
) -> OrderConfirmation:
    """
    Verify that a valid, unexpired confirmation exists for this exact cart, amount, and customer.
    """
    if not confirmation_id:
        raise ConfirmationError(
            "Human confirmation required. Please approve checkout before placing the order."
        )

    confirmation = (
        db.query(OrderConfirmation)
        .filter(OrderConfirmation.confirmation_id == confirmation_id)
        .first()
    )

    if not confirmation:
        raise ConfirmationError(f"Confirmation '{confirmation_id}' not found.")

    if confirmation.customer_id != customer_id:
        raise ConfirmationError("Confirmation was issued to a different customer.")

    if confirmation.cart_id != cart.id:
        raise ConfirmationError("Confirmation was issued for a different cart.")

    if confirmation.status != "approved":
        raise ConfirmationError(f"Confirmation is not active (status: {confirmation.status}).")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if now > confirmation.expires_at:
        confirmation.status = "expired"
        db.commit()
        raise ConfirmationError("Confirmation has expired. Please re-confirm the order.")

    # Verify cart contents and amount have not changed since confirmation
    current_hash = compute_cart_hash(cart)
    if confirmation.cart_hash != current_hash or confirmation.amount_paise != (cart.total_inr * 100):
        confirmation.status = "invalidated"
        db.commit()
        raise ConfirmationError(
            "Cart contents or total have changed since approval. Please confirm the updated cart."
        )

    return confirmation


def mark_confirmation_used(confirmation_id: str | None, db: Session) -> None:
    """
    Mark confirmation as used once the order is created.
    """
    if not confirmation_id:
        return

    confirmation = (
        db.query(OrderConfirmation)
        .filter(OrderConfirmation.confirmation_id == confirmation_id)
        .first()
    )
    if confirmation:
        confirmation.status = "used"
        db.commit()
