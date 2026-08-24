import json
import os
import time
from functools import lru_cache
from pathlib import Path

from app.services.file_lock import file_lock


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _data_dir() -> Path:
    return _project_root() / "data"


PRODUCTS_FILE = _data_dir() / "products.json"
MERCHANTS_FILE = _data_dir() / "merchants.json"
LOCK_FILE = _data_dir() / "products.json.lock"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ProductNotFoundError(ValueError):
    """Raised when a requested product does not exist."""


# ---------------------------------------------------------------------------
# Product / merchant loading
# ---------------------------------------------------------------------------


class Product:
    def __init__(self, data: dict):
        self.id = data["id"]
        self.merchant_id = data.get("merchant_id")
        self.sku = data.get("sku")
        self.name = data.get("name")
        self.category = data.get("category")
        self.subcategory = data.get("subcategory")
        self.description = data.get("description")
        self.price_inr = data.get("price_inr", 0)
        self.compare_at_price_inr = data.get("compare_at_price_inr")
        self.cost_inr = data.get("cost_inr")
        self.currency = data.get("currency", "INR")
        self.inventory_quantity = data.get("inventory_quantity", 0)
        self.available = data.get("available", False)
        self.rating = data.get("rating")
        self.review_count = data.get("review_count", 0)
        self.brand = data.get("brand")
        self.tags = data.get("tags", [])

    def __repr__(self) -> str:
        return (
            f"Product(id={self.id!r}, "
            f"inventory_quantity={self.inventory_quantity!r}, "
            f"available={self.available!r})"
        )


@lru_cache(maxsize=1)
def _load_products() -> dict[str, Product]:
    with PRODUCTS_FILE.open("r", encoding="utf-8") as file:
        raw_products = json.load(file)

    return {
        product["id"]: Product(product)
        for product in raw_products
    }


@lru_cache(maxsize=1)
def _load_merchants() -> dict[str, dict]:
    """
    Load merchants from merchants.json.

    The legacy cart service requires this loader to exist and return
    merchant records keyed by merchant ID.
    """
    if not MERCHANTS_FILE.exists():
        return {}

    with MERCHANTS_FILE.open("r", encoding="utf-8") as file:
        raw_merchants = json.load(file)

    if not isinstance(raw_merchants, list):
        raise ValueError("merchants.json must contain a JSON array")

    return {
        merchant["id"]: merchant
        for merchant in raw_merchants
        if isinstance(merchant, dict) and merchant.get("id")
    }


def _load_json(filename: str) -> list[dict]:
    filepath = _data_dir() / filename

    with filepath.open("r", encoding="utf-8") as file:
        return json.load(file)


# ---------------------------------------------------------------------------
# Safe JSON writing
# ---------------------------------------------------------------------------


def _safe_write_json(filename: str, data: list[dict]) -> None:
    filepath = _data_dir() / filename
    temp_filepath = filepath.with_suffix(".tmp")

    with temp_filepath.open("w", encoding="utf-8") as file:
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
            os.replace(temp_filepath, filepath)
            return

        except PermissionError:
            if attempt == max_retries - 1:
                raise

            time.sleep(0.05 * (attempt + 1))

    raise RuntimeError(f"Failed to replace {filepath}")


# ---------------------------------------------------------------------------
# Product helpers
# ---------------------------------------------------------------------------


def get_product(product_id: str) -> Product | None:
    """
    Return a single product by ID.
    """
    products = _load_products()
    return products.get(product_id)


def get_products() -> list[Product]:
    """
    Return all products.
    """
    return list(_load_products().values())


def search_products(
    query: str | None = None,
    category: str | None = None,
    merchant_id: str | None = None,
) -> list[Product]:
    """
    Search products using simple text/category/merchant filters.
    """

    products = _load_products().values()

    if query:
        query_lower = query.lower().strip()

        products = [
            product
            for product in products
            if (
                query_lower in (product.name or "").lower()
                or query_lower in (product.description or "").lower()
                or query_lower in (product.brand or "").lower()
                or any(
                    query_lower in str(tag).lower()
                    for tag in product.tags
                )
            )
        ]

    if category:
        category_lower = category.lower()

        products = [
            product
            for product in products
            if (
                (product.category or "").lower() == category_lower
                or (product.subcategory or "").lower() == category_lower
            )
        ]

    if merchant_id:
        products = [
            product
            for product in products
            if product.merchant_id == merchant_id
        ]

    return list(products)


# ---------------------------------------------------------------------------
# Inventory mutation
# ---------------------------------------------------------------------------


def decrement_inventory(items: dict[str, int]) -> None:
    """
    Atomically decrement inventory for multiple products.

    `items` maps:
        product_id -> quantity_to_decrement

    All inventory changes happen under one cross-process lock.

    If any requested quantity cannot be fulfilled, ValueError is raised
    and no partial inventory changes are written.
    """

    if not items:
        return

    # Validate quantities before touching the file.
    for product_id, quantity in items.items():
        if not isinstance(quantity, int) or isinstance(quantity, bool):
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
        raw_products = _load_json("products.json")

        products_by_id = {
            product["id"]: product
            for product in raw_products
        }

        # First pass: validate everything.
        for product_id, quantity in items.items():
            product = products_by_id.get(product_id)

            if product is None:
                raise ValueError(
                    f"Product {product_id} not found"
                )

            current_quantity = int(
                product.get("inventory_quantity", 0)
            )

            if current_quantity < quantity:
                raise ValueError(
                    f"Insufficient inventory for product {product_id}"
                )

        # Second pass: apply everything.
        for product_id, quantity in items.items():
            product = products_by_id[product_id]

            new_quantity = (
                int(product.get("inventory_quantity", 0))
                - quantity
            )

            product["inventory_quantity"] = new_quantity
            product["available"] = new_quantity > 0

        _safe_write_json("products.json", raw_products)

        # Clear cached Product objects because the JSON source changed.
        _load_products.cache_clear()


def increment_inventory(items: dict[str, int]) -> None:
    """
    Atomically increment inventory for multiple products.

    Used to compensate for a successful decrement when a later checkout
    operation fails.
    """

    if not items:
        return

    for product_id, quantity in items.items():
        if not isinstance(quantity, int) or isinstance(quantity, bool):
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
        raw_products = _load_json("products.json")

        products_by_id = {
            product["id"]: product
            for product in raw_products
        }

        for product_id, quantity in items.items():
            product = products_by_id.get(product_id)

            if product is None:
                raise ValueError(
                    f"Product {product_id} not found"
                )

            new_quantity = (
                int(product.get("inventory_quantity", 0))
                + quantity
            )

            product["inventory_quantity"] = new_quantity
            product["available"] = new_quantity > 0

        _safe_write_json("products.json", raw_products)

        _load_products.cache_clear()