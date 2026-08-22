import pytest
from app.agents.model import MockBuyerModel, ToolCall

def test_mock_agent_order_disambiguation():
    model = MockBuyerModel()

    # 1. Test case: Inspect context with choice resolution
    messages_inspect = [
        {"role": "user", "content": "What did I buy?"},
        {"role": "assistant", "type": "final", "content": "I found multiple orders for you. Which order would you like to inspect?\n\n- Order ID: ord_abc123\n- Order ID: ord_xyz789"},
        {"role": "user", "content": "the first one"}
    ]

    res = model.invoke(messages_inspect, [])
    assert res.tool_calls is not None
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].tool_name == "get_order"
    assert res.tool_calls[0].arguments == {"order_id": "ord_abc123"}

    # 2. Test case: Track context with choice resolution
    messages_track = [
        {"role": "user", "content": "Where are my orders?"},
        {"role": "assistant", "type": "final", "content": "I found multiple orders for you. Which order would you like me to track?\n\n- Order ID: ord_abc123\n- Order ID: ord_xyz789"},
        {"role": "user", "content": "the second one"}
    ]

    res = model.invoke(messages_track, [])
    assert res.tool_calls is not None
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].tool_name == "get_order_tracking"
    assert res.tool_calls[0].arguments == {"order_id": "ord_xyz789"}

    # 3. Test case: Explicit order ID resolution
    messages_explicit = [
        {"role": "user", "content": "Track my order"},
        {"role": "assistant", "type": "final", "content": "I found multiple orders for you. Which order would you like me to track?\n\n- Order ID: ord_abc123\n- Order ID: ord_xyz789"},
        {"role": "user", "content": "track ord_xyz789"}
    ]

    res = model.invoke(messages_explicit, [])
    assert res.tool_calls is not None
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].tool_name == "get_order_tracking"
    assert res.tool_calls[0].arguments == {"order_id": "ord_xyz789"}
