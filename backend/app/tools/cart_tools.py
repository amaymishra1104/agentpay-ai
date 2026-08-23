"""Deterministic cart tools reserved for future agent orchestration."""

from app.db.database import SessionLocal
from app.api.routes.cart import map_cart_to_schema
from app.services import cart_service
from app.services.catalog_service import ProductNotFoundError


def create_cart(merchant_id: str, customer_id: str) -> dict:
    """
    Create a new shopping cart for a merchant and customer.

    Args:
        merchant_id (str): The ID of the merchant (e.g., 'm_urbanrun' or 'urbanrun').
        customer_id (str): The ID of the customer.

    Returns:
        dict: The created cart state serialized to a dictionary.
    """
    with SessionLocal() as db:
        try:
            cart = cart_service.create_cart(merchant_id=merchant_id, customer_id=customer_id, db=db)
            return map_cart_to_schema(cart).model_dump()
        except ValueError as exc:
            raise ValueError(f"Failed to create cart: {exc}") from exc


def get_cart(cart_id: str, customer_id: str | None = None) -> dict:
    """
    Retrieve the current state of a shopping cart.

    Args:
        cart_id (str): The unique identifier of the cart.
        customer_id (str, optional): The customer ID.

    Returns:
        dict: The current cart state.
    """
    with SessionLocal() as db:
        cart = cart_service.get_cart(cart_id=cart_id, db=db, customer_id=customer_id)
        if not cart:
            raise ValueError(f"Cart with ID {cart_id} not found")
        return map_cart_to_schema(cart).model_dump()


def add_to_cart(cart_id: str, product_id: str, quantity: int = 1, customer_id: str | None = None) -> dict:
    """
    Add a product to the specified shopping cart.

    Args:
        cart_id (str): The unique identifier of the cart.
        product_id (str): The ID of the product to add.
        quantity (int): The quantity to add (must be greater than 0).
        customer_id (str, optional): The customer ID.

    Returns:
        dict: The updated cart state.
    """
    with SessionLocal() as db:
        try:
            cart = cart_service.add_item_to_cart(
                cart_id=cart_id,
                product_id=product_id,
                quantity=quantity,
                db=db,
                customer_id=customer_id,
            )
            return map_cart_to_schema(cart).model_dump()
        except (
            cart_service.CartNotFoundError,
            ProductNotFoundError,
            cart_service.MerchantMismatchError,
            cart_service.InsufficientInventoryError,
            cart_service.ProductUnavailableError,
            ValueError,
        ) as exc:
            raise ValueError(f"Failed to add item to cart: {exc}") from exc


def update_cart_item(cart_id: str, product_id: str, quantity: int, customer_id: str | None = None) -> dict:
    """
    Update the quantity of a product already in the shopping cart.

    Args:
        cart_id (str): The unique identifier of the cart.
        product_id (str): The ID of the product.
        quantity (int): The new quantity (must be greater than 0).
        customer_id (str, optional): The customer ID.

    Returns:
        dict: The updated cart state.
    """
    with SessionLocal() as db:
        try:
            cart = cart_service.update_item_quantity(
                cart_id=cart_id,
                product_id=product_id,
                quantity=quantity,
                db=db,
                customer_id=customer_id,
            )
            return map_cart_to_schema(cart).model_dump()
        except (
            cart_service.CartNotFoundError,
            ProductNotFoundError,
            cart_service.InsufficientInventoryError,
            ValueError,
        ) as exc:
            raise ValueError(f"Failed to update cart item quantity: {exc}") from exc


def remove_from_cart(cart_id: str, product_id: str, customer_id: str | None = None) -> dict:
    """
    Remove a product line item entirely from the shopping cart.

    Args:
        cart_id (str): The unique identifier of the cart.
        product_id (str): The ID of the product to remove.
        customer_id (str, optional): The customer ID.

    Returns:
        dict: The updated cart state.
    """
    with SessionLocal() as db:
        try:
            cart = cart_service.remove_item_from_cart(
                cart_id=cart_id,
                product_id=product_id,
                db=db,
                customer_id=customer_id,
            )
            return map_cart_to_schema(cart).model_dump()
        except (
            cart_service.CartNotFoundError,
            ProductNotFoundError,
            ValueError,
        ) as exc:
            raise ValueError(f"Failed to remove cart item: {exc}") from exc


def validate_cart(cart_id: str, customer_id: str | None = None) -> dict:
    """
    Perform audit and health checks on the cart state.
    Validates product active status, price snapshots, and inventory limits.

    Args:
        cart_id (str): The unique identifier of the cart.
        customer_id (str, optional): The customer ID.

    Returns:
        dict: Validation results structured as {"valid": bool, "issues": [...]}.
    """
    with SessionLocal() as db:
        try:
            return cart_service.validate_cart(cart_id=cart_id, db=db, customer_id=customer_id)
        except cart_service.CartNotFoundError as exc:
            raise ValueError(f"Failed to validate cart: {exc}") from exc
