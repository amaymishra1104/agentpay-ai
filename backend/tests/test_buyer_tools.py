from app.agents.tools import BuyerToolError, run_tool


def test_search_products_tool():
    result = run_tool(
        "search_products",
        {
            "query": "running shoes",
            "max_price": 5000,
            "min_rating": 4.0,
            "limit": 5,
        },
    )

    assert result is not None
    assert hasattr(result, "items")


def test_get_product_tool():
    result = run_tool(
        "get_product",
        {"product_id": "ur_shoe_001"},
    )

    assert result is not None


def test_unknown_tool_is_rejected():
    try:
        run_tool("delete_database", {})
        assert False, "Unknown tool should have been rejected"
    except BuyerToolError as exc:
        assert "not available" in str(exc)