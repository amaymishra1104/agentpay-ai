import os
from uuid import uuid4

os.environ["DATABASE_URL"] = "sqlite:///./agentpay.db"

from app.services.agent_session_service import (
    get_messages,
    get_or_create_session,
    get_session,
    save_message,
    update_cart_id,
)


def session_id() -> str:
    return f"test-session-{uuid4().hex}"


def test_create_new_session():
    created = get_or_create_session(session_id(), "customer-1")

    assert created.customer_id == "customer-1"
    assert created.cart_id is None
    assert created.created_at is not None
    assert created.updated_at is not None


def test_retrieve_existing_session():
    identifier = session_id()
    created = get_or_create_session(identifier, "customer-1")
    retrieved = get_session(identifier)

    assert retrieved is not None
    assert retrieved.session_id == created.session_id
    assert retrieved.customer_id == "customer-1"


def test_customer_mismatch_is_rejected():
    identifier = session_id()
    get_or_create_session(identifier, "customer-1")

    try:
        get_or_create_session(identifier, "customer-2")
    except ValueError as exc:
        assert "different customer" in str(exc)
    else:
        raise AssertionError("Expected customer mismatch to be rejected")


def test_save_normal_user_message():
    identifier = session_id()
    get_or_create_session(identifier)

    message = save_message(identifier, "user", "Hello")

    assert message.role == "user"
    assert message.message_type == "text"
    assert message.content == "Hello"
    assert message.sequence == 1


def test_save_multiple_messages_assigns_sequence():
    identifier = session_id()
    get_or_create_session(identifier)

    messages = [
        save_message(identifier, "user", "First"),
        save_message(identifier, "assistant", "Second"),
        save_message(identifier, "tool", "Third", message_type="tool_result"),
    ]

    assert [message.sequence for message in messages] == [1, 2, 3]


def test_get_messages_returns_chronological_order():
    identifier = session_id()
    get_or_create_session(identifier)
    save_message(identifier, "user", "First")
    save_message(identifier, "assistant", "Second")
    save_message(identifier, "tool", "Third")

    messages = get_messages(identifier)

    assert [message.content for message in messages] == [
        "First",
        "Second",
        "Third",
    ]
    assert [message.sequence for message in messages] == [1, 2, 3]


def test_tool_result_content_is_not_truncated():
    identifier = session_id()
    get_or_create_session(identifier)
    content = "product-result-" + ("x" * 5000)

    message = save_message(
        identifier,
        "tool",
        content,
        message_type="tool_result",
        tool_name="search_products",
        tool_call_id="call-1",
    )

    assert message.content == content
    assert len(message.content) == len(content)


def test_update_cart_id_persists():
    identifier = session_id()
    get_or_create_session(identifier)

    updated = update_cart_id(identifier, "cart-test-1")
    retrieved = get_session(identifier)

    assert updated.cart_id == "cart-test-1"
    assert retrieved is not None
    assert retrieved.cart_id == "cart-test-1"


def test_sessions_are_isolated():
    first_id = session_id()
    second_id = session_id()
    get_or_create_session(first_id)
    get_or_create_session(second_id)
    save_message(first_id, "user", "Only session A")
    save_message(second_id, "user", "Only session B")

    first_messages = get_messages(first_id)
    second_messages = get_messages(second_id)

    assert [message.content for message in first_messages] == [
        "Only session A"
    ]
    assert [message.content for message in second_messages] == [
        "Only session B"
    ]