from app.agents.graph import build_buyer_graph
from app.agents.state import BuyerAgentState


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

    tool_result = result["last_tool_result"]["result"]

    assert tool_result is not None

    assert result["final_response"] is not None