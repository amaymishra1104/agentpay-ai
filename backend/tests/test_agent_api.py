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


def test_buyer_agent_handles_rate_limit_cleanly(monkeypatch):
    class MockRateLimitedModel:
        def invoke(self, messages, tools):
            class DummyRateLimitError(Exception):
                status_code = 429
            raise DummyRateLimitError("Rate limit reached for TPD")

    import app.api.routes.agent
    monkeypatch.setattr(app.api.routes.agent, "_build_model", lambda: MockRateLimitedModel())

    response = client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": "test-session-rate-limit",
            "customer_id": "c_demo_001",
            "message": "hello",
        },
    )

    assert response.status_code == 429
    assert "rate-limited" in response.json()["detail"]


def test_groq_buyer_model_bounded_retry(monkeypatch):
    from app.agents.model_provider import GroqBuyerModel
    from app.config import Settings
    monkeypatch.setattr(
        "app.agents.model_provider.get_settings",
        lambda: Settings(groq_api_key="dummy_key", groq_model="dummy_model"),
    )

    call_count = 0

    class DummyHeaders(dict):
        pass

    class DummyRateLimitError(Exception):
        status_code = 429
        def __init__(self, message, headers=None):
            super().__init__(message)
            self.headers = headers

    def mock_create(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        headers = DummyHeaders()
        headers["retry-after"] = "0.01"
        raise DummyRateLimitError("Rate Limit", headers=headers)

    model = GroqBuyerModel()
    monkeypatch.setattr(model.client.chat.completions, "create", mock_create)

    try:
        model.invoke([{"role": "user", "content": "hi"}], [])
    except Exception as exc:
        assert call_count == 2
        assert exc.__class__.__name__ == "DummyRateLimitError"


def test_groq_buyer_model_fail_fast_long_wait(monkeypatch):
    from app.agents.model_provider import GroqBuyerModel
    from app.config import Settings
    monkeypatch.setattr(
        "app.agents.model_provider.get_settings",
        lambda: Settings(groq_api_key="dummy_key", groq_model="dummy_model"),
    )

    call_count = 0

    class DummyHeaders(dict):
        pass

    class DummyRateLimitError(Exception):
        status_code = 429
        def __init__(self, message, headers=None):
            super().__init__(message)
            self.headers = headers

    def mock_create(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        headers = DummyHeaders()
        headers["retry-after"] = "10.0"
        raise DummyRateLimitError("Rate Limit", headers=headers)

    model = GroqBuyerModel()
    monkeypatch.setattr(model.client.chat.completions, "create", mock_create)

    try:
        model.invoke([{"role": "user", "content": "hi"}], [])
    except Exception as exc:
        assert call_count == 1
        assert exc.__class__.__name__ == "DummyRateLimitError"


def test_get_buyer_session_endpoint(monkeypatch):
    configure_mock_provider(monkeypatch)
    identifier = new_session_id()

    # Chat with agent
    chat_res = client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": identifier,
            "customer_id": "c_demo_001",
            "message": "I need running shoes under 5000",
        },
    )
    assert chat_res.status_code == 200

    # Retrieve session history
    session_res = client.get(f"/api/v1/agent/sessions/{identifier}?customer_id=c_demo_001")
    assert session_res.status_code == 200
    data = session_res.json()
    assert data["session_id"] == identifier
    assert data["customer_id"] == "c_demo_001"
    assert len(data["messages"]) >= 2
    assert any(m["role"] == "user" for m in data["messages"])
    assert any(m["role"] == "assistant" for m in data["messages"])


def test_get_buyer_session_not_found():
    res = client.get("/api/v1/agent/sessions/non-existent-session-id")
    assert res.status_code == 404


def test_get_buyer_session_customer_permission_denied(monkeypatch):
    configure_mock_provider(monkeypatch)
    identifier = new_session_id()

    client.post(
        "/api/v1/agent/chat",
        json={
            "session_id": identifier,
            "customer_id": "c_customer_1",
            "message": "Hello",
        },
    )

    res = client.get(f"/api/v1/agent/sessions/{identifier}?customer_id=c_customer_2")
    assert res.status_code == 403