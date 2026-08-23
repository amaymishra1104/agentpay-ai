import os
os.environ["DATABASE_URL"] = "sqlite:///./agentpay.db"

import pytest
from app.services.catalog_service import get_cross_sell_recommendations, ProductNotFoundError
from app.tools.catalog_tools import get_cross_sell_recommendations as tool_get_cross_sell


def test_cross_sell_recommendations_for_shoe():
    result = get_cross_sell_recommendations("ur_shoe_001")
    assert result["source_product_id"] == "ur_shoe_001"
    assert result["source_product_name"] == "AeroRun X1"
    assert len(result["recommendations"]) > 0

    first_rec = result["recommendations"][0]
    assert "product_id" in first_rec
    assert "explanation" in first_rec
    assert "Recommended because" in first_rec["explanation"]


def test_cross_sell_recommendations_for_laptop():
    result = get_cross_sell_recommendations("ur_comp_001")
    assert result["source_product_id"] == "ur_comp_001"
    assert len(result["recommendations"]) > 0

    for rec in result["recommendations"]:
        assert "explanation" in rec
        assert "Recommended because" in rec["explanation"]


def test_cross_sell_invalid_product():
    with pytest.raises(ProductNotFoundError):
        get_cross_sell_recommendations("non_existent_product")


def test_cross_sell_tool_wrapper():
    res = tool_get_cross_sell("ur_shoe_001")
    assert res["source_product_id"] == "ur_shoe_001"
    assert isinstance(res["recommendations"], list)
