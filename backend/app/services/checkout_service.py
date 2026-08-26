import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import Order, OrderItem, AgentSession
from app.services import cart_service, razorpay_service
from app.services.catalog_service import (
    decrement_inventory,
    increment_inventory,
)


def checkout_cart(
    cart_id: str,
    payment_method: str,
    db: Session,
    customer_id: str | None = None,
    merchant_id: str | None = None,
    razorpay_order_id: str | None = None,
    razorpay_payment_id: str | None = None,
    razorpay_signature: str | None = None,
) -> Order:
    """
    Checkout the cart, deduct inventory, record deterministic payment
    details, and create the order.

    For Razorpay payments:
    - Cryptographic signature is verified server-side before any inventory mutation.
    - Idempotency ensures duplicate callbacks return the existing order.

    Inventory is decremented before the database transaction is committed.
    If database processing fails, the database transaction is rolled back
    and inventory is restored.

    Returns the created/existing order.
    """

    # 1. Retrieve cart with ownership check.
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

    # 2. Idempotency check: Return existing order if cart or payment was already finalized.
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

    # 3. Recalculate cart first.
    cart_service.recalculate_cart(cart)
    db.flush()

    # 4. Validate cart.
    val_res = cart_service.validate_cart(
        cart_id=stable_cart_id,
        db=db,
        customer_id=customer_id,
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

    # 5. Server-side payment verification for Razorpay.
    if payment_method == "razorpay":
        if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
            raise ValueError(
                "Razorpay payment verification requires razorpay_order_id, razorpay_payment_id, and razorpay_signature."
            )

        is_valid = razorpay_service.verify_payment_signature(
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature,
        )
        if not is_valid:
            raise ValueError("Invalid Razorpay payment signature.")

        payment_id = razorpay_payment_id
        transaction_ref = razorpay_order_id
    else:
        # Mock payment identifiers
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        transaction_ref = f"txn_{uuid.uuid4().hex[:12]}"

    # 6. Collect inventory changes.
    items_to_dec = {
        item.product_id: item.quantity
        for item in cart.items
    }

    # 7. Safely decrement inventory under cross-process file lock.
    decrement_inventory(items_to_dec)

    try:
        # 8. Create order.
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
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(order)

        # 9. Create order items using price snapshots.
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

        # 10. Mark cart as checked out.
        cart.status = "checked_out"
        cart.updated_at = datetime.utcnow()

        # 11. Clear cart references from active agent sessions.
        sessions = (
            db.query(AgentSession)
            .filter(AgentSession.cart_id == stable_cart_id)
            .all()
        )

        for session in sessions:
            session.cart_id = None
            session.updated_at = datetime.utcnow()

        # 12. Commit the database transaction.
        db.commit()
        db.refresh(order)

        return order

    except Exception:
        # Database state must be rolled back first.
        db.rollback()

        # Refresh the cart after rollback so its attributes are loaded again.
        try:
            db.refresh(cart)
        except Exception:
            pass

        # Restore inventory after the database rollback.
        try:
            increment_inventory(items_to_dec)
        except Exception:
            # Preserve the original database exception.
            pass

        raise