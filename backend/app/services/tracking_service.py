import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.db.models import Order, OrderItem, ReturnRequest, ReturnItem
from app.services.catalog_service import increment_inventory, _load_products


class OrderNotFoundError(Exception):
    pass


def get_order_tracking(order_id: str, db: Session, customer_id: str) -> dict:
    """
    Get structured tracking details for an order, checking ownership if customer_id is provided.
    """
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise OrderNotFoundError(f"Order with ID {order_id} not found")

    if not customer_id:
        raise PermissionError("Access denied: Customer ID is required")
    if order.customer_id != customer_id:
        raise PermissionError("Access denied: Order does not belong to this customer")

    # Generate timeline
    states = [
        ("placed", "Order placed", order.created_at),
        ("confirmed", "Confirmed", order.confirmed_at),
        ("packed", "Packed", order.packed_at),
        ("shipped", "Shipped", order.shipped_at),
        ("out_for_delivery", "Out for delivery", order.delivered_at if order.status == "out_for_delivery" else None), # Out for delivery uses updated_at or shipped_at if needed, but let's map appropriately
        ("delivered", "Delivered", order.delivered_at),
    ]

    # Handle custom status mapping
    if order.status == "cancelled":
        states.append(("cancelled", "Cancelled", order.cancelled_at))

    # Build timeline events
    timeline = []
    status_idx = {
        "placed": 0,
        "confirmed": 1,
        "packed": 2,
        "shipped": 3,
        "out_for_delivery": 4,
        "delivered": 5,
        "cancelled": 6,
    }
    
    current_idx = status_idx.get(order.status, 0)
    
    for s_name, label, ts in states:
        if order.status == "cancelled":
            completed = (s_name == "placed" or s_name == "cancelled")
        else:
            if s_name == "cancelled":
                continue
            idx = status_idx.get(s_name, 0)
            completed = (idx <= current_idx)

        # Set fallback simulated timestamps for completed states if None in db
        event_ts = ts
        if completed and not event_ts:
            if s_name == "placed":
                event_ts = order.created_at
            elif s_name == "confirmed":
                event_ts = order.created_at + timedelta(minutes=15)
            elif s_name == "packed":
                event_ts = order.created_at + timedelta(hours=2)
            elif s_name == "shipped":
                event_ts = order.created_at + timedelta(hours=6)
            elif s_name == "out_for_delivery":
                event_ts = order.created_at + timedelta(days=1)
            elif s_name == "delivered":
                event_ts = order.created_at + timedelta(days=1, hours=4)
        
        timeline.append({
            "status": s_name,
            "timestamp": event_ts,
            "label": label,
            "completed": completed
        })

    # Tracking number is generated deterministically
    tracking_number = f"AP-EX-{order_id.split('_')[-1].upper()}"
    est_delivery = order.created_at + timedelta(days=3)

    return {
        "order_id": order.order_id,
        "status": order.status,
        "estimated_delivery": est_delivery.strftime("%d %b %Y"),
        "tracking_number": tracking_number,
        "carrier": "AgentPay Express",
        "timeline": timeline,
    }


def advance_order_status(
    order_id: str,
    next_status: str | None,
    db: Session,
    customer_id: str | None = None,
) -> Order:
    """
    Advance simulated order fulfillment status. If next_status is not provided, advance to the next state in sequence.
    Verifies customer ownership if customer_id is provided.
    """
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise OrderNotFoundError(f"Order with ID {order_id} not found")

    if customer_id and order.customer_id != customer_id:
        raise PermissionError("Access denied: Order does not belong to this customer")

    if order.status == "cancelled":
        raise ValueError("Cannot advance status of a cancelled order")
    if order.status == "delivered":
        raise ValueError("Cannot advance status of a delivered order")

    # Sequence of status advancement
    sequence = ["placed", "confirmed", "packed", "shipped", "out_for_delivery", "delivered"]
    
    if not next_status:
        try:
            curr_idx = sequence.index(order.status)
            next_status = sequence[curr_idx + 1]
        except (ValueError, IndexError):
            raise ValueError(f"Fulfillment sequence error at status: {order.status}")
    else:
        if next_status not in sequence and next_status != "cancelled":
            raise ValueError(f"Invalid next status state: {next_status}")

    # Set timestamps
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    order.status = next_status
    order.updated_at = now

    if next_status == "confirmed":
        order.confirmed_at = now
    elif next_status == "packed":
        if not order.confirmed_at:
            order.confirmed_at = now
        order.packed_at = now
    elif next_status == "shipped":
        if not order.confirmed_at:
            order.confirmed_at = now
        if not order.packed_at:
            order.packed_at = now
        order.shipped_at = now
    elif next_status == "out_for_delivery":
        # Out for delivery: ensure preceding steps are filled
        if not order.confirmed_at:
            order.confirmed_at = now
        if not order.packed_at:
            order.packed_at = now
        if not order.shipped_at:
            order.shipped_at = now
    elif next_status == "delivered":
        if not order.confirmed_at:
            order.confirmed_at = now
        if not order.packed_at:
            order.packed_at = now
        if not order.shipped_at:
            order.shipped_at = now
        order.delivered_at = now

    db.commit()
    return order


