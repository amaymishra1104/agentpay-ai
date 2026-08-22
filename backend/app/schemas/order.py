from datetime import datetime
from pydantic import BaseModel, Field


class OrderItemSchema(BaseModel):
    product_id: str
    sku: str
    name: str
    quantity: int
    unit_price: int
    line_total: int


class OrderSchema(BaseModel):
    order_id: str
    cart_id: str
    customer_id: str
    merchant_id: str
    currency: str
    items: list[OrderItemSchema]
    subtotal: int
    discount: int
    shipping: int
    total: int
    status: str
    payment_status: str
    payment_id: str | None = None
    payment_method: str | None = None
    transaction_reference: str | None = None
    created_at: datetime
    updated_at: datetime
    
    # Fulfillment timestamps
    confirmed_at: datetime | None = None
    packed_at: datetime | None = None
    shipped_at: datetime | None = None
    delivered_at: datetime | None = None
    cancelled_at: datetime | None = None


class CheckoutRequest(BaseModel):
    payment_method: str = Field(default="mock_upi")
    customer_id: str


class TrackingTimelineEvent(BaseModel):
    status: str
    timestamp: datetime | None = None
    label: str
    completed: bool


class TrackingSchema(BaseModel):
    order_id: str
    status: str
    estimated_delivery: str
    tracking_number: str
    carrier: str
    timeline: list[TrackingTimelineEvent]


class ReturnItemSchema(BaseModel):
    product_id: str
    quantity: int
    reason: str | None = None


class ReturnRequestSchema(BaseModel):
    return_id: str
    order_id: str
    customer_id: str
    status: str
    items: list[ReturnItemSchema]
    created_at: datetime
    updated_at: datetime

