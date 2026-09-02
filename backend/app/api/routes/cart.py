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
    ConfirmationResponseSchema,
)
from app.schemas.payment import (
    CreatePaymentOrderRequest,
    CreatePaymentOrderResponse,
)
from app.schemas.order import OrderSchema, CheckoutRequest
from app.services import (
    auth_service,
    cart_service,
    checkout_service,
    confirmation_service,
    razorpay_service,
    spending_limit_service,
)
from app.services.catalog_service import ProductNotFoundError
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
def create_cart_endpoint(
    req: CartCreateRequest,
    customer_id: str = Depends(auth_service.get_authenticated_customer_id),
    db: Session = Depends(get_db),
) -> CartSchema:
    try:
        cart = cart_service.create_cart(
            merchant_id=req.merchant_id,
            customer_id=customer_id,
            db=db,
        )
        return map_cart_to_schema(cart)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{cart_id}", response_model=CartSchema)
def get_cart_endpoint(
    cart_id: str,
    customer_id: str = Depends(auth_service.get_authenticated_customer_id),
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
    customer_id: str = Depends(auth_service.get_authenticated_customer_id),
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
    customer_id: str = Depends(auth_service.get_authenticated_customer_id),
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
    customer_id: str = Depends(auth_service.get_authenticated_customer_id),
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
    customer_id: str = Depends(auth_service.get_authenticated_customer_id),
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
    customer_id: str = Depends(auth_service.get_authenticated_customer_id),
    db: Session = Depends(get_db),
) -> CartValidationResponse:
    try:
        res = cart_service.validate_cart(cart_id=cart_id, db=db, customer_id=customer_id)
        return CartValidationResponse(**res)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except cart_service.CartNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{cart_id}/confirm", response_model=ConfirmationResponseSchema)
def request_cart_confirmation_endpoint(
    cart_id: str,
    customer_id: str = Depends(auth_service.get_authenticated_customer_id),
    db: Session = Depends(get_db),
) -> ConfirmationResponseSchema:
    """
    Issue an explicit, time-limited Human Confirmation Token bound to the current cart,
    amount, and authenticated customer identity.
    """
    try:
        cart = cart_service.get_cart(cart_id, db, customer_id=customer_id)
        if not cart:
            raise cart_service.CartNotFoundError(f"Cart {cart_id} not found")

        confirmation = confirmation_service.request_cart_confirmation(
            cart=cart,
            customer_id=customer_id,
            db=db,
        )

        return ConfirmationResponseSchema(
            confirmation_id=confirmation.confirmation_id,
            cart_id=confirmation.cart_id,
            customer_id=confirmation.customer_id,
            amount_inr=confirmation.amount_paise // 100,
            amount_paise=confirmation.amount_paise,
            cart_hash=confirmation.cart_hash,
            status=confirmation.status,
            expires_at=confirmation.expires_at,
            created_at=confirmation.created_at,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except cart_service.CartNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, spending_limit_service.SpendingLimitExceededError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{cart_id}/payment/create-order", response_model=CreatePaymentOrderResponse)
def create_payment_order_endpoint(
    cart_id: str,
    req: CreatePaymentOrderRequest | None = None,
    customer_id: str = Depends(auth_service.get_authenticated_customer_id),
    db: Session = Depends(get_db),
) -> CreatePaymentOrderResponse:
    """
    Validate the cart and create an authoritative Razorpay test-mode order.
    Binds the Razorpay order to the cart, customer, and exact amount in SQLite.
    """
    try:
        cart = cart_service.get_cart(cart_id, db, customer_id=customer_id)
        if not cart:
            raise cart_service.CartNotFoundError(f"Cart {cart_id} not found")

        # Recalculate and validate cart
        cart_service.recalculate_cart(cart)
        db.flush()

        val_res = cart_service.validate_cart(
            cart_id=cart.id,
            db=db,
            customer_id=customer_id,
        )
        if not val_res["valid"]:
            issues_str = ", ".join(issue["message"] for issue in val_res["issues"])
            raise ValueError(f"Cart validation failed: {issues_str}")

        if cart.total_inr <= 0:
            raise ValueError("Cart total must be greater than zero for payment.")

        # Enforce spending limits
        spending_limit_service.check_transaction_limit(cart.total_inr)
        spending_limit_service.check_daily_spend_limit(customer_id, cart.total_inr, db)

        rzp_order = razorpay_service.create_razorpay_order(
            amount_inr=cart.total_inr,
            currency=cart.currency,
            receipt=f"rcpt_{cart.id[:30]}",
            notes={
                "cart_id": cart.id,
                "customer_id": customer_id,
                "merchant_id": cart.merchant_id,
            },
            db=db,
            cart_id=cart.id,
            customer_id=customer_id,
        )

        return CreatePaymentOrderResponse(
            razorpay_order_id=rzp_order["razorpay_order_id"],
            amount_paise=rzp_order["amount_paise"],
            currency=rzp_order["currency"],
            receipt=rzp_order.get("receipt"),
            key_id=rzp_order.get("key_id"),
            cart_id=cart.id,
            total_inr=cart.total_inr,
            mode=rzp_order["mode"],
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except cart_service.CartNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        ValueError,
        spending_limit_service.SpendingLimitExceededError,
        razorpay_service.RazorpayServiceError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{cart_id}/checkout", response_model=OrderSchema)
def checkout_cart_endpoint(
    cart_id: str,
    req: CheckoutRequest,
    customer_id: str = Depends(auth_service.get_authenticated_customer_id),
    db: Session = Depends(get_db),
) -> OrderSchema:
    """
    Finalize cart checkout under server-authoritative customer identity.
    """
    try:
        order = checkout_service.checkout_cart(
            cart_id=cart_id,
            payment_method=req.payment_method,
            db=db,
            customer_id=customer_id,
            razorpay_order_id=req.razorpay_order_id,
            razorpay_payment_id=req.razorpay_payment_id,
            razorpay_signature=req.razorpay_signature,
            confirmation_id=req.confirmation_id,
        )
        return map_order_to_schema(order)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except cart_service.CartNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        ValueError,
        confirmation_service.ConfirmationError,
        spending_limit_service.SpendingLimitExceededError,
        razorpay_service.PaymentVerificationError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
