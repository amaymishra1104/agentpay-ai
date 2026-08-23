"""Cart service containing shopping cart business logic."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.orm import Session

from app.db.models import Cart, CartItem
from app.policies.shipping_policy import ShippingPolicy
from app.services.catalog_service import _load_products, _load_merchants, ProductNotFoundError


class CartNotFoundError(ValueError):
    """Raised when a cart is not found in database."""


class MerchantMismatchError(ValueError):
    """Raised when adding a product from a different merchant to a cart."""


class InsufficientInventoryError(ValueError):
    """Raised when adding more units than are available in stock."""


class ProductUnavailableError(ValueError):
    """Raised when adding an unavailable product."""


def _normalize_merchant_id(val: str) -> str:
    val = val.lower().strip()
    if val.startswith("m_"):
        return val[2:]
    return val


def _data_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data"


def _load_offers() -> list[dict]:
    filepath = _data_dir() / "offers.json"
    with filepath.open("r", encoding="utf-8") as file:
        return json.load(file)


def _load_customers() -> list[dict]:
    filepath = _data_dir() / "customers.json"
    with filepath.open("r", encoding="utf-8") as file:
        return json.load(file)


def evaluate_offers(cart_items: list[CartItem]) -> list[dict]:
    """
    Deterministic offer evaluation logic based on items in the cart.
    Returns a list of applied offer summaries.
    """
    all_offers = _load_offers()
    cart_product_ids = {item.product_id for item in cart_items}

    # Evaluate which offers meet their eligibility conditions
    applicable_offers = []
    for offer in all_offers:
        offer_id = offer["id"]
        offer_pids = set(offer.get("product_ids", []))
        matching_pids = cart_product_ids.intersection(offer_pids)
        if not matching_pids:
            continue

        is_applicable = False

        if offer_id == "offer_shoe_socks_combo":
            # Requires at least one shoe and one sock
            has_shoe = any(pid.startswith("ur_shoe_") for pid in matching_pids)
            has_sock = any(pid.startswith("ur_sock_") for pid in matching_pids)
            if has_shoe and has_sock:
                is_applicable = True

        elif offer_id == "offer_trail_kit":
            # Requires at least 2 distinct products from the trail kit
            if len(matching_pids) >= 2:
                is_applicable = True

        elif offer_id == "offer_watch_upgrade":
            # Requires at least 1 watch in matching_pids
            if any(pid.startswith("ur_watch_") for pid in matching_pids):
                is_applicable = True

        elif offer_id == "offer_hydration_week":
            # Applies unconditionally to any hydration/belt product in matching_pids
            is_applicable = True

        elif offer_id == "offer_recovery_bundle":
            # Requires at least 2 distinct recovery items
            if len(matching_pids) >= 2:
                is_applicable = True

        elif offer_id == "offer_marathon_prep":
            # Requires at least 3 distinct marathon prep items
            if len(matching_pids) >= 3:
                is_applicable = True

        if is_applicable:
            applicable_offers.append(offer)

    # For each product, select the offer that gives the highest discount percent
    product_best_offer: dict[str, tuple[int, dict]] = {}  # product_id -> (discount_percent, offer)
    for offer in applicable_offers:
        discount_percent = offer["discount_percent"]
        for pid in cart_product_ids.intersection(set(offer.get("product_ids", []))):
            current_best = product_best_offer.get(pid, (0, {}))[0]
            if discount_percent > current_best:
                product_best_offer[pid] = (discount_percent, offer)

    # Calculate discount in paise per offer to aggregate
    offer_discounts: dict[str, int] = {}
    offer_details: dict[str, dict] = {}
    for item in cart_items:
        if item.product_id in product_best_offer:
            discount_percent, offer = product_best_offer[item.product_id]
            line_subtotal_paise = item.unit_price_inr * 100 * item.quantity
            item_discount_paise = (line_subtotal_paise * discount_percent) // 100

            offer_id = offer["id"]
            offer_discounts[offer_id] = offer_discounts.get(offer_id, 0) + item_discount_paise
            offer_details[offer_id] = offer

    applied_offers = []
    for offer_id, discount_paise in offer_discounts.items():
        offer = offer_details[offer_id]
        applied_offers.append({
            "offer_id": offer_id,
            "name": offer["title"],
            "discount_type": offer["type"],
            "discount_amount_inr": round(discount_paise / 100.0),
            "reason": f"Applied {offer['discount_percent']}% discount to eligible items",
            "discount_amount_paise": discount_paise,
        })
    return applied_offers


def recalculate_cart(cart: Cart) -> None:
    """
    Recalculates cart subtotal, shipping, discounts, and total in a deterministic manner.
    Keeps all financial operations precise using paise/integers and rounds at the boundary.
    """
    subtotal_paise = 0
    all_products = _load_products()

    for item in cart.items:
        product = all_products.get(item.product_id)
        if product:
            item.name = product.name
            item.sku = product.sku
            item.unit_price_inr = product.price_inr
            item.available = product.available and product.inventory_quantity > 0
            item.inventory_checked = True
            item.line_total_inr = item.unit_price_inr * item.quantity
            subtotal_paise += item.line_total_inr * 100
        else:
            item.available = False
            item.line_total_inr = 0

    # Calculate discounts
    applied = evaluate_offers(cart.items)
    discount_paise = sum(offer["discount_amount_paise"] for offer in applied)
    cart.applied_offers_json = json.dumps([
        {k: v for k, v in offer.items() if k != "discount_amount_paise"}
        for offer in applied
    ])

    # Calculate shipping
    subtotal_inr = round(subtotal_paise / 100.0)
    shipping_policy = ShippingPolicy()
    shipping_inr = shipping_policy.calculate_shipping(subtotal_inr)
    shipping_paise = shipping_inr * 100

    total_paise = max(0, subtotal_paise - discount_paise + shipping_paise)

    # Store integer Rupee values at database boundary
    cart.subtotal_inr = subtotal_inr
    cart.discount_inr = round(discount_paise / 100.0)
    cart.shipping_inr = shipping_inr
    cart.total_inr = round(total_paise / 100.0)
    cart.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)


def create_cart(merchant_id: str, customer_id: str, db: Session) -> Cart:
    """Creates and stores a new cart in the database."""
    # Validate merchant exists
    merchants = _load_merchants()
    normalized_m_id = _normalize_merchant_id(merchant_id)
    merchant_key = None
    for k in merchants:
        if _normalize_merchant_id(k) == normalized_m_id:
            merchant_key = k
            break

    if not merchant_key:
        raise ValueError(f"Merchant not found: {merchant_id}")

    cart_id = f"cart_{uuid.uuid4().hex[:12]}"
    cart = Cart(
        id=cart_id,
        merchant_id=merchant_key,
        customer_id=customer_id,
        currency="INR",
        status="active",
        subtotal_inr=0,
        discount_inr=0,
        shipping_inr=0,
        total_inr=0,
        applied_offers_json="[]",
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(cart)
    recalculate_cart(cart)
    db.commit()
    db.refresh(cart)
    return cart


def get_cart(cart_id: str, db: Session, customer_id: str | None = None) -> Cart | None:
    """Retrieves a cart by ID."""
    cart = db.query(Cart).filter(Cart.id == cart_id).first()
    if not cart:
        return None
    if customer_id is not None and cart.customer_id != customer_id:
        raise PermissionError("Access denied: You do not have permission to access this cart")
    return cart


def add_item_to_cart(cart_id: str, product_id: str, quantity: int, db: Session, customer_id: str | None = None) -> Cart:
    """Adds a product to the cart or increments its quantity if it already exists."""
    cart = get_cart(cart_id, db, customer_id)
    if not cart:
        raise CartNotFoundError(f"Cart {cart_id} not found")

    if cart.status != "active":
        raise ValueError("Cart is not active")

    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero")

    # Fetch authoritative catalog product
    products = _load_products()
    product = products.get(product_id)
    if not product:
        raise ProductNotFoundError(f"Product {product_id} not found")

    # Verify merchant matches
    if _normalize_merchant_id(product.merchant_id) != _normalize_merchant_id(cart.merchant_id):
        raise MerchantMismatchError(
            f"Product {product_id} belongs to a different merchant than this cart. "
            f"Catalog merchant is {product.merchant_id}; cart merchant is {cart.merchant_id}."
        )

    # Verify product is available
    if not product.available:
        raise ProductUnavailableError(f"Product {product_id} is marked unavailable")

    # Check current quantity in cart to check against total inventory
    existing_item = next((item for item in cart.items if item.product_id == product_id), None)
    new_quantity = quantity
    if existing_item:
        new_quantity += existing_item.quantity

    if product.inventory_quantity < new_quantity:
        raise InsufficientInventoryError(
            f"Requested quantity {new_quantity} exceeds available stock {product.inventory_quantity}"
        )

    if existing_item:
        existing_item.quantity = new_quantity
    else:
        cart_item = CartItem(
            cart_id=cart.id,
            product_id=product.id,
            sku=product.sku,
            name=product.name,
            unit_price_inr=product.price_inr,
            quantity=quantity,
            line_total_inr=product.price_inr * quantity,
            available=True,
            inventory_checked=True,
        )
        cart.items.append(cart_item)

    recalculate_cart(cart)
    db.commit()
    db.refresh(cart)
    return cart


def update_item_quantity(cart_id: str, product_id: str, quantity: int, db: Session, customer_id: str | None = None) -> Cart:
    """Updates the quantity of a product in the cart."""
    cart = get_cart(cart_id, db, customer_id)
    if not cart:
        raise CartNotFoundError(f"Cart {cart_id} not found")

    if cart.status != "active":
        raise ValueError("Cart is not active")

    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero")

    existing_item = next((item for item in cart.items if item.product_id == product_id), None)
    if not existing_item:
        raise ProductNotFoundError(f"Product {product_id} not found in cart")

    products = _load_products()
    product = products.get(product_id)
    if not product:
        raise ProductNotFoundError(f"Product {product_id} not found in catalog")

    # Check inventory
    if product.inventory_quantity < quantity:
        raise InsufficientInventoryError(
            f"Requested quantity {quantity} exceeds available stock {product.inventory_quantity}"
        )

    existing_item.quantity = quantity
    recalculate_cart(cart)
    db.commit()
    db.refresh(cart)
    return cart


def remove_item_from_cart(cart_id: str, product_id: str, db: Session, customer_id: str | None = None) -> Cart:
    """Removes a product from the cart."""
    cart = get_cart(cart_id, db, customer_id)
    if not cart:
        raise CartNotFoundError(f"Cart {cart_id} not found")

    if cart.status != "active":
        raise ValueError("Cart is not active")

    existing_item = next((item for item in cart.items if item.product_id == product_id), None)
    if not existing_item:
        raise ProductNotFoundError(f"Product {product_id} not found in cart")

    cart.items.remove(existing_item)
    recalculate_cart(cart)
    db.commit()
    db.refresh(cart)
    return cart


def clear_cart(cart_id: str, db: Session, customer_id: str | None = None) -> Cart:
    """Removes all items from the cart and resets totals."""
    cart = get_cart(cart_id, db, customer_id)
    if not cart:
        raise CartNotFoundError(f"Cart {cart_id} not found")

    if cart.status != "active":
        raise ValueError("Cart is not active")

    cart.items.clear()
    recalculate_cart(cart)
    db.commit()
    db.refresh(cart)
    return cart


def validate_cart(
    cart_id: str,
    db: Session,
    customer_id: str | None = None,
    merchant_id: str | None = None,
) -> dict:
    """
    Validates a cart against the current state of products, inventory, and status.
    Returns a dict with 'valid' and a list of 'issues'.
    """
    cart = get_cart(cart_id, db)
    if not cart:
        raise CartNotFoundError(f"Cart {cart_id} not found")

    issues = []

    if cart.status != "active":
        issues.append({
            "type": "CART_INACTIVE",
            "message": "Cart is not active.",
        })
        return {"valid": False, "issues": issues}

    if not cart.items or len(cart.items) == 0:
        issues.append({
            "type": "CART_EMPTY",
            "message": "Cart is empty.",
        })

    if customer_id and cart.customer_id != customer_id:
        issues.append({
            "type": "CUSTOMER_MISMATCH",
            "message": "Customer ID does not match cart.",
        })

    if merchant_id and cart.merchant_id != merchant_id:
        issues.append({
            "type": "MERCHANT_MISMATCH",
            "message": "Merchant ID does not match cart.",
        })

    products = _load_products()

    for item in cart.items:
        product = products.get(item.product_id)
        if not product:
            issues.append({
                "type": "PRODUCT_UNAVAILABLE",
                "product_id": item.product_id,
                "message": f"Product {item.name} is no longer available in the catalog.",
            })
            continue

        if not product.available:
            issues.append({
                "type": "PRODUCT_UNAVAILABLE",
                "product_id": item.product_id,
                "message": f"Product {item.name} is out of stock/unavailable.",
            })
            continue

        if product.inventory_quantity < item.quantity:
            issues.append({
                "type": "INVENTORY_CHANGED",
                "product_id": item.product_id,
                "message": f"Only {product.inventory_quantity} units remain.",
            })

        if product.price_inr != item.unit_price_inr:
            issues.append({
                "type": "PRICE_CHANGED",
                "product_id": item.product_id,
                "message": f"Price of {item.name} changed from {item.unit_price_inr} INR to {product.price_inr} INR.",
            })

    return {
        "valid": len(issues) == 0,
        "issues": issues,
    }

