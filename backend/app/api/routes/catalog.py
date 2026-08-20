from fastapi import APIRouter, HTTPException, Query

from app.schemas.catalog import (
	AgentCatalogProduct,
	CategoryListResponse,
	ProductComparisonResponse,
	ProductSearchResponse,
	RelatedProductsResponse,
)
from app.services.catalog_service import ProductNotFoundError, list_categories
from app.tools.catalog_tools import compare_products, get_product, get_related_products, search_products

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/products", response_model=ProductSearchResponse)
def list_products(
	query: str | None = None,
	category: str | None = None,
	min_price: int | None = Query(default=None, ge=0),
	max_price: int | None = Query(default=None, ge=0),
	min_rating: float | None = Query(default=None, ge=0, le=5),
	in_stock: bool | None = None,
	limit: int = Query(default=20, ge=1, le=100),
) -> ProductSearchResponse:
	return search_products(
		query=query,
		category=category,
		min_price=min_price,
		max_price=max_price,
		min_rating=min_rating,
		in_stock=in_stock,
		limit=limit,
	)


@router.get("/products/{product_id}", response_model=AgentCatalogProduct)
def fetch_product(product_id: str) -> AgentCatalogProduct:
	try:
		return get_product(product_id)
	except ProductNotFoundError as exc:
		raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/products/{product_id}/related", response_model=RelatedProductsResponse)
def fetch_related(product_id: str, limit: int = Query(default=6, ge=1, le=20)) -> RelatedProductsResponse:
	try:
		return get_related_products(product_id=product_id, limit=limit)
	except ProductNotFoundError as exc:
		raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/categories", response_model=CategoryListResponse)
def get_categories() -> CategoryListResponse:
	return CategoryListResponse(categories=list_categories())


@router.post("/products/compare", response_model=ProductComparisonResponse)
def compare(product_ids: list[str]) -> ProductComparisonResponse:
	try:
		return compare_products(product_ids)
	except ProductNotFoundError as exc:
		raise HTTPException(status_code=404, detail=str(exc)) from exc
