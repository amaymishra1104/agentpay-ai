from __future__ import annotations

from copy import deepcopy
from typing import Any


BUYER_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_products",
        "description": (
            "Search the UrbanRun product catalog using optional "
            "query, category, price, rating, and stock filters. "
            "Use this when the buyer is looking for products."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Natural-language product search query, "
                        "such as 'running shoes' or 'trail shoes'."
                    ),
                },
                "category": {
                    "type": "string",
                    "description": "Product category to filter by.",
                },
                "min_price": {
                    "type": "integer",
                    "description": "Minimum product price in INR.",
                },
                "max_price": {
                    "type": "integer",
                    "description": "Maximum product price in INR.",
                },
                "min_rating": {
                    "type": "number",
                    "description": "Minimum acceptable product rating.",
                },
                "in_stock": {
                    "type": "boolean",
                    "description": (
                        "Whether to restrict results to products "
                        "currently in stock."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "Maximum number of products to return."
                    ),
                    "default": 20,
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_product",
        "description": (
            "Get authoritative details for a specific UrbanRun "
            "product using its product ID."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "description": "The UrbanRun product ID.",
                },
            },
            "required": ["product_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_related_products",
        "description": (
            "Find complementary, upsell, and alternative products "
            "related to a specific product."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "description": "The source product ID.",
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "Maximum number of related products to return."
                    ),
                    "default": 6,
                },
            },
            "required": ["product_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "compare_products",
        "description": (
            "Compare multiple UrbanRun products using structured "
            "catalog information."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product_ids": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                    "description": "List of product IDs to compare.",
                },
            },
            "required": ["product_ids"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_cart",
        "description": (
            "Create a new shopping cart for the current buyer "
            "and UrbanRun merchant."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "merchant_id": {
                    "type": "string",
                    "description": "The merchant ID.",
                },
                "customer_id": {
                    "type": "string",
                    "description": "The buyer's customer ID.",
                },
            },
            "required": ["merchant_id", "customer_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_cart",
        "description": (
            "Retrieve the current state of an existing shopping cart."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cart_id": {
                    "type": "string",
                    "description": "The shopping cart ID.",
                },
            },
            "required": ["cart_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "add_to_cart",
        "description": (
            "Add a product to an existing cart. The server obtains "
            "the authoritative product price and validates inventory."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cart_id": {
                    "type": "string",
                    "description": "The shopping cart ID.",
                },
                "product_id": {
                    "type": "string",
                    "description": "The product ID to add.",
                },
                "quantity": {
                    "type": "integer",
                    "description": "Number of units to add.",
                    "default": 1,
                },
            },
            "required": ["cart_id", "product_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_cart_item",
        "description": (
            "Change the quantity of an existing cart item. "
            "The server validates inventory and recalculates totals."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cart_id": {
                    "type": "string",
                    "description": "The shopping cart ID.",
                },
                "product_id": {
                    "type": "string",
                    "description": "The product ID.",
                },
                "quantity": {
                    "type": "integer",
                    "description": "The new quantity for the cart item.",
                },
            },
            "required": [
                "cart_id",
                "product_id",
                "quantity",
            ],
            "additionalProperties": False,
        },
    },
    {
        "name": "remove_from_cart",
        "description": (
            "Remove a product completely from an existing shopping cart."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cart_id": {
                    "type": "string",
                    "description": "The shopping cart ID.",
                },
                "product_id": {
                    "type": "string",
                    "description": "The product ID to remove.",
                },
            },
            "required": ["cart_id", "product_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "validate_cart",
        "description": (
            "Validate a shopping cart against current product "
            "availability, prices, and inventory."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cart_id": {
                    "type": "string",
                    "description": "The shopping cart ID.",
                },
            },
            "required": ["cart_id"],
            "additionalProperties": False,
        },
    },
]


def get_buyer_tool_definitions() -> list[dict[str, Any]]:
    """
    Return independent copies of all Buyer Agent tool definitions.
    """

    return deepcopy(BUYER_TOOL_DEFINITIONS)


def get_buyer_tool_names() -> list[str]:
    """
    Return the names of all tools available to the Buyer Agent.
    """

    return [
        str(tool["name"])
        for tool in BUYER_TOOL_DEFINITIONS
    ]


def get_buyer_tool_definition(
    tool_name: str,
) -> dict[str, Any] | None:
    """
    Return an independent copy of one Buyer Agent tool definition.
    """

    for tool in BUYER_TOOL_DEFINITIONS:
        if tool["name"] == tool_name:
            return deepcopy(tool)

    return None