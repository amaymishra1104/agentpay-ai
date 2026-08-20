import json
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.catalog_service import _load_products, ProductRecord

client = TestClient(app)


def test_1_create_cart() -> None:
    response = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    assert response.status_code == 201
    payload = response.json()
    assert payload["cart_id"].startswith("cart_")
    assert payload["merchant_id"] == "m_urbanrun"
    assert payload["customer_id"] == "c_demo_001"
    assert payload["subtotal_inr"] == 0
    assert payload["total_inr"] == 150  # Flat rate shipping for < 5000 INR


def test_2_get_cart() -> None:
    # First create a cart
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    response = client.get(f"/api/v1/cart/{cart_id}")
    assert response.status_code == 200
    assert response.json()["cart_id"] == cart_id


def test_3_add_valid_product() -> None:
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    # Add AeroRun X1 (Price: 4499)
    response = client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 1
    })
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["product_id"] == "ur_shoe_001"
    assert payload["items"][0]["quantity"] == 1
    assert payload["subtotal_inr"] == 4499
    assert payload["total_inr"] == 4499 + 150  # 4499 + 150 shipping = 4649


def test_4_add_unavailable_product() -> None:
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    # Velocity Knit (ur_shoe_004) has available: false in seed data
    response = client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_004",
        "quantity": 1
    })
    assert response.status_code == 400
    assert "unavailable" in response.json()["detail"].lower()


def test_5_add_quantity_greater_than_inventory() -> None:
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    # AeroRun X1 has inventory_quantity: 48. Let's request 100.
    response = client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 100
    })
    assert response.status_code == 400
    assert "exceeds available stock" in response.json()["detail"].lower()


def test_6_add_same_product_twice() -> None:
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    # Add 1 unit
    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 1
    })
    # Add another 2 units
    response = client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 2
    })
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["quantity"] == 3
    assert payload["subtotal_inr"] == 4499 * 3


def test_7_update_quantity() -> None:
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 1
    })

    # Update to 5 units
    response = client.patch(f"/api/v1/cart/{cart_id}/items/ur_shoe_001", json={
        "quantity": 5
    })
    assert response.status_code == 200
    assert response.json()["items"][0]["quantity"] == 5


def test_8_remove_product() -> None:
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 1
    })

    response = client.delete(f"/api/v1/cart/{cart_id}/items/ur_shoe_001")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 0


def test_9_clear_cart() -> None:
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 1
    })
    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_002",
        "quantity": 1
    })

    response = client.delete(f"/api/v1/cart/{cart_id}")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 0
    assert response.json()["subtotal_inr"] == 0


def test_10_correct_subtotal() -> None:
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    # ur_shoe_001 (4499) and ur_shoe_002 (5999)
    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 2
    })
    response = client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_002",
        "quantity": 1
    })
    assert response.json()["subtotal_inr"] == (4499 * 2) + 5999


def test_11_correct_discount() -> None:
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    # Hydration Week (10% discount seasonal offer) for hydration items:
    # ur_hyd_001 = 699 INR and ur_sock_001 = 499 INR
    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_hyd_001",
        "quantity": 2
    })
    response = client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_sock_001",
        "quantity": 1
    })
    payload = response.json()
    # Deterministic integer paise calculation: 10% of 699*2 = 139.80 -> 140 INR
    assert payload["discount_inr"] == 140


def test_12_correct_shipping() -> None:
    # 1. Below threshold (5000 INR)
    create_res_1 = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id_1 = create_res_1.json()["cart_id"]
    res_1 = client.post(f"/api/v1/cart/{cart_id_1}/items", json={
        "product_id": "ur_shoe_003",
        "quantity": 1
    }) # Price 3999
    assert res_1.json()["shipping_inr"] == 150

    # 2. Above threshold (5000 INR)
    create_res_2 = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id_2 = create_res_2.json()["cart_id"]
    res_2 = client.post(f"/api/v1/cart/{cart_id_2}/items", json={
        "product_id": "ur_shoe_002",
        "quantity": 1
    }) # Price 5999
    assert res_2.json()["shipping_inr"] == 0


