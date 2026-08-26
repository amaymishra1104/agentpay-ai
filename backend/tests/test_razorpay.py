import hashlib
import hmac
import os
from unittest.mock import MagicMock, patch
import pytest

from app.config import get_settings
from app.services.razorpay_service import (
    create_razorpay_order,
    verify_payment_signature,
    verify_webhook_signature,
    is_razorpay_configured,
    RazorpayServiceError,
)


def test_is_razorpay_configured():
    settings = get_settings()
    with patch.object(settings, "razorpay_key_id", "rzp_test_123"), \
         patch.object(settings, "razorpay_key_secret", "secret_abc"):
        assert is_razorpay_configured() is True

    with patch.object(settings, "razorpay_key_id", None), \
         patch.object(settings, "razorpay_key_secret", None):
        assert is_razorpay_configured() is False


def test_create_razorpay_order_sandbox_fallback():
    settings = get_settings()
    with patch.object(settings, "razorpay_key_id", None), \
         patch.object(settings, "razorpay_key_secret", None):
        res = create_razorpay_order(amount_inr=1500, currency="INR")
        assert "razorpay_order_id" in res
        assert res["razorpay_order_id"].startswith("rzp_order_test_")
        assert res["amount_paise"] == 150000
        assert res["currency"] == "INR"
        assert res["mode"] == "sandbox"
        assert res["key_id"] == "rzp_test_sandbox_key"
        assert res["status"] == "created"


def test_create_razorpay_order_with_configured_keys():
    settings = get_settings()
    with patch.object(settings, "razorpay_key_id", "rzp_test_key_123"), \
         patch.object(settings, "razorpay_key_secret", "rzp_secret_456"):
        mock_client = MagicMock()
        mock_client.order.create.return_value = {
            "id": "order_live_rzp_999",
            "amount": 250000,
            "currency": "INR",
            "receipt": "rcpt_test_custom",
            "status": "created",
        }

        with patch("razorpay.Client", return_value=mock_client):
            res = create_razorpay_order(
                amount_inr=2500,
                currency="INR",
                receipt="rcpt_test_custom",
                notes={"cart_id": "cart_123", "customer_id": "c_456"},
            )
            assert res["razorpay_order_id"] == "order_live_rzp_999"
            assert res["amount_paise"] == 250000
            assert res["currency"] == "INR"
            assert res["key_id"] == "rzp_test_key_123"
            assert res["status"] == "created"

            mock_client.order.create.assert_called_once_with({
                "amount": 250000,
                "currency": "INR",
                "receipt": "rcpt_test_custom",
                "payment_capture": 1,
                "notes": {"cart_id": "cart_123", "customer_id": "c_456"},
            })


def test_create_razorpay_order_invalid_amount():
    with pytest.raises(ValueError, match="Invalid amount"):
        create_razorpay_order(amount_inr=0)

    with pytest.raises(ValueError, match="Invalid amount"):
        create_razorpay_order(amount_inr=-50)


def test_create_razorpay_order_upstream_api_failure():
    settings = get_settings()
    with patch.object(settings, "razorpay_key_id", "rzp_test_key_123"), \
         patch.object(settings, "razorpay_key_secret", "rzp_secret_456"):
        mock_client = MagicMock()
        mock_client.order.create.side_effect = Exception("Razorpay API Timeout / 500")

        with patch("razorpay.Client", return_value=mock_client):
            with pytest.raises(RazorpayServiceError, match="Razorpay order creation failed"):
                create_razorpay_order(amount_inr=100)


def test_verify_payment_signature_valid_and_invalid():
    secret = "my_super_secret_test_key"
    order_id = "order_rzp_abc123"
    payment_id = "pay_rzp_xyz789"

    # Compute valid signature
    msg = f"{order_id}|{payment_id}"
    valid_sig = hmac.new(
        secret.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    settings = get_settings()
    with patch.object(settings, "razorpay_key_id", "rzp_test_123"), \
         patch.object(settings, "razorpay_key_secret", secret):
        # Valid signature should pass
        assert verify_payment_signature(order_id, payment_id, valid_sig) is True

        # Tampered signature should fail
        assert verify_payment_signature(order_id, payment_id, "invalid_tampered_sig") is False

        # Wrong payment ID should fail
        assert verify_payment_signature(order_id, "pay_different", valid_sig) is False

        # Wrong order ID should fail
        assert verify_payment_signature("order_different", payment_id, valid_sig) is False

        # Empty fields should fail
        assert verify_payment_signature("", payment_id, valid_sig) is False
        assert verify_payment_signature(order_id, "", valid_sig) is False
        assert verify_payment_signature(order_id, payment_id, "") is False


def test_verify_webhook_signature():
    secret = "whsec_test_secret_123"
    payload = '{"event":"payment.captured","payload":{"payment":{"entity":{"id":"pay_123"}}}}'

    valid_wh_sig = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    settings = get_settings()
    with patch.object(settings, "webhook_secret", secret):
        assert verify_webhook_signature(payload, valid_wh_sig) is True
        assert verify_webhook_signature(payload.encode("utf-8"), valid_wh_sig) is True
        assert verify_webhook_signature(payload, "invalid_sig") is False
        assert verify_webhook_signature(payload, "") is False
