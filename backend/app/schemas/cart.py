from datetime import datetime
from pydantic import BaseModel, Field


class CartItemSchema(BaseModel):
    product_id: str
    sku: str
    name: str
    unit_price_inr: int
    quantity: int
    line_total_inr: int
    available: bool
    inventory_checked: bool


class AppliedOfferSchema(BaseModel):
    offer_id: str
    name: str
    discount_type: str
    discount_amount_inr: int
    reason: str


class CartSchema(BaseModel):
    cart_id: str
    merchant_id: str
    customer_id: str
    currency: str
    items: list[CartItemSchema]
    subtotal_inr: int
    discount_inr: int
    shipping_inr: int
    total_inr: int
    applied_offers: list[AppliedOfferSchema]
    status: str
    created_at: datetime
    updated_at: datetime


class CartCreateRequest(BaseModel):
    merchant_id: str
    customer_id: str


class CartItemAddRequest(BaseModel):
    product_id: str
    quantity: int = Field(..., gt=0)


class CartItemUpdateRequest(BaseModel):
    quantity: int = Field(..., gt=0)


class CartValidationIssue(BaseModel):
    type: str
    product_id: str | None = None
    message: str


class CartValidationResponse(BaseModel):
    valid: bool
    issues: list[CartValidationIssue]
