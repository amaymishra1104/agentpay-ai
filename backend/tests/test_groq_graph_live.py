import os

import pytest
from dotenv import load_dotenv

from app.agents.graph import build_buyer_graph
from app.agents.model_provider import GroqBuyerModel
from app.agents.state import BuyerAgentState


load_dotenv()


@pytest.mark.live_groq
def test_groq_buyer_graph_executes_catalog_tool():

    if not os.getenv("GROQ_API_KEY"):
        pytest.skip(
            "GROQ_API_KEY is not configured."
        )

    model = GroqBuyerModel()

    graph = build_buyer_graph(
        model=model
    )

    state = BuyerAgentState(
        session_id="live-groq-test",
        customer_id="c_demo_001",
        user_message=(
            "I need running shoes under 5000 rupees."
        ),
        messages=[
            {
                "role": "system",
                "content": (
                    "You are the AgentPay Buyer Agent. "
                    "Use the provided tools to help the buyer. "
                    "Never invent product information. "
                    "When the buyer asks to find products, "
                    "use search_products."
                ),
            },
            {
                "role": "user",
                "content": (
                    "I need running shoes under 5000 rupees."
                ),
            },
        ],
    )

    result = graph.invoke(state)

    assert result["last_tool_result"] is not None

    assert (
        result["last_tool_result"]["tool_name"]
        == "search_products"
    )

    assert result["last_tool_result"]["result"] is not None

    assert result["final_response"]

    assert len(
        result["tool_history"]
    ) >= 1