def test_13_correct_final_total() -> None:
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    # ur_shoe_001 (4499) + ur_sock_001 (499) = 4998
    # offer_shoe_socks_combo (12%) discount on eligible shoe + socks:
    # 12% of 4998 = 599.76 INR discount -> 600 INR
    # shipping is 150 (since subtotal 4998 < 5000)
    # total = 4998 - 600 + 150 = 4548
    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 1
    })
    response = client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_sock_001",
        "quantity": 1
    })
    payload = response.json()
    assert payload["subtotal_inr"] == 4998
    assert payload["discount_inr"] == 600
    assert payload["shipping_inr"] == 150
    assert payload["total_inr"] == 4548


def test_14_client_cannot_override_product_price() -> None:
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    # Client tries to pass price fields in request, but API only accepts product_id and quantity
    # We test that prices are always looked up from database.
    # Product AeroRun X1 is 4499 INR in seed data.
    response = client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 1,
        "price": 10.0,
        "unit_price_inr": 10
    })
    assert response.status_code == 200
    assert response.json()["items"][0]["unit_price_inr"] == 4499


def test_15_client_cannot_inject_arbitrary_discount() -> None:
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    response = client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 1,
        "discount_inr": 1000
    })
    assert response.status_code == 200
    assert response.json()["discount_inr"] == 0  # No discount since no offer is met


def test_16_invalid_cart_id_returns_404() -> None:
    response = client.get("/api/v1/cart/does_not_exist")
    assert response.status_code == 404

    response = client.post("/api/v1/cart/does_not_exist/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 1
    })
    assert response.status_code == 404


def test_17_invalid_product_id_returns_404() -> None:
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    response = client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "does_not_exist",
        "quantity": 1
    })
    assert response.status_code == 404


def test_18_cart_validation_detects_inventory_changes() -> None:
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    # Add AeroRun X1 (quantity 10)
    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 10
    })

    # Validate passes initially
    val_res = client.post(f"/api/v1/cart/{cart_id}/validate")
    assert val_res.json()["valid"] is True

    # Mock catalog so product stock is now less than 10
    mock_products = _load_products()
    modified_product = mock_products["ur_shoe_001"].model_copy()
    modified_product.inventory_quantity = 5

    with patch("app.services.cart_service._load_products") as mock_load:
        # Return a copy with reduced stock
        fake_dict = {**mock_products, "ur_shoe_001": modified_product}
        mock_load.return_value = fake_dict

        val_res = client.post(f"/api/v1/cart/{cart_id}/validate")
        assert val_res.json()["valid"] is False
        assert any(issue["type"] == "INVENTORY_CHANGED" for issue in val_res.json()["issues"])


def test_19_cart_validation_detects_price_changes() -> None:
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    # Add AeroRun X1
    client.post(f"/api/v1/cart/{cart_id}/items", json={
        "product_id": "ur_shoe_001",
        "quantity": 1
    })

    # Mock catalog price change
    mock_products = _load_products()
    modified_product = mock_products["ur_shoe_001"].model_copy()
    modified_product.price_inr = 5000

    with patch("app.services.cart_service._load_products") as mock_load:
        fake_dict = {**mock_products, "ur_shoe_001": modified_product}
        mock_load.return_value = fake_dict

        val_res = client.post(f"/api/v1/cart/{cart_id}/validate")
        assert val_res.json()["valid"] is False
        assert any(issue["type"] == "PRICE_CHANGED" for issue in val_res.json()["issues"])


def test_20_merchant_isolation_is_enforced() -> None:
    # Create a cart for merchant "urbanrun"
    create_res = client.post("/api/v1/cart", json={
        "merchant_id": "m_urbanrun",
        "customer_id": "c_demo_001"
    })
    cart_id = create_res.json()["cart_id"]

    # Mock a product from a different merchant
    mock_products = _load_products()
    modified_product = mock_products["ur_shoe_001"].model_copy()
    modified_product.merchant_id = "m_different_merchant"

    with patch("app.services.cart_service._load_products") as mock_load:
        fake_dict = {**mock_products, "ur_shoe_001": modified_product}
        mock_load.return_value = fake_dict

        response = client.post(f"/api/v1/cart/{cart_id}/items", json={
            "product_id": "ur_shoe_001",
            "quantity": 1
        })
        assert response.status_code == 400
        assert "different merchant" in response.json()["detail"].lower()
