from pydantic import BaseModel, Field


class CreatePaymentOrderRequest(BaseModel):
    customer_id: str | None = None


class CreatePaymentOrderResponse(BaseModel):
    razorpay_order_id: str
    amount_paise: int
    currency: str = "INR"
    receipt: str | None = None
    key_id: str | None = None
    cart_id: str
    total_inr: int
    mode: str = "test"
