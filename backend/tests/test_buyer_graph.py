from app.agents.model import BuyerModel, ModelResponse, ToolCall
from app.agents.graph import build_buyer_graph
from app.agents.state import BuyerAgentState
from app.agents.tool_registry import get_buyer_tool_names


class ToolResultGroundingModel(BuyerModel):
    def __init__(self):
        self.calls = []

    def invoke(self, messages, tools):
        self.calls.append(messages)

        if len(self.calls) == 1:
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        tool_name="search_products",
                        arguments={
                            "query": "running shoes",
                            "max_price": 5000,
                            "in_stock": True,
                            "limit": 10,
                        },
                    )
                ]
            )

        tool_result = messages[-1]
        return ModelResponse(
            content=f"Catalog results: {tool_result['content']}"
        )


def test_buyer_graph_searches_running_shoes():
    graph = build_buyer_graph()

    state = BuyerAgentState(
        session_id="test-session",
        customer_id="c_demo_001",
        user_message="I need running shoes under 5000",
        messages=[
            {
                "role": "user",
                "type": "user",
                "content": "I need running shoes under 5000",
            }
        ],
    )

    result = graph.invoke(state)

    assert result["last_tool_result"] is not None

    assert (
        result["last_tool_result"]["tool_name"]
        == "search_products"
    )

    assert result["last_tool_result"]["result"] is not None

    assert result["final_response"] is not None


def test_buyer_graph_final_response_uses_search_result():
    model = ToolResultGroundingModel()
    graph = build_buyer_graph(model)

    result = graph.invoke(
        BuyerAgentState(
            session_id="grounding-session",
            customer_id="c_demo_001",
            user_message="I need running shoes under 5000",
            messages=[
                {
                    "role": "user",
                    "content": "I need running shoes under 5000",
                }
            ],
        )
    )

    assert result["last_tool_result"]["tool_name"] == "search_products"
    assert result["final_response"]
    assert "AeroRun X1" in result["final_response"]
    assert "How can I help" not in result["final_response"]

    second_call_messages = model.calls[1]
    assert [message["role"] for message in second_call_messages] == [
        "user",
        "assistant",
        "tool",
    ]
    assert second_call_messages[-1]["type"] == "tool_result"


def test_buyer_graph_has_access_to_allowlisted_tools():
    """
    Verify the Buyer Agent registry exposes the expected
    commerce tools.
    """

    tool_names = get_buyer_tool_names()

    assert "search_products" in tool_names
    assert "get_product" in tool_names
    assert "compare_products" in tool_names

    assert "create_cart" in tool_names
    assert "add_to_cart" in tool_names
    assert "update_cart_item" in tool_names
    assert "remove_from_cart" in tool_names
    assert "validate_cart" in tool_names

    assert "charge_payment" not in tool_names
    assert "modify_inventory" not in tool_names
    assert "apply_arbitrary_discount" not in tool_names