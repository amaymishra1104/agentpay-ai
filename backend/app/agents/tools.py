from __future__ import annotations

from typing import Any, Callable

from app.tools.catalog_tools import (
    compare_products,
    get_product,
    get_related_products,
    search_products,
)
from app.tools.cart_tools import (
    add_to_cart,
    create_cart,
    get_cart,
    remove_from_cart,
    update_cart_item,
    validate_cart,
)
from app.tools.payment_tools import (
    checkout_cart,
    get_order,
    get_order_tracking,
    cancel_order,
    request_return,
)



class BuyerToolError(Exception):
    """Raised when a buyer-agent tool fails."""


def run_tool(
    tool_name: str,
    arguments: dict[str, Any],
) -> Any:
    """Execute an allowlisted buyer-agent tool."""

    tools: dict[str, Callable[..., Any]] = {
        "search_products": search_products,
        "get_product": get_product,
        "get_related_products": get_related_products,
        "compare_products": compare_products,
        "create_cart": create_cart,
        "get_cart": get_cart,
        "add_to_cart": add_to_cart,
        "update_cart_item": update_cart_item,
        "remove_from_cart": remove_from_cart,
        "validate_cart": validate_cart,
        "checkout_cart": checkout_cart,
        "get_order": get_order,
        "get_order_tracking": get_order_tracking,
        "cancel_order": cancel_order,
        "request_return": request_return,
    }

    tool = tools.get(tool_name)

    if tool is None:
        raise BuyerToolError(
            f"Tool '{tool_name}' is not available to the buyer agent."
        )

    try:
        return tool(**arguments)
    except Exception as exc:
        raise BuyerToolError(
            f"Buyer tool '{tool_name}' failed: {exc}"
        ) from exc