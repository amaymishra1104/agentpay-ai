import os
os.environ["DATABASE_URL"] = "sqlite:///./agentpay.db"

import json

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_search_by_query() -> None:
    response = client.get("/api/v1/catalog/products", params={"query": "running shoes"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] > 0
    assert any(item["category"] == "running_shoes" for item in payload["items"])


def test_search_by_price() -> None:
    response = client.get("/api/v1/catalog/products", params={"max_price": 500})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] > 0
    assert all(item["price"]["amount"] <= 500 for item in payload["items"])


def test_search_by_rating() -> None:
    response = client.get("/api/v1/catalog/products", params={"min_rating": 4.8})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] > 0
    assert all(item["rating"]["score"] >= 4.8 for item in payload["items"])


def test_search_by_category() -> None:
    response = client.get("/api/v1/catalog/products", params={"category": "running_belts"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] > 0
    assert all(item["category"] == "running_belts" for item in payload["items"])


def test_out_of_stock_filtering() -> None:
    response = client.get("/api/v1/catalog/products", params={"in_stock": True, "limit": 100})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] > 0
    assert all(item["availability"]["in_stock"] is True for item in payload["items"])


def test_product_lookup() -> None:
    response = client.get("/api/v1/catalog/products/ur_shoe_001")
    assert response.status_code == 200
    payload = response.json()
    assert payload["product_id"] == "ur_shoe_001"
    assert payload["name"] == "AeroRun X1"


def test_related_products() -> None:
    response = client.get("/api/v1/catalog/products/ur_shoe_001/related")
    assert response.status_code == 200
    payload = response.json()
    assert payload["product_id"] == "ur_shoe_001"
    assert len(payload["complementary"]) > 0
    assert len(payload["upsell"]) > 0


def test_product_comparison() -> None:
    response = client.post(
        "/api/v1/catalog/products/compare",
        json=["ur_shoe_001", "ur_shoe_002", "ur_watch_001"],
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 3
    assert payload["items"][0]["product_id"] == "ur_shoe_001"


def test_cost_never_exposed() -> None:
    search_response = client.get("/api/v1/catalog/products", params={"limit": 5})
    detail_response = client.get("/api/v1/catalog/products/ur_shoe_001")
    compare_response = client.post(
        "/api/v1/catalog/products/compare",
        json=["ur_shoe_001", "ur_shoe_002"],
    )

    assert search_response.status_code == 200
    assert detail_response.status_code == 200
    assert compare_response.status_code == 200

    combined_payload = json.dumps(
        [search_response.json(), detail_response.json(), compare_response.json()]
    )
    assert "cost_inr" not in combined_payload


def test_invalid_product_id_returns_404() -> None:
    response = client.get("/api/v1/catalog/products/does_not_exist")
    assert response.status_code == 404
