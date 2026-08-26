import json
import logging
import os
import time
from functools import lru_cache
from pathlib import Path

from app.services.file_lock import file_lock

from app.schemas.catalog import (
    AgentCatalogProduct,
    AvailabilityView,
    CatalogQueryParams,
    MerchantRecord,
    OfferSummary,
    PriceView,
    ProductComparisonItem,
    ProductComparisonResponse,
    ProductRecord,
    ProductSearchResponse,
    RatingView,
    RelatedProductsResponse,
)


logger = logging.getLogger(__name__)


class ProductNotFoundError(ValueError):
    """Raised when a product does not exist in the catalog."""


class CatalogDataError(RuntimeError):
    """Raised when catalog seed data is malformed or inconsistent."""


def _data_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data"


LOCK_FILE = (
    Path(os.environ["AGENTPAY_LOCK_FILE"])
    if os.environ.get("AGENTPAY_LOCK_FILE")
    else _data_dir() / "products.json.lock"
)


def _load_json(filename: str) -> list[dict]:
    filepath = _data_dir() / filename

    max_retries = 5
    payload = None

    for attempt in range(max_retries):
        try:
            with filepath.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            break

        except (PermissionError, json.JSONDecodeError) as exc:
            if attempt == max_retries - 1:
                raise exc

            time.sleep(0.05 * (attempt + 1))

    if not isinstance(payload, list):
        raise CatalogDataError(
            f"{filename} must contain a JSON array"
        )

    return payload


@lru_cache(maxsize=1)
def _load_merchants() -> dict[str, MerchantRecord]:
    records = [
        MerchantRecord.model_validate(item)
        for item in _load_json("merchants.json")
    ]

    return {
        record.id: record
        for record in records
    }


@lru_cache(maxsize=1)
def _load_products() -> dict[str, ProductRecord]:
    records = [
        ProductRecord.model_validate(item)
        for item in _load_json("products.json")
    ]

    products_by_id = {
        record.id: record
        for record in records
    }

    for product in records:
        for related_id in (
            product.complementary_product_ids
            + product.upsell_product_ids
        ):
            if related_id not in products_by_id:
                raise CatalogDataError(
                    f"Product {product.id} references "
                    f"missing related product {related_id}"
                )

        if product.available and product.inventory_quantity <= 0:
            raise CatalogDataError(
                f"Product {product.id} marked available "
                f"with non-positive inventory"
            )

        if not product.available and product.inventory_quantity > 0:
            logger.warning(
                "Product %s has stock but is marked unavailable; "
                "honoring explicit unavailable flag",
                product.id,
            )

    return products_by_id


@lru_cache(maxsize=1)
def _load_offers_by_product() -> dict[str, list[OfferSummary]]:
    offers_by_product: dict[str, list[OfferSummary]] = {}

    products_by_id = _load_products()
    offer_ids: set[str] = set()

    for offer in _load_json("offers.json"):
        offer_ids.add(offer["id"])

        product_ids = offer.get("product_ids", [])

        if not isinstance(product_ids, list):
            raise CatalogDataError(
                f"Offer {offer.get('id', 'unknown')} "
                f"has invalid product_ids"
            )

        for product_id in product_ids:
            if product_id not in products_by_id:
                raise CatalogDataError(
                    f"Offer {offer.get('id', 'unknown')} "
                    f"references missing product {product_id}"
                )

            offers_by_product.setdefault(
                product_id,
                [],
            ).append(
                OfferSummary(
                    offer_id=offer["id"],
                    title=offer["title"],
                    type=offer["type"],
                    discount_percent=offer["discount_percent"],
                )
            )

    for product in products_by_id.values():
        for offer_id in product.eligible_offers:
            if offer_id not in offer_ids:
                raise CatalogDataError(
                    f"Product {product.id} references "
                    f"missing offer {offer_id}"
                )

    return offers_by_product


