from __future__ import annotations

import ast
import json
import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.model import BuyerModel, MockBuyerModel, ToolCall
from app.agents.state import BuyerAgentState
from app.agents.tool_registry import get_buyer_tool_definitions
from app.agents.tools import run_tool


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_LLM_MESSAGES = 16
MAX_SEARCH_PRODUCTS = 6
MAX_RELATED_PRODUCTS = 6
MAX_HISTORICAL_TOOL_CHARS = 12000

# AgentPay's demo catalog currently uses UrbanRun.
# This is application-owned data and must NOT be supplied by the LLM.
DEFAULT_MERCHANT_ID = "m_urbanrun"


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------


def _tool_call_message(
    tool_call: Any,
) -> dict[str, Any]:
    """Convert an internal ToolCall into AgentPay state."""

    return {
        "role": "assistant",
        "type": "tool_call",
        "tool_name": tool_call.tool_name,
        "arguments": tool_call.arguments,
        "tool_call_id": tool_call.tool_call_id,
        "content": None,
    }


def _tool_result_message(
    tool_name: str,
    tool_call_id: str,
    result: Any,
) -> dict[str, Any]:
    """
    Build the model-facing tool result message.

    The model gets a compact representation while the application
    keeps the complete result separately in tool_history.
    """

    compact_result = _compact_tool_result(
        tool_name,
        result,
    )

    return {
        "role": "tool",
        "type": "tool_result",
        "tool_name": tool_name,
        "tool_call_id": tool_call_id,
        "content": json.dumps(
            compact_result,
            ensure_ascii=False,
            default=_json_default,
        ),
    }


def _json_default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value)


# ---------------------------------------------------------------------------
# Product/result compaction
# ---------------------------------------------------------------------------


def _compact_product(product: Any) -> dict[str, Any]:
    """
    Keep only product information the LLM needs for reasoning.
    """

    if hasattr(product, "model_dump"):
        product = product.model_dump(mode="json")

    if not isinstance(product, dict):
        return {
            "value": str(product),
        }

    price = product.get("price") or {}
    availability = product.get("availability") or {}
    rating = product.get("rating") or {}
    shipping = product.get("shipping") or {}

    price_inr = product.get("price_inr")

    if price_inr is None and isinstance(price, dict):
        price_inr = price.get("amount")

    in_stock = product.get("in_stock")

    if in_stock is None and isinstance(availability, dict):
        in_stock = availability.get("in_stock")

    quantity = product.get("quantity")

    if quantity is None and isinstance(availability, dict):
        quantity = availability.get("quantity")

    rating_score = product.get("rating")
    reviews = product.get("reviews")

    if isinstance(rating, dict):
        rating_score = rating.get(
            "score",
            rating_score,
        )
        reviews = rating.get(
            "reviews",
            reviews,
        )

    free_shipping = product.get("free_shipping")

    if free_shipping is None and isinstance(shipping, dict):
        free_shipping = shipping.get("free_shipping")

    estimated_shipping_days = product.get(
        "estimated_shipping_days"
    )

    if (
        estimated_shipping_days is None
        and isinstance(shipping, dict)
    ):
        estimated_shipping_days = shipping.get(
            "estimated_days"
        )

    compact: dict[str, Any] = {
        "product_id": product.get("product_id"),
        "name": product.get("name"),
        "category": product.get("category"),
        "subcategory": product.get("subcategory"),
        "description": product.get("description"),
        "brand": product.get("brand"),
        "price_inr": price_inr,
        "rating": rating_score,
        "reviews": reviews,
        "in_stock": in_stock,
        "quantity": quantity,
        "free_shipping": free_shipping,
        "estimated_shipping_days": estimated_shipping_days,
        "features": product.get(
            "features",
            [],
        ),
    }

    return {
        key: value
        for key, value in compact.items()
        if value is not None
    }


