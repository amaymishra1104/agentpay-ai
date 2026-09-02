"""
Authoritative Razorpay Webhook Processing Service.

Verifies cryptographic webhook signatures (X-Razorpay-Signature) and ensures
strict database-level idempotency so duplicate webhook deliveries produce identical state
without double-decrementing inventory or creating duplicate orders.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Order, PaymentOrder, WebhookEvent
from app.services import razorpay_service

logger = logging.getLogger("agentpay")


class WebhookVerificationError(ValueError):
    """Raised when webhook signature verification fails."""
    pass


def process_razorpay_webhook(
    raw_payload: bytes | str,
    signature_header: str | None,
    db: Session,
    event_id_header: str | None = None,
) -> dict:
    """
    Process incoming Razorpay webhook event idempotently.
    """
    if isinstance(raw_payload, str):
        raw_bytes = raw_payload.encode("utf-8")
    else:
        raw_bytes = raw_payload

    # 1. Verify cryptographic signature
    if not signature_header or not razorpay_service.verify_webhook_signature(raw_bytes, signature_header):
        logger.warning("Rejected Razorpay webhook: invalid signature header")
        raise WebhookVerificationError("Invalid or missing Razorpay webhook signature")

    # 2. Parse event payload
    try:
        event_data = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        raise ValueError("Invalid JSON in webhook payload") from exc

    event_type = event_data.get("event", "unknown")
    event_id = (
        event_data.get("event_id")
        or event_data.get("id")
        or event_id_header
    )
    if not event_id:
        # Fallback deterministic event id based on payload hash
        import hashlib
        event_id = f"evt_{hashlib.sha256(raw_bytes).hexdigest()[:24]}"

    # 3. Database-level Idempotency: Pre-check for duplicate event
    existing_event = db.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).first()
    if existing_event:
        logger.info("Webhook event %s was already processed. Returning idempotent response.", event_id)
        return {
            "status": "already_processed",
            "event_id": event_id,
            "event_type": event_type,
        }

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    webhook_record = WebhookEvent(
        event_id=event_id,
        event_type=event_type,
        payload_json=raw_bytes.decode("utf-8", errors="replace"),
        status="processed",
        created_at=now,
    )

    payload_obj = event_data.get("payload", {})
    payment_entity = payload_obj.get("payment", {}).get("entity", {})
    refund_entity = payload_obj.get("refund", {}).get("entity", {})

    rzp_order_id = payment_entity.get("order_id")
    rzp_payment_id = payment_entity.get("id") or refund_entity.get("payment_id")

    try:
        db.add(webhook_record)

        # 4. Apply state transitions atomically within the same transaction
        if event_type == "payment.captured":
            if rzp_order_id:
                payment_order = db.query(PaymentOrder).filter(PaymentOrder.razorpay_order_id == rzp_order_id).first()
                if payment_order:
                    payment_order.status = "captured"
                    if rzp_payment_id:
                        payment_order.razorpay_payment_id = rzp_payment_id
                    payment_order.updated_at = now

            if rzp_payment_id or rzp_order_id:
                order = db.query(Order).filter(
                    (Order.payment_id == rzp_payment_id) | (Order.transaction_reference == rzp_order_id)
                ).first()
                if order:
                    order.payment_status = "successful"
                    if rzp_payment_id and not order.payment_id:
                        order.payment_id = rzp_payment_id
                    order.updated_at = now

        elif event_type == "payment.failed":
            if rzp_order_id:
                payment_order = db.query(PaymentOrder).filter(PaymentOrder.razorpay_order_id == rzp_order_id).first()
                if payment_order:
                    payment_order.status = "failed"
                    payment_order.updated_at = now

            if rzp_payment_id or rzp_order_id:
                order = db.query(Order).filter(
                    (Order.payment_id == rzp_payment_id) | (Order.transaction_reference == rzp_order_id)
                ).first()
                if order:
                    order.payment_status = "failed"
                    order.updated_at = now

        elif event_type == "refund.processed":
            if rzp_payment_id:
                order = db.query(Order).filter(Order.payment_id == rzp_payment_id).first()
                if order:
                    order.payment_status = "refunded"
                    order.status = "cancelled" if order.status in ("placed", "confirmed", "packed") else order.status
                    order.updated_at = now

        db.commit()

    except IntegrityError:
        db.rollback()
        logger.info("IntegrityError on event %s: concurrent duplicate webhook handled.", event_id)
        return {
            "status": "already_processed",
            "event_id": event_id,
            "event_type": event_type,
        }
    except Exception as exc:
        db.rollback()
        logger.error("Error processing webhook %s: %s", event_id, exc)
        raise

    return {
        "status": "processed",
        "event_id": event_id,
        "event_type": event_type,
    }
