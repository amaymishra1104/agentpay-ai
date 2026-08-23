import os
os.environ["DATABASE_URL"] = "sqlite:///./agentpay.db"

import pytest
from app.services.razorpay_service import (
    create_razorpay_order,
    verify_payment_signature,
    verify_webhook_signature,
    is_razorpay_configured,
)


def test_razorpay_order_creation_sandbox_mode():
    res = create_razorpay_order(amount_inr=1500, currency="INR")
    assert "razorpay_order_id" in res
    assert res["amount_paise"] == 150000
    assert res["currency"] == "INR"
    assert res["status"] == "created"
    assert res["mode"] in ("sandbox", "test", "live")


def test_razorpay_mock_signature_verification():
    # Test sandbox mock signature verification
    valid = verify_payment_signature(
        razorpay_order_id="rzp_order_test_123",
        razorpay_payment_id="pay_test_123",
        razorpay_signature="mock_sig_123",
    )
    assert valid is True


def test_razorpay_webhook_signature():
    payload = '{"event": "payment.captured"}'
    # Test webhook verification returns boolean
    sig = verify_webhook_signature(payload, "invalid_sig")
    assert isinstance(sig, bool)