def _compact_tool_result(
    tool_name: str,
    result: Any,
) -> Any:
    """
    Create an LLM-safe representation of a deterministic tool result.

    The complete result remains available to the application/API layer.
    """

    if hasattr(result, "model_dump"):
        result = result.model_dump(mode="json")

    if tool_name == "search_products":

        if not isinstance(result, dict):
            return result

        items = result.get(
            "items",
            [],
        )

        if not isinstance(items, list):
            return {
                "total": result.get(
                    "total",
                    0,
                ),
                "items": [],
            }

        return {
            "total": result.get(
                "total",
                len(items),
            ),
            "items": [
                _compact_product(product)
                for product in items[:MAX_SEARCH_PRODUCTS]
            ],
        }

    if tool_name == "get_product":

        if isinstance(result, dict):
            return _compact_product(result)

        return result

    if tool_name in {
        "get_related_products",
        "compare_products",
    }:

        if isinstance(result, dict):

            items = result.get("items")

            if isinstance(items, list):
                return {
                    "items": [
                        _compact_product(item)
                        for item in items[
                            :MAX_RELATED_PRODUCTS
                        ]
                    ],
                    "total": result.get(
                        "total",
                        len(items),
                    ),
                }

        return result

    # Cart and validation results are normally small enough
    # to preserve completely.
    return result


# ---------------------------------------------------------------------------
# Historical context helpers
# ---------------------------------------------------------------------------


def _message_size(
    message: dict[str, Any],
) -> int:
    content = message.get("content")

    if content is None:
        content = ""

    return len(str(content))


def _build_llm_context(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Keep enough conversation history for multi-turn references.

    We preserve the latest user turn together with the immediately
    preceding tool call/result pair whenever possible.
    """

    if not messages:
        return []

    if len(messages) <= MAX_LLM_MESSAGES:
        return list(messages)

    recent = list(
        messages[-MAX_LLM_MESSAGES:]
    )

    # If we retained a tool result without its corresponding
    # tool call, prepend the matching tool call.
    first = recent[0]

    if (
        first.get("role") == "tool"
        or first.get("type") == "tool_result"
    ):

        tool_call_id = first.get(
            "tool_call_id"
        )

        matching_index: int | None = None

        for index in range(
            len(messages) - 1,
            -1,
            -1,
        ):
            candidate = messages[index]

            if (
                candidate.get("type") == "tool_call"
                and candidate.get("tool_call_id")
                == tool_call_id
            ):
                matching_index = index
                break

        if matching_index is not None:
            start_index = max(
                0,
                matching_index,
            )

            recent = messages[
                start_index : start_index + MAX_LLM_MESSAGES
            ]

    return recent


def _parse_tool_content(
    content: Any,
) -> Any:
    """
    Parse persisted tool-result content.

    Supports JSON first and Python literal fallback because older
    persisted sessions may contain str(dict) representations.
    """

    if not isinstance(content, str):
        return content

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    try:
        return ast.literal_eval(content)
    except (
        SyntaxError,
        ValueError,
    ):
        return content


def _compact_historical_tool_message(
    message: dict[str, Any],
) -> dict[str, Any]:
    """
    Normalize persisted historical tool results.

    Search results are compacted structurally instead of blindly
    truncating JSON in the middle of product records.
    """

    if (
        message.get("role") != "tool"
        and message.get("type") != "tool_result"
    ):
        return message

    tool_name = str(
        message.get(
            "tool_name",
            "",
        )
    )

    content = message.get(
        "content",
        "",
    )

    parsed = _parse_tool_content(
        content
    )

    compacted_result = _compact_tool_result(
        tool_name,
        parsed,
    )

    try:
        serialized = json.dumps(
            compacted_result,
            ensure_ascii=False,
            default=_json_default,
        )
    except (
        TypeError,
        ValueError,
    ):
        serialized = str(
            compacted_result
        )

    # Safety ceiling only after structural compaction.
    if len(serialized) > MAX_HISTORICAL_TOOL_CHARS:
        if isinstance(compacted_result, dict) and "items" in compacted_result and isinstance(compacted_result["items"], list):
            items = list(compacted_result["items"])
            while items and len(serialized) > MAX_HISTORICAL_TOOL_CHARS:
                items.pop()
                compacted_result["items"] = items
                try:
                    serialized = json.dumps(
                        compacted_result,
                        ensure_ascii=False,
                        default=_json_default,
                    )
                except (TypeError, ValueError):
                    serialized = str(compacted_result)
                    break
        elif isinstance(compacted_result, list):
            items = list(compacted_result)
            while items and len(serialized) > MAX_HISTORICAL_TOOL_CHARS:
                items.pop()
                compacted_result = items
                try:
                    serialized = json.dumps(
                        compacted_result,
                        ensure_ascii=False,
                        default=_json_default,
                    )
                except (TypeError, ValueError):
                    serialized = str(compacted_result)
                    break

    if len(serialized) > MAX_HISTORICAL_TOOL_CHARS:
        serialized = (
            serialized[
                :MAX_HISTORICAL_TOOL_CHARS
            ]
            + "\n"
            "[Historical tool-result content "
            "truncated for LLM context.]"
        )

    compacted = dict(message)
    compacted["content"] = serialized

    return compacted


def _prepare_messages_for_llm(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    context = _build_llm_context(
        messages
    )

    return [
        _compact_historical_tool_message(
            message
        )
        for message in context
    ]


def _historical_products(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return products from the latest usable catalog result."""

    for message in reversed(messages):
        if message.get("type") != "tool_result":
            continue

        if message.get("tool_name") not in {
            "search_products",
            "compare_products",
            "get_related_products",
        }:
            continue

        parsed = _parse_tool_content(message.get("content", ""))
        if not isinstance(parsed, dict):
            continue

        items = parsed.get("items", [])
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]

    return []


