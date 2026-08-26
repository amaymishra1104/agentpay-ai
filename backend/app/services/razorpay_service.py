"""
Razorpay Integration Helper Module — TEST MODE Architecture.

Provides Razorpay order creation, payment signature verification,
webhook validation, and sandbox fallback.
"""

import hashlib
import hmac
import logging
import uuid
from app.config import get_settings

logger = logging.getLogger("agentpay")


class RazorpayServiceError(Exception):
    """Base exception for Razorpay integration errors."""
    pass


class PaymentVerificationError(RazorpayServiceError):
    """Raised when Razorpay payment signature verification fails."""
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
) -> dict:
    """
    Create a Razorpay order in paise (amount_inr * 100).
    If credentials are not configured, returns a sandbox test mode order structure.
    """
    if amount_inr <= 0:
        raise ValueError(f"Invalid amount for Razorpay order: {amount_inr}. Must be > 0.")

    settings = get_settings()
    amount_paise = amount_inr * 100
    order_receipt = receipt or f"rcpt_{uuid.uuid4().hex[:10]}"

    if not is_razorpay_configured():
        # Sandbox Test Mode Fallback (when real test keys are not configured in environment)
        mock_rzp_order_id = f"rzp_order_test_{uuid.uuid4().hex[:10]}"
        return {
            "mode": "sandbox",
            "razorpay_order_id": mock_rzp_order_id,
            "amount_paise": amount_paise,
            "currency": currency,
            "receipt": order_receipt,
            "key_id": "rzp_test_sandbox_key",
            "status": "created",
        }

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
        return {
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
