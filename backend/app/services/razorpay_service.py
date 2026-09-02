"""
Razorpay Integration Helper Module — TEST MODE Architecture.

Provides Razorpay order creation, payment signature verification,
payment-intent mapping (PaymentOrder binding), webhook validation, and sandbox fallback.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Cart, PaymentOrder

logger = logging.getLogger("agentpay")


class RazorpayServiceError(Exception):
    """Base exception for Razorpay integration errors."""
    pass


class PaymentVerificationError(RazorpayServiceError):
    """Raised when Razorpay payment signature or order binding verification fails."""
    pass


def is_razorpay_configured() -> bool:
    """Check if Razorpay API keys are configured."""
    settings = get_settings()
    return bool(settings.razorpay_key_id and settings.razorpay_key_secret)


def create_razorpay_order(
    amount_inr: int,
    currency: str = "INR",
    receipt: str | None = None,
    notes: dict | None = None,
    db: Session | None = None,
    cart_id: str | None = None,
    customer_id: str | None = None,
) -> dict:
    """
    Create a Razorpay order in paise (amount_inr * 100).
    Persists the authoritative PaymentOrder record in SQLite to bind
    razorpay_order_id -> cart_id + customer_id + amount_paise.
    """
    if amount_inr <= 0:
        raise ValueError(f"Invalid amount for Razorpay order: {amount_inr}. Must be > 0.")

    settings = get_settings()
    amount_paise = amount_inr * 100
    order_receipt = receipt or f"rcpt_{uuid.uuid4().hex[:10]}"

    bound_cart_id = cart_id or (notes.get("cart_id") if notes else None) or "unknown_cart"
    bound_customer_id = customer_id or (notes.get("customer_id") if notes else None) or "unknown_customer"

    if not is_razorpay_configured():
        # Sandbox Test Mode Fallback (when real test keys are not configured in environment)
        mock_rzp_order_id = f"rzp_order_test_{uuid.uuid4().hex[:10]}"
        result = {
            "mode": "sandbox",
            "razorpay_order_id": mock_rzp_order_id,
            "amount_paise": amount_paise,
            "currency": currency,
            "receipt": order_receipt,
            "key_id": "rzp_test_sandbox_key",
            "status": "created",
        }
    else:
        try:
            import razorpay

            client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
            order_data = {
                "amount": amount_paise,
                "currency": currency,
                "receipt": order_receipt,
                "payment_capture": 1,
            }
            if notes:
                order_data["notes"] = {str(k): str(v) for k, v in notes.items()}

            rzp_order = client.order.create(order_data)
            result = {
                "mode": settings.razorpay_mode,
                "razorpay_order_id": rzp_order["id"],
                "amount_paise": rzp_order["amount"],
                "currency": rzp_order["currency"],
                "receipt": rzp_order.get("receipt", order_receipt),
                "key_id": settings.razorpay_key_id,
                "status": rzp_order.get("status", "created"),
            }
        except Exception as exc:
            logger.error("Failed to create Razorpay order upstream: %s", exc)
            raise RazorpayServiceError(f"Razorpay order creation failed: {exc}") from exc

    # Persist PaymentOrder in the database for payment-intent binding
    if db is not None:
        try:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            payment_order = PaymentOrder(
                razorpay_order_id=result["razorpay_order_id"],
                cart_id=bound_cart_id,
                customer_id=bound_customer_id,
                amount_paise=amount_paise,
                currency=currency,
                status="created",
                created_at=now,
                updated_at=now,
            )
            db.add(payment_order)
            db.commit()
        except Exception as exc:
            logger.warning("Failed to persist PaymentOrder record: %s", exc)
            db.rollback()

    return result


def verify_payment_signature(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> bool:
    """
    Verify the HMAC-SHA256 signature returned by Razorpay Checkout frontend.
    generated_signature = hmac_sha256(razorpay_order_id + "|" + razorpay_payment_id, secret)
    """
    if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
        return False

    settings = get_settings()

    # In mock sandbox mode without keys, approve mock signatures
    if not is_razorpay_configured() and razorpay_signature.startswith("mock_sig_"):
        return True

    secret = settings.razorpay_key_secret or "mock_secret"
    msg = f"{razorpay_order_id}|{razorpay_payment_id}"
    generated_sig = hmac.new(
        secret.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(generated_sig, razorpay_signature)


def verify_and_bind_payment_order(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
    cart: Cart,
    customer_id: str,
    db: Session,
) -> PaymentOrder:
    """
    Complete Payment-Order Verification & Binding:
    1. Authenticate that the Razorpay order exists in the persistent PaymentOrder mapping.
    2. Verify PaymentOrder.customer_id matches the authenticated customer.
    3. Verify PaymentOrder.cart_id matches the checkout cart.
    4. Recalculate cart total and verify PaymentOrder.amount_paise matches (cart.total_inr * 100).
    5. Verify cryptographic HMAC-SHA256 signature.
    """
    if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
        raise PaymentVerificationError(
            "Razorpay payment verification requires razorpay_order_id, razorpay_payment_id, and razorpay_signature."
        )

    # 1. Load persistent payment intent
    payment_order = (
        db.query(PaymentOrder)
        .filter(PaymentOrder.razorpay_order_id == razorpay_order_id)
        .first()
    )

    if not payment_order:
        raise PaymentVerificationError(
            f"Razorpay order '{razorpay_order_id}' was not found in registered payment orders."
        )

    # 2. Check customer ownership
    if payment_order.customer_id != customer_id:
        raise PaymentVerificationError(
            f"Cross-customer payment rejected: Razorpay order was initiated by customer '{payment_order.customer_id}', not '{customer_id}'."
        )

    # 3. Check cart binding
    if payment_order.cart_id != cart.id:
        raise PaymentVerificationError(
            f"Cart substitution rejected: Razorpay order belongs to cart '{payment_order.cart_id}', not '{cart.id}'."
        )

    # 4. Check exact amount in paise
    expected_paise = cart.total_inr * 100
    if payment_order.amount_paise != expected_paise:
        raise PaymentVerificationError(
            f"Amount mismatch rejected: Razorpay order authorized for ₹{payment_order.amount_paise / 100:.2f}, but cart total is ₹{expected_paise / 100:.2f}."
        )

    # 5. Cryptographic signature check
    if not verify_payment_signature(
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
        razorpay_signature=razorpay_signature,
    ):
        raise PaymentVerificationError("Invalid Razorpay payment signature.")

    # 6. Update payment order record
    payment_order.status = "captured"
    payment_order.razorpay_payment_id = razorpay_payment_id
    payment_order.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    return payment_order


def verify_webhook_signature(payload_body: str | bytes, signature_header: str) -> bool:
    """
    Verify Razorpay webhook signature header using WEBHOOK_SECRET.
    """
    if not signature_header:
        return False

    settings = get_settings()
    secret = settings.webhook_secret or "mock_webhook_secret"

    if isinstance(payload_body, str):
        payload_body = payload_body.encode("utf-8")

    expected_sig = hmac.new(
        secret.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_sig, signature_header)
