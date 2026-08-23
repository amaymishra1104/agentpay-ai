from app.agents.tool_registry import (
    get_buyer_tool_definition,
    get_buyer_tool_definitions,
    get_buyer_tool_names,
)


EXPECTED_TOOLS = {
    "search_products",
    "get_product",
    "get_related_products",
    "get_cross_sell_recommendations",
    "compare_products",
    "create_cart",
    "get_cart",
    "add_to_cart",
    "update_cart_item",
    "remove_from_cart",
    "validate_cart",
    "checkout_cart",
    "get_order",
    "get_order_tracking",
    "cancel_order",
    "request_return",
}


def test_buyer_registry_contains_expected_tools():
    names = set(get_buyer_tool_names())

    assert names == EXPECTED_TOOLS


def test_buyer_registry_returns_definitions():
    definitions = get_buyer_tool_definitions()

    assert len(definitions) == len(EXPECTED_TOOLS)

    for definition in definitions:
        assert "name" in definition
        assert "description" in definition
        assert "parameters" in definition

        assert (
            definition["parameters"]["type"]
            == "object"
        )


def test_search_products_definition():
    definition = get_buyer_tool_definition(
        "search_products"
    )

    assert definition is not None

    properties = definition["parameters"]["properties"]

    assert "query" in properties
    assert "category" in properties
    assert "min_price" in properties
    assert "max_price" in properties
    assert "min_rating" in properties
    assert "in_stock" in properties
    assert "limit" in properties


def test_add_to_cart_definition():
    definition = get_buyer_tool_definition(
        "add_to_cart"
    )

    assert definition is not None

    required = set(
        definition["parameters"]["required"]
    )

    assert required == {
        "cart_id",
        "product_id",
    }


def test_unknown_tool_definition_returns_none():
    result = get_buyer_tool_definition(
        "charge_credit_card"
    )

    assert result is None


def test_registry_returns_independent_definition_list():
    first = get_buyer_tool_definitions()
    first[0]["name"] = "tampered_tool"

    second = get_buyer_tool_definitions()

    assert second[0]["name"] == "search_products"