from pydantic import BaseModel, Field


class CreateOrderRequest(BaseModel):
    customer_id: str = Field(min_length=1)
    amount_minor: int = Field(ge=1)
    currency: str = Field(default="INR", min_length=3, max_length=3)


class CreateOrderResponse(BaseModel):
    order_id: str
    provider: str = "razorpay"
    mode: str = "test"
