import uuid
from datetime import datetime
from sqlalchemy.orm import Session

from app.db.models import Order, OrderItem, AgentSession
from app.services import cart_service
from app.services.catalog_service import decrement_inventory, increment_inventory


def checkout_cart(
    cart_id: str,
    payment_method: str,
    db: Session,
    customer_id: str | None = None,
    merchant_id: str | None = None,
) -> Order:
    """
    Checkout the cart, deduct inventory, record deterministic payment details, and create the order.
    Returns the created/existing order.
    """
    # 1. Retrieve cart with ownership check
    cart = cart_service.get_cart(cart_id, db, customer_id=customer_id)
    if not cart:
        raise cart_service.CartNotFoundError(f"Cart {cart_id} not found")

    # 2. Idempotency check: If an order already exists for this cart, return it.
    existing_order = db.query(Order).filter(Order.cart_id == cart_id).first()
    if existing_order:
        return existing_order

    # 3. Recalculate cart first
    cart_service.recalculate_cart(cart)
    db.flush()

    # 4. Validate cart
    val_res = cart_service.validate_cart(
        cart_id=cart_id,
        db=db,
        customer_id=customer_id,
        merchant_id=merchant_id,
    )
    if not val_res["valid"]:
        issues_str = ", ".join([issue["message"] for issue in val_res["issues"]])
        raise ValueError(f"Cart validation failed: {issues_str}")

    # 5. Collect items to decrement
    items_to_dec = {item.product_id: item.quantity for item in cart.items}

    # 6. Safely decrement inventory in the JSON file
    decrement_inventory(items_to_dec)

    try:
        # 7. Generate mock payment receipt/reference
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        transaction_ref = f"txn_{uuid.uuid4().hex[:12]}"

        # 8. Create Order
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

        # 9. Create OrderItems using price snapshots from CartItem
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

        # 10. Mark cart as checked out
        cart.status = "checked_out"
        cart.updated_at = datetime.utcnow()

        # 11. Clear cart reference in active agent sessions
        sessions = db.query(AgentSession).filter(AgentSession.cart_id == cart_id).all()
        for session in sessions:
            session.cart_id = None
            session.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(order)
        return order
    except Exception as exc:
        db.rollback()
        # Revert inventory decrement
        try:
            increment_inventory(items_to_dec)
        except Exception:
            pass
        raise exc
