from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from app.db.database import get_db
from app.db.models import Order
from app.schemas.order import (
    OrderSchema,
    OrderItemSchema,
    TrackingSchema,
    TrackingTimelineEvent,
    ReturnRequestSchema,
    ReturnItemSchema,
)
from app.services import auth_service, tracking_service

router = APIRouter(prefix="/checkout", tags=["checkout"])


class AdvanceStatusRequest(BaseModel):
    next_status: str | None = None


class CancelOrderRequest(BaseModel):
    customer_id: str | None = None


class ReturnRequestInput(BaseModel):
    product_id: str
    quantity: int = 1
    reason: str | None = None
    customer_id: str | None = None


def map_order_to_schema(order: Order) -> OrderSchema:
    """Helper to convert Order database model to OrderSchema Pydantic model."""
    items = [
        OrderItemSchema(
            product_id=item.product_id,
            sku=item.sku,
            name=item.name,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=item.line_total,
        )
        for item in order.items
    ]

    return OrderSchema(
        order_id=order.order_id,
        cart_id=order.cart_id,
        customer_id=order.customer_id,
        merchant_id=order.merchant_id,
        currency=order.currency,
        items=items,
        subtotal=order.subtotal,
        discount=order.discount,
        shipping=order.shipping,
        total=order.total,
        status=order.status,
        payment_status=order.payment_status,
        payment_id=order.payment_id,
        payment_method=order.payment_method,
        transaction_reference=order.transaction_reference,
        created_at=order.created_at,
        updated_at=order.updated_at,
        confirmed_at=order.confirmed_at,
        packed_at=order.packed_at,
        shipped_at=order.shipped_at,
        delivered_at=order.delivered_at,
        cancelled_at=order.cancelled_at,
    )


@router.get("/orders", response_model=list[OrderSchema])
def list_orders_endpoint(
    customer_id: str = Depends(auth_service.get_authenticated_customer_id),
    db: Session = Depends(get_db),
) -> list[OrderSchema]:
    """Retrieve history of all orders placed by the authenticated customer."""
    orders = (
        db.query(Order)
        .filter(Order.customer_id == customer_id)
        .order_by(Order.created_at.desc())
        .all()
    )
    return [map_order_to_schema(o) for o in orders]


@router.get("/order/{order_id}", response_model=OrderSchema)
def get_order_endpoint(
    order_id: str,
    customer_id: str = Depends(auth_service.get_authenticated_customer_id),
    db: Session = Depends(get_db),
) -> OrderSchema:
    """Get single order details, verifying ownership via authenticated customer."""
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=404,
            detail=f"Order with ID {order_id} not found",
        )
    if order.customer_id != customer_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied: You do not have permission to view this order",
        )
    return map_order_to_schema(order)


@router.get("/order/by-cart/{cart_id}", response_model=OrderSchema)
def get_order_by_cart_endpoint(
    cart_id: str,
    customer_id: str = Depends(auth_service.get_authenticated_customer_id),
    db: Session = Depends(get_db),
) -> OrderSchema:
    """Get single order details matching a cart ID, verifying ownership via authenticated customer."""
    order = db.query(Order).filter(Order.cart_id == cart_id).first()
    if not order:
        raise HTTPException(
            status_code=404,
            detail=f"Order for cart ID {cart_id} not found",
        )
    if order.customer_id != customer_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied: You do not have permission to view this order",
        )
    return map_order_to_schema(order)


@router.get("/order/{order_id}/tracking", response_model=TrackingSchema)
def get_order_tracking_endpoint(
    order_id: str,
    customer_id: str = Depends(auth_service.get_authenticated_customer_id),
    db: Session = Depends(get_db),
) -> TrackingSchema:
    """Retrieve fulfillment timeline and tracking information for an order."""
    try:
        tracking_info = tracking_service.get_order_tracking(order_id, db, customer_id)
        return TrackingSchema(**tracking_info)
    except tracking_service.OrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/order/{order_id}/advance-status", response_model=OrderSchema)
def advance_status_endpoint(
    order_id: str,
    req: AdvanceStatusRequest | None = None,
    customer_id: str = Depends(auth_service.get_authenticated_customer_id),
    db: Session = Depends(get_db),
) -> OrderSchema:
    """
    Advance order fulfillment state.
    Strictly enforces customer ownership so Customer B cannot advance Customer A's order.
    """
    next_status = req.next_status if req else None
    try:
        order = tracking_service.advance_order_status(
            order_id=order_id,
            next_status=next_status,
            db=db,
            customer_id=customer_id,
        )
        return map_order_to_schema(order)
    except tracking_service.OrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/order/{order_id}/cancel", response_model=OrderSchema)
def cancel_order_endpoint(
    order_id: str,
    req: CancelOrderRequest | None = None,
    customer_id: str = Depends(auth_service.get_authenticated_customer_id),
    db: Session = Depends(get_db),
) -> OrderSchema:
    """Cancel order, check ownership, restore stock inventory, and update payment status."""
    try:
        order = tracking_service.cancel_order(order_id, db, customer_id)
        return map_order_to_schema(order)
    except tracking_service.OrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/order/{order_id}/return", response_model=ReturnRequestSchema)
def return_order_endpoint(
    order_id: str,
    req: ReturnRequestInput,
    customer_id: str = Depends(auth_service.get_authenticated_customer_id),
    db: Session = Depends(get_db),
) -> ReturnRequestSchema:
    """Submit a sandbox product item return request under authenticated customer identity."""
    try:
        ret_req = tracking_service.request_return(
            order_id=order_id,
            product_id=req.product_id,
            quantity=req.quantity,
            reason=req.reason,
            db=db,
            customer_id=customer_id,
        )
        items = [
            ReturnItemSchema(
                product_id=item.product_id,
                quantity=item.quantity,
                reason=item.reason,
            )
            for item in ret_req.items
        ]
        return ReturnRequestSchema(
            return_id=ret_req.return_id,
            order_id=ret_req.order_id,
            customer_id=ret_req.customer_id,
            status=ret_req.status,
            items=items,
            created_at=ret_req.created_at,
            updated_at=ret_req.updated_at,
        )
    except tracking_service.OrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