def _to_public_product(
    product: ProductRecord,
) -> AgentCatalogProduct:

    offers = _load_offers_by_product().get(
        product.id,
        [],
    )

    return AgentCatalogProduct(
        product_id=product.id,
        name=product.name,
        category=product.category,
        subcategory=product.subcategory,
        description=product.description,
        brand=product.brand,
        price=PriceView(
            amount=product.price_inr,
            currency=product.currency,
        ),
        availability=AvailabilityView(
            in_stock=(
                product.available
                and product.inventory_quantity > 0
            ),
            quantity=product.inventory_quantity,
        ),
        rating=RatingView(
            score=product.rating,
            reviews=product.review_count,
        ),
        features=product.features,
        specifications=product.specifications,
        shipping=product.shipping,
        return_policy=product.return_policy,
        offers=offers,
        recommended_with=product.complementary_product_ids,
        better_alternative=(
            product.upsell_product_ids[0]
            if product.upsell_product_ids
            else None
        ),
        image_url=product.image_url,
    )


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _search_text(product: ProductRecord) -> str:
    fields = [
        product.name,
        product.category,
        product.subcategory,
        product.description,
        product.brand,
        " ".join(product.tags),
        " ".join(product.features),
    ]

    return _normalize(" ".join(fields))


def _relevance_score(
    product: ProductRecord,
    query: str | None,
) -> int:

    if not query:
        return 0

    normalized_query = _normalize(query)
    haystack = _search_text(product)

    terms = [
        term
        for term in normalized_query.split(" ")
        if term
    ]

    if not terms:
        return 0

    score = 0

    if normalized_query in haystack:
        score += 8

    for term in terms:
        if term in haystack:
            score += 2

        if term in _normalize(product.name):
            score += 3

        if term in _normalize(product.category):
            score += 2

    return score


def _price_fit_score(
    product: ProductRecord,
    params: CatalogQueryParams,
) -> float:

    if params.max_price is not None and params.max_price > 0:

        if product.price_inr > params.max_price:
            return 0.0

        return 1 - (
            product.price_inr / params.max_price
        )

    return 1 / (product.price_inr + 1)


def _matches_filters(
    product: ProductRecord,
    params: CatalogQueryParams,
) -> bool:

    if (
        params.category
        and _normalize(product.category)
        != _normalize(params.category)
    ):
        return False

    if (
        params.min_price is not None
        and product.price_inr < params.min_price
    ):
        return False

    if (
        params.max_price is not None
        and product.price_inr > params.max_price
    ):
        return False

    if (
        params.min_rating is not None
        and product.rating < params.min_rating
    ):
        return False

    if params.in_stock is True:
        if not (
            product.available
            and product.inventory_quantity > 0
        ):
            return False

    if params.in_stock is False:
        if (
            product.available
            and product.inventory_quantity > 0
        ):
            return False

    if (
        params.query
        and _relevance_score(
            product,
            params.query,
        ) <= 0
    ):
        return False

    return True


def search_products(
    params: CatalogQueryParams,
) -> ProductSearchResponse:

    products = list(
        _load_products().values()
    )

    filtered = [
        product
        for product in products
        if _matches_filters(product, params)
    ]

    ranked = sorted(
        filtered,
        key=lambda product: (
            _relevance_score(
                product,
                params.query,
            ),
            1 if (
                product.available
                and product.inventory_quantity > 0
            ) else 0,
            product.rating,
            _price_fit_score(
                product,
                params,
            ),
            product.review_count,
            -product.price_inr,
        ),
        reverse=True,
    )

    items = [
        _to_public_product(product)
        for product in ranked[: params.limit]
    ]

    return ProductSearchResponse(
        items=items,
        total=len(filtered),
    )


def get_product(
    product_id: str,
) -> AgentCatalogProduct:

    product = _load_products().get(product_id)

    if product is None:
        raise ProductNotFoundError(
            f"Product not found: {product_id}"
        )

    return _to_public_product(product)


