"""
Checkout Service with End-to-End Payment Hardening.

Checkout Pipeline:
1. Server-authoritative customer identity and tenant ownership verification.
2. Database-level idempotency to prevent duplicate orders or double-decrements.
3. Authoritative server-side cart recalculation and validation.
4. Human confirmation gate check (if provided or enforced).
5. Server-side Per-Transaction and Daily spending limit checks.
6. Cryptographic Razorpay signature & PaymentOrder (cart/amount/customer) binding.
7. Atomic cross-process inventory decrement under lock.
8. Database order creation with IntegrityError recovery.
9. Final state transitions and cleanup.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AgentSession, Order, OrderItem
from app.services import (
    cart_service,
    confirmation_service,
    razorpay_service,
    spending_limit_service,
)
from app.services.catalog_service import (
    decrement_inventory,
    increment_inventory,
)

logger = logging.getLogger("agentpay")


def checkout_cart(
    cart_id: str,
    payment_method: str,
    db: Session,
    customer_id: str | None = None,
    merchant_id: str | None = None,
    razorpay_order_id: str | None = None,
    razorpay_payment_id: str | None = None,
    razorpay_signature: str | None = None,
    confirmation_id: str | None = None,
) -> Order:
    """
    Checkout the cart with full security & payment hardening guarantees.
    """

    # 1. Retrieve cart with strict tenant ownership check.
    cart = cart_service.get_cart(
        cart_id,
        db,
        customer_id=customer_id,
    )

    if not cart:
        raise cart_service.CartNotFoundError(
            f"Cart {cart_id} not found"
        )

    # Keep a stable identifier because SQLAlchemy rollback can expire ORM attributes.
    stable_cart_id = cart.id
    effective_customer_id = customer_id or cart.customer_id

    # 2. Database-level idempotency pre-check: Return existing order if already finalized.
    if razorpay_payment_id:
        existing_order = (
            db.query(Order)
            .filter(
                (Order.cart_id == stable_cart_id)
                | (Order.payment_id == razorpay_payment_id)
            )
            .first()
        )
    else:
        existing_order = (
            db.query(Order)
            .filter(Order.cart_id == stable_cart_id)
            .first()
        )

    if existing_order:
        return existing_order

    # 3. Recalculate cart server-side.
    cart_service.recalculate_cart(cart)
    db.flush()

    # 4. Validate cart contents and stock availability.
    val_res = cart_service.validate_cart(
        cart_id=stable_cart_id,
        db=db,
        customer_id=effective_customer_id,
        merchant_id=merchant_id,
    )

    if not val_res["valid"]:
        issues_str = ", ".join(
            issue["message"]
            for issue in val_res["issues"]
        )
        raise ValueError(
            f"Cart validation failed: {issues_str}"
        )

    # 5. Human Confirmation Gate Check (if confirmation_id is provided)
    if confirmation_id:
        confirmation_service.verify_order_confirmation(
            confirmation_id=confirmation_id,
            cart=cart,
            customer_id=effective_customer_id,
            db=db,
        )

    # 6. Spending Limits Checks (Per-Transaction & Daily Limits)
    spending_limit_service.check_transaction_limit(cart.total_inr)
    spending_limit_service.check_daily_spend_limit(effective_customer_id, cart.total_inr, db)

    # 7. Payment Verification and Binding
    if payment_method == "razorpay":
        if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
            raise ValueError(
                "Razorpay payment verification requires razorpay_order_id, razorpay_payment_id, and razorpay_signature."
            )

        # Complete PaymentOrder binding verification
        razorpay_service.verify_and_bind_payment_order(
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature,
            cart=cart,
            customer_id=effective_customer_id,
            db=db,
        )

        payment_id = razorpay_payment_id
        transaction_ref = razorpay_order_id
    else:
        # Mock payment identifiers
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        transaction_ref = f"txn_{uuid.uuid4().hex[:12]}"

    # 8. Collect inventory changes.
    items_to_dec = {
        item.product_id: item.quantity
        for item in cart.items
    }

    # 9. Safely decrement inventory under cross-process file lock.
    decrement_inventory(items_to_dec)

    try:
        # 10. Create order record.
        order_id = f"ord_{uuid.uuid4().hex[:12]}"

        order = Order(
            order_id=order_id,
            cart_id=cart.id,
            customer_id=cart.customer_id,
            merchant_id=cart.merchant_id,
            currency=cart.currency,
            subtotal=cart.subtotal_inr,
            discount=cart.discount_inr,
            shipping=cart.shipping_inr,
            total=cart.total_inr,
            status="placed",
            payment_status="successful",
            payment_id=payment_id,
            payment_method=payment_method,
            transaction_reference=transaction_ref,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )

        db.add(order)

        # 11. Create order items using authoritative price snapshots.
        for item in cart.items:
            order_item = OrderItem(
                order_id=order_id,
                product_id=item.product_id,
                sku=item.sku,
                name=item.name,
                quantity=item.quantity,
                unit_price=item.unit_price_inr,
                line_total=item.line_total_inr,
            )
            db.add(order_item)

        # 12. Mark cart as checked out.
        cart.status = "checked_out"
        cart.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # 13. Clear cart references from active agent sessions.
        sessions = (
            db.query(AgentSession)
            .filter(AgentSession.cart_id == stable_cart_id)
            .all()
        )

        for session in sessions:
            session.cart_id = None
            session.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # 14. Mark confirmation as used if present
        if confirmation_id:
            confirmation_service.mark_confirmation_used(confirmation_id, db)

        # 15. Commit database transaction.
        db.commit()
        db.refresh(order)

        return order

    except IntegrityError:
        # Concurrent duplicate checkout attempt hit unique database constraint.
        db.rollback()
        # Restore inventory
        try:
            increment_inventory(items_to_dec)
        except Exception:
            pass

        # Retrieve and return the already committed order
        existing = (
            db.query(Order)
            .filter(
                (Order.cart_id == stable_cart_id)
                | (Order.payment_id == payment_id)
            )
            .first()
        )
        if existing:
            return existing
        raise

    except Exception:
        # General rollback on unexpected error
        db.rollback()

        try:
            db.refresh(cart)
        except Exception:
            pass

        # Restore inventory
        try:
            increment_inventory(items_to_dec)
        except Exception:
            pass

        raise