def cancel_order(order_id: str, db: Session, customer_id: str) -> Order:
    """
    Cancel an order if eligible, check customer ownership, restore inventory, and prevent duplicate cancellation.
    """
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise OrderNotFoundError(f"Order with ID {order_id} not found")

    if not customer_id:
        raise PermissionError("Access denied: Customer ID is required")
    if order.customer_id != customer_id:
        raise PermissionError("Access denied: Order does not belong to this customer")

    if order.status == "cancelled":
        return order  # Return gracefully if already cancelled (idempotent/duplicate cancellation rejection)

    # Cancel eligibility
    cancellable_states = {"placed", "confirmed", "packed"}
    if order.status not in cancellable_states:
        raise ValueError(f"Order is not eligible for cancellation in state: '{order.status}'. Only placed, confirmed, or packed orders are cancellable.")

    # Restoring inventory stock
    items_to_restore = {item.product_id: item.quantity for item in order.items}
    increment_inventory(items_to_restore)

    # Update states
    order.status = "cancelled"
    order.payment_status = "refunded"
    order.cancelled_at = datetime.now(timezone.utc).replace(tzinfo=None)
    order.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    db.commit()
    return order


def request_return(
    order_id: str,
    product_id: str,
    quantity: int,
    reason: str | None,
    db: Session,
    customer_id: str,
) -> ReturnRequest:
    """
    Create a sandbox return request for a delivered order.
    """
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise OrderNotFoundError(f"Order with ID {order_id} not found")

    if not customer_id:
        raise PermissionError("Access denied: Customer ID is required")
    if order.customer_id != customer_id:
        raise PermissionError("Access denied: Order does not belong to this customer")

    if order.status not in ("delivered", "returned"):
        raise ValueError("Only delivered orders are eligible for return requests.")

    # Verify matching item and quantity in order
    matching_item = None
    for item in order.items:
        if item.product_id == product_id:
            matching_item = item
            break

    if not matching_item:
        raise ValueError(f"Product {product_id} is not part of this order.")

    if quantity <= 0 or quantity > matching_item.quantity:
        raise ValueError(f"Invalid quantity requested for return. Maximum is {matching_item.quantity}.")

    # Load product from catalog to check return policy
    catalog = _load_products()
    catalog_product = catalog.get(product_id)
    if catalog_product:
        policy = catalog_product.return_policy
        if policy:
            eligible = getattr(policy, "eligible", True)
            if not eligible:
                raise ValueError(f"Product {catalog_product.name} is not eligible for returns.")
            
            # Check return window (fallback to 7 days if not defined)
            policy_days = getattr(policy, "days", 7) or 7
            delivery_date = order.delivered_at or order.created_at
            if datetime.now(timezone.utc).replace(tzinfo=None) > delivery_date + timedelta(days=policy_days):
                raise ValueError(f"The return period of {policy_days} days for this product has expired.")

    # Prevent duplicate returns on the same order item
    existing_return = db.query(ReturnRequest).filter(ReturnRequest.order_id == order_id).first()
    if existing_return:
        for item in existing_return.items:
            if item.product_id == product_id:
                raise ValueError("A return request has already been submitted for this product.")

    # Create ReturnRequest
    return_id = f"ret_{uuid.uuid4().hex[:12]}"
    ret_req = ReturnRequest(
        return_id=return_id,
        order_id=order_id,
        customer_id=order.customer_id,
        status="requested",
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Create ReturnItem
    ret_item = ReturnItem(
        return_id=return_id,
        product_id=product_id,
        quantity=quantity,
        reason=reason,
    )
    ret_req.items.append(ret_item)
    db.add(ret_req)

    # Update order state optionally
    order.status = "returned" if order.status != "returned" else order.status
    order.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    db.commit()
    db.refresh(ret_req)
    return ret_req