def get_related_products(
    product_id: str,
    limit: int = 6,
) -> RelatedProductsResponse:

    source = _load_products().get(product_id)

    if source is None:
        raise ProductNotFoundError(
            f"Product not found: {product_id}"
        )

    products_by_id = _load_products()

    complementary = [
        _to_public_product(products_by_id[pid])
        for pid in source.complementary_product_ids
        if pid in products_by_id
    ][:limit]

    upsell = [
        _to_public_product(products_by_id[pid])
        for pid in source.upsell_product_ids
        if pid in products_by_id
    ][:limit]

    alternatives: list[AgentCatalogProduct] = []

    for product in products_by_id.values():

        if product.id == source.id:
            continue

        if product.category != source.category:
            continue

        if (
            product.price_inr < source.price_inr * 0.85
            or product.price_inr > source.price_inr * 1.15
        ):
            continue

        alternatives.append(
            _to_public_product(product)
        )

    alternatives = sorted(
        alternatives,
        key=lambda item: (
            item.rating.score,
            item.availability.in_stock,
            -item.price.amount,
        ),
        reverse=True,
    )[:limit]

    return RelatedProductsResponse(
        product_id=product_id,
        complementary=complementary,
        upsell=upsell,
        alternatives=alternatives,
    )


def get_cross_sell_recommendations(
    product_id: str,
) -> dict:

    source = _load_products().get(product_id)

    if source is None:
        raise ProductNotFoundError(
            f"Product not found: {product_id}"
        )

    products_by_id = _load_products()
    recommendations = []

    for comp_id in source.complementary_product_ids:

        if comp_id in products_by_id:

            comp = products_by_id[comp_id]

            recommendations.append(
                {
                    "product_id": comp.id,
                    "name": comp.name,
                    "category": comp.category,
                    "price_inr": comp.price_inr,
                    "explanation": (
                        f"Recommended because it is compatible "
                        f"with your selected {source.name} "
                        f"({source.category}) and is frequently "
                        f"paired with similar purchases."
                    ),
                }
            )

    if not recommendations:

        category_map = {
            "laptops": [
                "backpack",
                "headphones",
            ],
            "headphones": [
                "backpack",
                "yoga_mat",
            ],
            "backpack": [
                "hydration_bottles",
                "sports_watches",
            ],
            "yoga_mat": [
                "fitness_accessories",
                "hydration_bottles",
            ],
        }

        target_categories = category_map.get(
            source.category,
            ["fitness_accessories"],
        )

        for product in products_by_id.values():

            if (
                product.category in target_categories
                and product.available
            ):

                recommendations.append(
                    {
                        "product_id": product.id,
                        "name": product.name,
                        "category": product.category,
                        "price_inr": product.price_inr,
                        "explanation": (
                            f"Recommended because it matches "
                            f"your selected {source.name} "
                            f"category ({source.category}) and "
                            f"enhances your experience."
                        ),
                    }
                )

                if len(recommendations) >= 3:
                    break

    return {
        "source_product_id": product_id,
        "source_product_name": source.name,
        "recommendations": recommendations,
    }


def list_categories() -> list[str]:

    categories = {
        _normalize(product.category): product.category
        for product in _load_products().values()
    }

    return sorted(categories.values())


def compare_products(
    product_ids: list[str],
) -> ProductComparisonResponse:

    if not product_ids:
        return ProductComparisonResponse(items=[])

    products_by_id = _load_products()

    missing = [
        product_id
        for product_id in product_ids
        if product_id not in products_by_id
    ]

    if missing:
        raise ProductNotFoundError(
            f"Products not found: {', '.join(missing)}"
        )

    items = [
        ProductComparisonItem(
            product_id=product.id,
            name=product.name,
            category=product.category,
            price=PriceView(
                amount=product.price_inr,
                currency=product.currency,
            ),
            rating=RatingView(
                score=product.rating,
                reviews=product.review_count,
            ),
            availability=AvailabilityView(
                in_stock=(
                    product.available
                    and product.inventory_quantity > 0
                ),
                quantity=product.inventory_quantity,
            ),
            features=product.features,
            shipping=product.shipping,
            return_policy=product.return_policy,
            offers=_load_offers_by_product().get(
                product.id,
                [],
            ),
        )
        for product in [
            products_by_id[pid]
            for pid in product_ids
        ]
    ]

    return ProductComparisonResponse(
        items=items
    )


def _invalidate_catalog_caches() -> None:
    _load_products.cache_clear()
    _load_offers_by_product.cache_clear()


