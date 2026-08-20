"""Deterministic catalog tools for future agent orchestration."""

from app.schemas.catalog import (
	AgentCatalogProduct,
	CatalogQueryParams,
	ProductComparisonResponse,
	ProductSearchResponse,
	RelatedProductsResponse,
)
from app.services import catalog_service


def search_products(
	*,
	query: str | None = None,
	category: str | None = None,
	min_price: int | None = None,
	max_price: int | None = None,
	min_rating: float | None = None,
	in_stock: bool | None = None,
	limit: int = 20,
) -> ProductSearchResponse:
	"""Search catalog products using deterministic filters and ranking."""
	params = CatalogQueryParams(
		query=query,
		category=category,
		min_price=min_price,
		max_price=max_price,
		min_rating=min_rating,
		in_stock=in_stock,
		limit=limit,
	)
	return catalog_service.search_products(params)


def get_product(product_id: str) -> AgentCatalogProduct:
	"""Return one product in public agent-readable format."""
	return catalog_service.get_product(product_id)


def get_related_products(product_id: str, limit: int = 6) -> RelatedProductsResponse:
	"""Return complementary, upsell, and alternative products for one product."""
	return catalog_service.get_related_products(product_id=product_id, limit=limit)


def compare_products(product_ids: list[str]) -> ProductComparisonResponse:
	"""Return a structured product comparison view safe for buyer consumption."""
	return catalog_service.compare_products(product_ids)
