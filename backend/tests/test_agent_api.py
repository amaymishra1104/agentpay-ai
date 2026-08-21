from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings
from app.services.agent_session_service import get_messages


client = TestClient(app)


def new_session_id() -> str:
    return f"api-session-{uuid4().hex}"


def configure_mock_provider(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    get_settings.cache_clear()


def test_buyer_agent_chat_with_mock_model(
    monkeypatch,
):
    configure_mock_provider(monkeypatch)

    identifier = new_session_id()

    response = client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": identifier,
            "customer_id": "c_demo_001",
            "message": (
                "I need running shoes "
                "under 5000"
            ),
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert (
        data["session_id"]
        == identifier
    )

    assert data["response"]

    assert (
        data["tool_used"]
        == "search_products"
    )

    assert (
        data["tool_result"]
        is not None
    )


def test_buyer_agent_persists_multi_turn_conversation(monkeypatch):
    configure_mock_provider(monkeypatch)
    identifier = new_session_id()

    first = client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": identifier,
            "customer_id": "c_demo_001",
            "message": "I need running shoes under 5000",
        },
    )
    second = client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": identifier,
            "customer_id": "c_demo_001",
            "message": "Compare the first two",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["tool_used"] == "compare_products"
    assert second.json()["response"]

    messages = get_messages(identifier)
    assert any(message.role == "user" for message in messages)
    assert any(message.message_type == "tool_call" for message in messages)
    assert any(message.message_type == "tool_result" for message in messages)
    assert len(messages) >= 8


def test_buyer_agent_adds_referenced_search_product(monkeypatch):
    configure_mock_provider(monkeypatch)
    identifier = new_session_id()

    first = client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": identifier,
            "customer_id": "c_demo_001",
            "message": "I need running shoes under 5000",
        },
    )
    first_product_id = first.json()["tool_result"]["result"]["items"][0][
        "product_id"
    ]

    second = client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": identifier,
            "customer_id": "c_demo_001",
            "message": "Add the first one to my cart",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["response"]
    assert second.json()["cart_id"]

    messages = get_messages(identifier)
    add_calls = [
        message
        for message in messages
        if message.message_type == "tool_call"
        and message.tool_name == "add_to_cart"
    ]
    assert add_calls
    assert first_product_id in add_calls[-1].content


def test_buyer_agent_adds_second_product_and_reuses_cart(monkeypatch):
    configure_mock_provider(monkeypatch)
    identifier = new_session_id()
    request = {
        "session_id": identifier,
        "customer_id": "c_demo_001",
    }

    search = client.post(
        "/api/v1/agent/chat",
        json={**request, "message": "I need running shoes under 5000"},
    )
    products = search.json()["tool_result"]["result"]["items"]
    first_product_id = products[0]["product_id"]
    second_product_id = products[1]["product_id"]

    first_add = client.post(
        "/api/v1/agent/chat",
        json={**request, "message": "Add the first one to my cart"},
    )
    second_add = client.post(
        "/api/v1/agent/chat",
        json={**request, "message": "Add the second one to my cart"},
    )

    assert first_add.status_code == 200
    assert second_add.status_code == 200
    assert second_add.json()["cart_id"] == first_add.json()["cart_id"]

    messages = get_messages(identifier)
    add_calls = [
        message
        for message in messages
        if message.message_type == "tool_call"
        and message.tool_name == "add_to_cart"
    ]
    assert len(add_calls) == 2
    assert first_product_id in add_calls[0].content
    assert second_product_id in add_calls[1].content


def test_buyer_agent_returns_actual_cart_contents(monkeypatch):
    configure_mock_provider(monkeypatch)
    identifier = new_session_id()
    request = {
        "session_id": identifier,
        "customer_id": "c_demo_001",
    }

    search = client.post(
        "/api/v1/agent/chat",
        json={**request, "message": "I need running shoes under 5000"},
    )
    product = search.json()["tool_result"]["result"]["items"][0]
    added = client.post(
        "/api/v1/agent/chat",
        json={**request, "message": f"Add {product['name']} to my cart"},
    )
    viewed = client.post(
        "/api/v1/agent/chat",
        json={**request, "message": "What's in my cart?"},
    )

    assert added.status_code == 200
    assert viewed.status_code == 200
    assert viewed.json()["tool_used"] == "get_cart"
    items = viewed.json()["tool_result"]["result"]["items"]
    assert any(item["product_id"] == product["product_id"] for item in items)


def test_buyer_agent_sessions_are_isolated(monkeypatch):
    configure_mock_provider(monkeypatch)
    first_id = new_session_id()
    second_id = new_session_id()

    first = client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": first_id,
            "customer_id": "c_demo_001",
            "message": "I need running shoes under 5000",
        },
    )
    second = client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": second_id,
            "customer_id": "c_demo_001",
            "message": "Hello",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["tool_used"] is None
    assert second.json()["tool_result"] is None
    assert all(
        message.session_id == second_id
        for message in get_messages(second_id)
    )
    assert not any(
        message.content == "I need running shoes under 5000"
        for message in get_messages(second_id)
    )


def test_buyer_agent_rejects_customer_mismatch(monkeypatch):
    configure_mock_provider(monkeypatch)
    identifier = new_session_id()

    created = client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": identifier,
            "customer_id": "customer-a",
            "message": "Hello",
        },
    )
    rejected = client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": identifier,
            "customer_id": "customer-b",
            "message": "Hello",
        },
    )

    assert created.status_code == 200
    assert rejected.status_code == 400
    assert "different customer" in rejected.json()["detail"]


def test_buyer_agent_rejects_empty_message():
    response = client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": "test-session",
            "customer_id": "c_demo_001",
            "message": "",
        },
    )

    assert response.status_code == 422


def test_buyer_agent_requires_session_id():
    response = client.post(
        "/api/v1/agent/chat",
        json={
            "customer_id": "c_demo_001",
            "message": "Hello",
        },
    )

    assert response.status_code == 422