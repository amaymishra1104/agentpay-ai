import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.cart import (
    CartSchema,
    CartCreateRequest,
    CartItemAddRequest,
    CartItemUpdateRequest,
    CartValidationResponse,
    CartItemSchema,
    AppliedOfferSchema,
)
from app.services import cart_service
from app.services.catalog_service import ProductNotFoundError
from app.schemas.order import OrderSchema, CheckoutRequest
from app.services import checkout_service
from app.api.routes.checkout import map_order_to_schema

router = APIRouter(prefix="/cart", tags=["cart"])


def map_cart_to_schema(cart) -> CartSchema:
    """Helper to convert Cart database model to CartSchema Pydantic model."""
    items = [
        CartItemSchema(
            product_id=item.product_id,
            sku=item.sku,
            name=item.name,
            unit_price_inr=item.unit_price_inr,
            quantity=item.quantity,
            line_total_inr=item.line_total_inr,
            available=item.available,
            inventory_checked=item.inventory_checked,
        )
        for item in cart.items
    ]

    try:
        offers = json.loads(cart.applied_offers_json)
    except Exception:
        offers = []

    applied_offers = [AppliedOfferSchema(**o) for o in offers]

    return CartSchema(
        cart_id=cart.id,
        merchant_id=cart.merchant_id,
        customer_id=cart.customer_id,
        currency=cart.currency,
        items=items,
        subtotal_inr=cart.subtotal_inr,
        discount_inr=cart.discount_inr,
        shipping_inr=cart.shipping_inr,
        total_inr=cart.total_inr,
        applied_offers=applied_offers,
        status=cart.status,
        created_at=cart.created_at,
        updated_at=cart.updated_at,
    )


@router.post("", response_model=CartSchema, status_code=status.HTTP_201_CREATED)
def create_cart_endpoint(req: CartCreateRequest, db: Session = Depends(get_db)) -> CartSchema:
    try:
        cart = cart_service.create_cart(
            merchant_id=req.merchant_id,
            customer_id=req.customer_id,
            db=db,
        )
        return map_cart_to_schema(cart)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{cart_id}", response_model=CartSchema)
def get_cart_endpoint(
    cart_id: str,
    customer_id: str,
    db: Session = Depends(get_db),
) -> CartSchema:
    try:
        cart = cart_service.get_cart(cart_id=cart_id, db=db, customer_id=customer_id)
        if not cart:
            raise HTTPException(
                status_code=404,
                detail=f"Cart with ID {cart_id} not found",
            )
        return map_cart_to_schema(cart)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/{cart_id}/items", response_model=CartSchema)
def add_item_endpoint(
    cart_id: str,
    req: CartItemAddRequest,
    customer_id: str,
    db: Session = Depends(get_db),
) -> CartSchema:
    try:
        cart = cart_service.add_item_to_cart(
            cart_id=cart_id,
            product_id=req.product_id,
            quantity=req.quantity,
            db=db,
            customer_id=customer_id,
        )
        return map_cart_to_schema(cart)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except cart_service.CartNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        cart_service.MerchantMismatchError,
        cart_service.InsufficientInventoryError,
        cart_service.ProductUnavailableError,
        ValueError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{cart_id}/items/{product_id}", response_model=CartSchema)
def update_item_endpoint(
    cart_id: str,
    product_id: str,
    req: CartItemUpdateRequest,
    customer_id: str,
    db: Session = Depends(get_db),
) -> CartSchema:
    try:
        cart = cart_service.update_item_quantity(
            cart_id=cart_id,
            product_id=product_id,
            quantity=req.quantity,
            db=db,
            customer_id=customer_id,
        )
        return map_cart_to_schema(cart)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except cart_service.CartNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        cart_service.InsufficientInventoryError,
        ValueError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{cart_id}/items/{product_id}", response_model=CartSchema)
def remove_item_endpoint(
    cart_id: str,
    product_id: str,
    customer_id: str,
    db: Session = Depends(get_db),
) -> CartSchema:
    try:
        cart = cart_service.remove_item_from_cart(
            cart_id=cart_id,
            product_id=product_id,
            db=db,
            customer_id=customer_id,
        )
        return map_cart_to_schema(cart)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except cart_service.CartNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{cart_id}", response_model=CartSchema)
def clear_cart_endpoint(
    cart_id: str,
    customer_id: str,
    db: Session = Depends(get_db),
) -> CartSchema:
    try:
        cart = cart_service.clear_cart(cart_id=cart_id, db=db, customer_id=customer_id)
        return map_cart_to_schema(cart)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except cart_service.CartNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{cart_id}/validate", response_model=CartValidationResponse)
def validate_cart_endpoint(
    cart_id: str,
    customer_id: str,
    db: Session = Depends(get_db),
) -> CartValidationResponse:
    try:
        res = cart_service.validate_cart(cart_id=cart_id, db=db, customer_id=customer_id)
        return CartValidationResponse(**res)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except cart_service.CartNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{cart_id}/checkout", response_model=OrderSchema)
def checkout_cart_endpoint(
    cart_id: str,
    req: CheckoutRequest,
    db: Session = Depends(get_db),
) -> OrderSchema:
    try:
        order = checkout_service.checkout_cart(
            cart_id=cart_id,
            payment_method=req.payment_method,
            db=db,
            customer_id=req.customer_id,
        )
        return map_order_to_schema(order)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except cart_service.CartNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

