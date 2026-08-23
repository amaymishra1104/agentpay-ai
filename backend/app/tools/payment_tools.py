from app.db.database import SessionLocal
from app.services import checkout_service, tracking_service
from app.api.routes.checkout import map_order_to_schema
from app.db.models import Order


def checkout_cart(cart_id: str, payment_method: str = "mock_upi", customer_id: str | None = None) -> dict:
    """
    Checkout the specified cart and place the order.

    Args:
        cart_id (str): The unique identifier of the cart.
        payment_method (str): The mock payment method to use (e.g., 'mock_upi' or 'mock_card').
        customer_id (str, optional): The ID of the customer placing the order.

    Returns:
        dict: The created order details serialized as a dictionary.
    """
    with SessionLocal() as db:
        try:
            order = checkout_service.checkout_cart(
                cart_id=cart_id,
                payment_method=payment_method,
                db=db,
                customer_id=customer_id,
            )
            return map_order_to_schema(order).model_dump()
        except Exception as exc:
            raise ValueError(f"Checkout failed: {exc}")


def get_order(order_id: str | None = None, cart_id: str | None = None, customer_id: str | None = None) -> dict:
    """
    Retrieve details of an order using its order ID or cart ID.
    If no ID is supplied and the customer has multiple orders, it returns the summary list to clarify.

    Args:
        order_id (str, optional): The unique identifier of the order.
        cart_id (str, optional): The cart ID associated with the order.
        customer_id (str, optional): The ID of the customer retrieving the order.

    Returns:
        dict: The order details.
    """
    if not customer_id:
        raise ValueError("Customer ID is required.")

    with SessionLocal() as db:
        query = db.query(Order).filter(Order.customer_id == customer_id)

        if order_id:
            order = query.filter(Order.order_id == order_id).first()
            if not order:
                raise ValueError("No matching order found")
            return map_order_to_schema(order).model_dump()
        
        if cart_id:
            order = query.filter(Order.cart_id == cart_id).first()
            if not order:
                raise ValueError("No matching order found")
            return map_order_to_schema(order).model_dump()

        orders = query.order_by(Order.created_at.desc()).all()
        if not orders:
            raise ValueError("No matching order found")
        
        if len(orders) == 1:
            return map_order_to_schema(orders[0]).model_dump()

        # Multiple orders found: Return a structure to trigger LLM clarification
        return {
            "multiple_orders": True,
            "orders": [
                {
                    "order_id": o.order_id,
                    "date": o.created_at.isoformat(),
                    "total": o.total,
                    "status": o.status,
                    "items": [
                        {"name": item.name, "quantity": item.quantity}
                        for item in o.items
                    ]
                }
                for o in orders
            ]
        }


def get_order_tracking(order_id: str | None = None, customer_id: str | None = None) -> dict:
    """
    Retrieve structured tracking timeline and status for an order.
    If order_id is None, it looks for the customer's orders and resolves or clarifies.

    Args:
        order_id (str, optional): The unique identifier of the order.
        customer_id (str, optional): The ID of the customer tracking the order.

    Returns:
        dict: The tracking details or list of orders to clarify.
    """
    if not customer_id:
        raise ValueError("Customer ID is required.")

    with SessionLocal() as db:
        if not order_id:
            # Find all orders for this customer to track latest or clarify
            orders = db.query(Order).filter(Order.customer_id == customer_id).order_by(Order.created_at.desc()).all()
            if not orders:
                raise ValueError("No orders found to track.")
            if len(orders) == 1:
                order_id = orders[0].order_id
            else:
                return {
                    "multiple_orders": True,
                    "orders": [
                        {
                            "order_id": o.order_id,
                            "date": o.created_at.isoformat(),
                            "total": o.total,
                            "status": o.status,
                            "items": [{"name": item.name, "quantity": item.quantity} for item in o.items]
                        }
                        for o in orders
                    ]
                }

        try:
            return tracking_service.get_order_tracking(order_id, db, customer_id)
        except Exception as exc:
            raise ValueError(f"Tracking query failed: {exc}")


def cancel_order(order_id: str, customer_id: str | None = None) -> dict:
    """
    Cancel an order if eligible, check customer ownership, restore stock, and update payment status.

    Args:
        order_id (str): The unique identifier of the order.
        customer_id (str, optional): The ID of the customer cancelling the order.

    Returns:
        dict: The cancelled order details.
    """
    if not customer_id:
        raise ValueError("Customer ID is required.")

    with SessionLocal() as db:
        try:
            order = tracking_service.cancel_order(order_id, db, customer_id)
            return map_order_to_schema(order).model_dump()
        except Exception as exc:
            raise ValueError(f"Cancellation failed: {exc}")


def request_return(
    order_id: str,
    product_id: str,
    quantity: int = 1,
    reason: str | None = None,
    customer_id: str | None = None,
) -> dict:
    """
    Submit a sandbox return request for a delivered product item.

    Args:
        order_id (str): The unique identifier of the order.
        product_id (str): The product ID to return.
        quantity (int): The quantity to return.
        reason (str, optional): The reason for the return.
        customer_id (str, optional): The ID of the customer submitting the return.

    Returns:
        dict: The return request details.
    """
    if not customer_id:
        raise ValueError("Customer ID is required.")

    with SessionLocal() as db:
        try:
            ret_req = tracking_service.request_return(
                order_id=order_id,
                product_id=product_id,
                quantity=quantity,
                reason=reason,
                db=db,
                customer_id=customer_id,
            )
            return {
                "return_id": ret_req.return_id,
                "order_id": ret_req.order_id,
                "customer_id": ret_req.customer_id,
                "status": ret_req.status,
                "created_at": ret_req.created_at.isoformat(),
                "updated_at": ret_req.updated_at.isoformat(),
            }
        except Exception as exc:
            raise ValueError(f"Return request failed: {exc}")