def _safe_write_json(
    filename: str,
    data: list[dict],
) -> None:

    filepath = _data_dir() / filename
    temp_filepath = filepath.with_suffix(".tmp")

    with temp_filepath.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )

        file.flush()
        os.fsync(file.fileno())

    max_retries = 5

    for attempt in range(max_retries):

        try:
            os.replace(
                temp_filepath,
                filepath,
            )
            return

        except PermissionError:

            if attempt == max_retries - 1:
                raise

            time.sleep(
                0.05 * (attempt + 1)
            )

    raise RuntimeError(
        f"Failed to replace {filepath}"
    )


def decrement_inventory(
    items: dict[str, int],
) -> None:
    """
    Atomically decrement inventory for multiple products.

    The complete read -> validate -> mutate -> write operation
    is protected by the cross-process file lock.
    """

    if not items:
        return

    # Validate the request before acquiring the lock.
    for product_id, quantity in items.items():

        if (
            not isinstance(quantity, int)
            or isinstance(quantity, bool)
        ):
            raise ValueError(
                f"Invalid inventory quantity for product "
                f"{product_id}: {quantity}"
            )

        if quantity <= 0:
            raise ValueError(
                f"Invalid inventory quantity for product "
                f"{product_id}: {quantity}"
            )

    with file_lock(LOCK_FILE):

        # IMPORTANT:
        # Always read the latest products.json while holding the lock.
        # Do not use the cached _load_products() here because another
        # process may have changed the file immediately before this
        # operation acquired the lock.
        raw_products = _load_json(
            "products.json"
        )

        products_by_id = {
            product["id"]: product
            for product in raw_products
        }

        # First pass: validate every requested mutation.
        # Nothing is changed until ALL products pass validation.
        for product_id, quantity in items.items():

            product = products_by_id.get(
                product_id
            )

            if product is None:
                raise ValueError(
                    f"Product {product_id} not found"
                )

            current_quantity = int(
                product.get(
                    "inventory_quantity",
                    0,
                )
            )

            if current_quantity < quantity:
                raise ValueError(
                    f"Insufficient inventory for product "
                    f"{product_id}"
                )

        # Second pass: apply every mutation.
        for product_id, quantity in items.items():

            product = products_by_id[
                product_id
            ]

            new_quantity = (
                int(
                    product.get(
                        "inventory_quantity",
                        0,
                    )
                )
                - quantity
            )

            product[
                "inventory_quantity"
            ] = new_quantity

            product[
                "available"
            ] = new_quantity > 0

        # Atomic replacement while the lock is still held.
        _safe_write_json(
            "products.json",
            raw_products,
        )

        # The cached ProductRecord objects are now stale.
        _invalidate_catalog_caches()


def increment_inventory(
    items: dict[str, int],
) -> None:
    """
    Atomically increment inventory for multiple products.

    The complete read -> mutate -> write operation is protected
    by the same cross-process file lock used by decrement_inventory.
    """

    if not items:
        return

    # Validate the request before acquiring the lock.
    for product_id, quantity in items.items():

        if (
            not isinstance(quantity, int)
            or isinstance(quantity, bool)
        ):
            raise ValueError(
                f"Invalid inventory quantity for product "
                f"{product_id}: {quantity}"
            )

        if quantity <= 0:
            raise ValueError(
                f"Invalid inventory quantity for product "
                f"{product_id}: {quantity}"
            )

    with file_lock(LOCK_FILE):

        # Always read the latest file while holding the lock.
        raw_products = _load_json(
            "products.json"
        )

        products_by_id = {
            product["id"]: product
            for product in raw_products
        }

        # Validate all product IDs before mutating anything.
        for product_id in items:

            product = products_by_id.get(
                product_id
            )

            if product is None:
                raise ValueError(
                    f"Product {product_id} not found"
                )

        # Apply every increment.
        for product_id, quantity in items.items():

            product = products_by_id[
                product_id
            ]

            new_quantity = (
                int(
                    product.get(
                        "inventory_quantity",
                        0,
                    )
                )
                + quantity
            )

            product[
                "inventory_quantity"
            ] = new_quantity

            product[
                "available"
            ] = new_quantity > 0

        # Atomic replacement while the lock is still held.
        _safe_write_json(
            "products.json",
            raw_products,
        )

        # The cached ProductRecord objects are now stale.
        _invalidate_catalog_caches()