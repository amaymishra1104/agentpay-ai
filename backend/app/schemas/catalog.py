from datetime import datetime

from pydantic import BaseModel, Field


class MerchantRecord(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    city: str = Field(min_length=1)


class ShippingInfo(BaseModel):
    free_shipping: bool
    estimated_days: int = Field(ge=1)


class ReturnPolicyInfo(BaseModel):
    days: int = Field(ge=0)
    eligible: bool


class OfferSummary(BaseModel):
    offer_id: str
    title: str
    type: str
    discount_percent: int = Field(ge=0)


class ProductRecord(BaseModel):
    id: str = Field(min_length=1)
    merchant_id: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    subcategory: str = Field(min_length=1)
    description: str = Field(default="")
    price_inr: int = Field(ge=0)
    compare_at_price_inr: int = Field(ge=0)
    cost_inr: int = Field(ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    inventory_quantity: int = Field(ge=0)
    available: bool
    rating: float = Field(ge=0, le=5)
    review_count: int = Field(ge=0)
    brand: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    specifications: dict[str, str] = Field(default_factory=dict)
    image_url: str = Field(min_length=1)
    shipping: ShippingInfo
    return_policy: ReturnPolicyInfo
    eligible_offers: list[str] = Field(default_factory=list)
    complementary_product_ids: list[str] = Field(default_factory=list)
    upsell_product_ids: list[str] = Field(default_factory=list)
    created_at: datetime


class PriceView(BaseModel):
    amount: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)


class AvailabilityView(BaseModel):
    in_stock: bool
    quantity: int = Field(ge=0)


class RatingView(BaseModel):
    score: float = Field(ge=0, le=5)
    reviews: int = Field(ge=0)


class AgentCatalogProduct(BaseModel):
    product_id: str
    name: str
    category: str
    subcategory: str
    description: str
    brand: str
    price: PriceView
    availability: AvailabilityView
    rating: RatingView
    features: list[str] = Field(default_factory=list)
    specifications: dict[str, str] = Field(default_factory=dict)
    shipping: ShippingInfo
    return_policy: ReturnPolicyInfo
    offers: list[OfferSummary] = Field(default_factory=list)
    recommended_with: list[str] = Field(default_factory=list)
    better_alternative: str | None = None
    image_url: str


class CatalogQueryParams(BaseModel):
    query: str | None = None
    category: str | None = None
    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)
    min_rating: float | None = Field(default=None, ge=0, le=5)
    in_stock: bool | None = None
    limit: int = Field(default=20, ge=1, le=100)


class ProductSearchResponse(BaseModel):
    items: list[AgentCatalogProduct] = Field(default_factory=list)
    total: int = Field(ge=0)


class RelatedProductsResponse(BaseModel):
    product_id: str
    complementary: list[AgentCatalogProduct] = Field(default_factory=list)
    upsell: list[AgentCatalogProduct] = Field(default_factory=list)
    alternatives: list[AgentCatalogProduct] = Field(default_factory=list)


class CategoryListResponse(BaseModel):
    categories: list[str] = Field(default_factory=list)


class ProductComparisonItem(BaseModel):
    product_id: str
    name: str
    category: str
    price: PriceView
    rating: RatingView
    availability: AvailabilityView
    features: list[str] = Field(default_factory=list)
    shipping: ShippingInfo
    return_policy: ReturnPolicyInfo
    offers: list[OfferSummary] = Field(default_factory=list)


class ProductComparisonResponse(BaseModel):
    items: list[ProductComparisonItem] = Field(default_factory=list)