def _resolve_product_arguments(
    state: BuyerAgentState,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Resolve product references against trusted historical results."""

    if tool_name not in {
        "add_to_cart",
        "remove_from_cart",
        "update_cart_item",
        "get_product",
        "compare_products",
    }:
        return arguments

    products = _historical_products(state.messages)
    if not products:
        return arguments

    text = state.user_message.lower()
    selected: list[dict[str, Any]] = []

    if tool_name == "compare_products":
        selected = products[:2]
    else:
        position = re.search(r"\b(first|second|third|fourth)\b", text)
        positions = {"first": 0, "second": 1, "third": 2, "fourth": 3}
        if position and positions[position.group(1)] < len(products):
            selected = [products[positions[position.group(1)]]]
        else:
            for product in products:
                name = str(product.get("name", "")).lower()
                if name and name in text:
                    selected = [product]
                    break

            if not selected and "cheaper" in text:
                priced = [item for item in products if item.get("price_inr") is not None]
                if priced:
                    selected = [min(priced, key=lambda item: item["price_inr"])]

            if not selected and "highest rated" in text:
                rated = [item for item in products if item.get("rating") is not None]
                if rated:
                    selected = [max(rated, key=lambda item: item["rating"])]

            if not selected and any(word in text for word in ("it", "that", "back")):
                for message in reversed(state.messages):
                    if message.get("type") != "tool_call":
                        continue
                    prior_id = message.get("arguments", {}).get("product_id")
                    selected = [item for item in products if item.get("product_id") == prior_id]
                    if selected:
                        break

    if not selected:
        return arguments

    if tool_name == "compare_products":
        resolved_ids = [item.get("product_id") for item in selected]
        if all(isinstance(product_id, str) for product_id in resolved_ids):
            return {**arguments, "product_ids": resolved_ids}

    product_id = selected[0].get("product_id")
    if isinstance(product_id, str):
        return {**arguments, "product_id": product_id}

    return arguments


# ---------------------------------------------------------------------------
# Trusted application context
# ---------------------------------------------------------------------------


def _inject_trusted_tool_arguments(
    state: BuyerAgentState,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """
    Inject application-owned identity/context into tool calls.

    The LLM can request an action, but it cannot choose:
      - customer_id
      - cart_id
      - merchant_id

    Those values belong to AgentPay's application layer.
    """

    safe_arguments = dict(arguments)

    if tool_name == "create_cart":

        # Never trust customer identity supplied by the model.
        safe_arguments["customer_id"] = (
            state.customer_id
        )

        # Match merchant ID against merchants.json
        from app.services.catalog_service import _load_merchants
        model_merchant_id = arguments.get("merchant_id")
        merchants = _load_merchants()
        matched_merchant_id = DEFAULT_MERCHANT_ID

        if model_merchant_id:
            normalized_model_mid = str(model_merchant_id).lower().strip()
            if normalized_model_mid.startswith("m_"):
                normalized_model_mid = normalized_model_mid[2:]

            for k in merchants:
                norm_k = k.lower().strip()
                if norm_k.startswith("m_"):
                    norm_k = norm_k[2:]
                if norm_k == normalized_model_mid:
                    matched_merchant_id = k
                    break

        safe_arguments["merchant_id"] = matched_merchant_id

    elif tool_name in {
        "add_to_cart",
        "get_cart",
        "update_cart_item",
        "remove_from_cart",
        "validate_cart",
        "checkout_cart",
        "get_order",
        "get_order_tracking",
    }:

        # Never allow the LLM to select another customer's cart.
        if state.cart_id:
            safe_arguments["cart_id"] = (
                state.cart_id
            )

    # Inject customer_id securely only into tools that support it
    if tool_name in {
        "checkout_cart",
        "get_order",
        "get_order_tracking",
        "cancel_order",
        "request_return",
    }:
        safe_arguments["customer_id"] = (
            state.customer_id
        )

    return safe_arguments


def _extract_cart_id(
    result: Any,
) -> str | None:
    """
    Extract cart_id from a cart-related tool result.
    """

    if hasattr(result, "model_dump"):
        result = result.model_dump(
            mode="json"
        )

    if not isinstance(result, dict):
        return None

    cart_id = result.get(
        "cart_id"
    )

    if isinstance(cart_id, str):
        return cart_id

    cart = result.get("cart")

    if isinstance(cart, dict):
        nested_cart_id = cart.get(
            "cart_id"
        )

        if isinstance(
            nested_cart_id,
            str,
        ):
            return nested_cart_id

    return None



def _latest_user_text(state: BuyerAgentState) -> str:
    """Return the current user request in normalized form."""
    if state.user_message:
        return state.user_message.strip().lower()

    for message in reversed(state.messages):
        if message.get("role") == "user":
            return str(message.get("content", "")).strip().lower()

    return ""


def _is_add_to_cart_request(text: str) -> bool:
    """Detect explicit add-to-cart intent without relying on the LLM."""
    add_markers = (
        "add ",
        "add the ",
        "put ",
        "put the ",
        "buy ",
        "buy the ",
    )
    cart_markers = (
        "cart",
        "basket",
    )
    return any(marker in text for marker in add_markers) and any(
        marker in text for marker in cart_markers
    )


def _is_cart_view_request(text: str) -> bool:
    """Detect requests to inspect an existing cart."""
    return (
        "cart" in text
        and any(
            phrase in text
            for phrase in (
                "what's in",
                "what is in",
                "show me",
                "show my",
                "view",
                "see my",
                "see what's",
                "check my",
                "open my",
                "contents",
                "items",
            )
        )
    )


def _select_product_from_history(
    state: BuyerAgentState,
) -> dict[str, Any] | None:
    """
    Resolve the product the user referred to from trusted catalog history.

    This is deliberately application-side. Product references such as
    "the second one" must never depend on an LLM inventing an ID.
    """
    products = _historical_products(state.messages)
    if not products:
        return None

    text = _latest_user_text(state)

    position = re.search(
        r"\b(first|second|third|fourth)\b",
        text,
    )
    positions = {
        "first": 0,
        "second": 1,
        "third": 2,
        "fourth": 3,
    }

    if position:
        index = positions[position.group(1)]
        if index < len(products):
            return products[index]

    for product in products:
        name = str(product.get("name", "")).strip().lower()
        if name and name in text:
            return product

    if "cheaper" in text:
        priced = [
            item
            for item in products
            if isinstance(item.get("price_inr"), (int, float))
        ]
        if priced:
            return min(priced, key=lambda item: item["price_inr"])

    if "highest rated" in text or "best rated" in text:
        rated = [
            item
            for item in products
            if isinstance(item.get("rating"), (int, float))
        ]
        if rated:
            return max(rated, key=lambda item: item["rating"])

    return None


def _has_tool_result_after_latest_user(
    messages: list[dict[str, Any]],
    tool_name: str,
) -> bool:
    latest_user = max(
        (index for index, message in enumerate(messages) if message.get("role") == "user"),
        default=-1,
    )
    return any(
        (message.get("role") == "tool" or message.get("type") == "tool_result")
        and message.get("tool_name") == tool_name
        for message in messages[latest_user + 1 :]
    )


def _build_deterministic_cart_action(
    state: BuyerAgentState,
) -> dict[str, Any] | None:
    """
    Handle high-confidence cart operations before the LLM.

    AgentPay owns cart identity and product-reference resolution. This
    prevents the model from asking the customer for internal IDs or
    accidentally creating a second cart during a multi-turn session.
    """
    text = _latest_user_text(state)

    if _is_cart_view_request(text):
        if _has_tool_result_after_latest_user(state.messages, "get_cart"):
            return None

        if state.cart_id:
            return {
                "tool_calls": [
                    ToolCall(
                        tool_name="get_cart",
                        arguments={"cart_id": state.cart_id},
                        tool_call_id="agentpay_cart_view",
                    )
                ]
            }

        return {
            "final_response": (
                "Your cart is currently empty. "
                "Find a product and ask me to add it to your cart."
            ),
            "messages": [
                {
                    "role": "assistant",
                    "type": "final",
                    "content": (
                        "Your cart is currently empty. "
                        "Find a product and ask me to add it to your cart."
                    ),
                }
            ],
        }

    if not _is_add_to_cart_request(text):
        return None

    if _has_tool_result_after_latest_user(state.messages, "add_to_cart"):
        return None

    product = _select_product_from_history(state)

    if not product:
        return None

    product_id = product.get("product_id")
    if not isinstance(product_id, str) or not product_id:
        return None

    quantity = 1
    quantity_match = re.search(
        r"\b(\d+)\s*(?:x|items?|pairs?)\b",
        text,
    )
    if quantity_match:
        quantity = max(1, int(quantity_match.group(1)))

    return {
        "tool_calls": [
            ToolCall(
                tool_name="add_to_cart",
                arguments={
                    "product_id": product_id,
                    "quantity": quantity,
                    **(
                        {"cart_id": state.cart_id}
                        if state.cart_id
                        else {}
                    ),
                },
                tool_call_id="agentpay_add_to_cart",
            )
        ]
    }

# ---------------------------------------------------------------------------
# Agent node
# ---------------------------------------------------------------------------


def agent_node(
    state: BuyerAgentState,
    model: BuyerModel,
) -> dict[str, Any]:
    """
    Ask the model whether to use a tool or finish.
    """

    # High-confidence shopping/cart actions are resolved by AgentPay
    # before asking the LLM. This keeps internal IDs out of the conversation
    # and makes multi-turn references such as "the second one" reliable.
    deterministic_action = _build_deterministic_cart_action(state)

    if deterministic_action is not None:
        if "tool_calls" in deterministic_action:
            return {
                "messages": [
                    _tool_call_message(call)
                    for call in deterministic_action["tool_calls"]
                ]
            }

        return deterministic_action

    tools = get_buyer_tool_definitions()

    llm_messages = _prepare_messages_for_llm(
        state.messages
    )

    response = model.invoke(
        messages=llm_messages,
        tools=tools,
    )

    if response.has_tool_calls:

        tool_calls = (
            response.tool_calls
            or []
        )

        return {
            "messages": [
                _tool_call_message(
                    call
                )
                for call in tool_calls
            ]
        }

    final_response = (
        response.content
        or ""
    )

    return {
        "final_response": final_response,
        "messages": [
            {
                "role": "assistant",
                "type": "final",
                "content": final_response,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Tool node
# ---------------------------------------------------------------------------


def tool_node(
    state: BuyerAgentState,
) -> dict[str, Any]:
    """
    Execute the requested deterministic AgentPay tool.

    IMPORTANT:
    The LLM only chooses the action and user-facing parameters.
    Trusted identity/context is injected by the application.
    """

    if not state.messages:
        return {}

    last_message = state.messages[-1]

    if last_message.get("type") != "tool_call":
        return {}

    tool_name = str(
        last_message.get(
            "tool_name",
            "",
        )
    )

    raw_arguments = last_message.get(
        "arguments",
        {},
    )

    if not isinstance(
        raw_arguments,
        dict,
    ):
        raw_arguments = {}

    raw_arguments = _resolve_product_arguments(
        state,
        tool_name,
        raw_arguments,
    )

    tool_call_id = str(
        last_message.get(
            "tool_call_id",
            "agentpay_tool_call",
        )
    )

    # ---------------------------------------------------------------
    # Trusted argument injection
    # ---------------------------------------------------------------

    arguments = _inject_trusted_tool_arguments(
        state=state,
        tool_name=tool_name,
        arguments=raw_arguments,
    )

    # ---------------------------------------------------------------
    # Automatic cart creation
    # ---------------------------------------------------------------

    # If the user asks to add something and there is no cart yet,
    # AgentPay creates the cart itself.
    #
    # This prevents the LLM from having to reason about cart
    # lifecycle or ask the user for internal IDs.
    if (
        tool_name == "add_to_cart"
        and not state.cart_id
    ):

        if not state.customer_id:
            raise ValueError(
                "A customer identity is required "
                "before creating a cart."
            )

        # Resolve merchant_id from actual product record
        from app.services.catalog_service import _load_products
        product_id = arguments.get("product_id")
        products = _load_products()
        product = products.get(product_id)
        merchant_id = product.merchant_id if product else DEFAULT_MERCHANT_ID

        created_cart = run_tool(
            "create_cart",
            {
                "merchant_id": merchant_id,
                "customer_id": state.customer_id,
            },
        )

        new_cart_id = _extract_cart_id(
            created_cart
        )

        if not new_cart_id:
            raise ValueError(
                "Cart creation succeeded without "
                "returning a cart_id."
            )

        # Update the add-to-cart request with the
        # newly created trusted cart ID.
        arguments["cart_id"] = new_cart_id

        # Execute the actual requested operation.
        result = run_tool(
            tool_name,
            arguments,
        )

        # Preserve both operations in history.
        create_history_item = {
            "tool_name": "create_cart",
            "arguments": {
                "merchant_id": merchant_id,
                "customer_id": state.customer_id,
            },
            "result": created_cart,
        }

        add_history_item = {
            "tool_name": tool_name,
            "arguments": arguments,
            "result": result,
        }

        model_result = _compact_tool_result(
            tool_name,
            result,
        )

        return {
            "cart_id": new_cart_id,
            "last_tool_result": {
                "tool_name": tool_name,
                "result": result,
            },
            "tool_history": [
                create_history_item,
                add_history_item,
            ],
            "messages": [
                {
                    "role": "tool",
                    "type": "tool_result",
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(
                        model_result,
                        ensure_ascii=False,
                        default=_json_default,
                    ),
                }
            ],
        }

    # ---------------------------------------------------------------
    # Normal tool execution
    # ---------------------------------------------------------------

    result = run_tool(
        tool_name,
        arguments,
    )

    # ---------------------------------------------------------------
    # Persist newly created cart IDs in graph state
    # ---------------------------------------------------------------

    cart_id = state.cart_id

    if tool_name == "create_cart":
        created_cart_id = _extract_cart_id(
            result
        )

        if created_cart_id:
            cart_id = created_cart_id

    elif tool_name in {
        "add_to_cart",
        "update_cart_item",
        "remove_from_cart",
    }:
        result_cart_id = _extract_cart_id(
            result
        )

        if result_cart_id:
            cart_id = result_cart_id

    # Preserve the complete result for API/application consumers.
    tool_history_item = {
        "tool_name": tool_name,
        "arguments": arguments,
        "result": result,
    }

    model_result = _compact_tool_result(
        tool_name,
        result,
    )

    return {
        "cart_id": cart_id,
        "last_tool_result": {
            "tool_name": tool_name,
            "result": result,
        },
        "tool_history": [
            tool_history_item
        ],
        "messages": [
            {
                "role": "tool",
                "type": "tool_result",
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "content": json.dumps(
                    model_result,
                    ensure_ascii=False,
                    default=_json_default,
                ),
            }
        ],
    }


# ---------------------------------------------------------------------------
# Graph routing
# ---------------------------------------------------------------------------


def route_after_agent(
    state: BuyerAgentState,
) -> str:
    """
    Route tool calls to the tool node; otherwise finish.
    """

    if not state.messages:
        return END

    if (
        state.messages[-1].get("type")
        == "tool_call"
    ):
        return "tool"

    return END


def route_after_tool(
    state: BuyerAgentState,
) -> str:
    """
    Return to the model after deterministic tool execution.
    """

    if state.last_tool_result is not None:
        return "agent"

    return END


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def create_agent_node(
    model: BuyerModel,
):
    """
    Bind a model instance to a LangGraph node.
    """

    def node(
        state: BuyerAgentState,
    ) -> dict[str, Any]:

        return agent_node(
            state,
            model,
        )

    return node


def build_buyer_graph(
    model: BuyerModel | None = None,
):
    """
    Build the AgentPay Buyer Agent graph.

    No model means deterministic MockBuyerModel.
    Production can inject GroqBuyerModel.
    """

    if model is None:
        model = MockBuyerModel()

    graph = StateGraph(
        BuyerAgentState
    )

    graph.add_node(
        "agent",
        create_agent_node(
            model
        ),
    )

    graph.add_node(
        "tool",
        tool_node,
    )

    graph.add_edge(
        START,
        "agent",
    )

    graph.add_conditional_edges(
        "agent",
        route_after_agent,
        {
            "tool": "tool",
            END: END,
        },
    )

    graph.add_conditional_edges(
        "tool",
        route_after_tool,
        {
            "agent": "agent",
            END: END,
        },
    )

    return graph.compile()