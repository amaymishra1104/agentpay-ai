from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.state import BuyerAgentState
from app.agents.tools import run_tool


def agent_node(state: BuyerAgentState) -> dict[str, Any]:
    """
    Deterministic reasoning node used to validate the Buyer Agent
    graph before connecting a real LLM.

    Current behavior:
    - Detects a running-shoe request.
    - Calls the catalog search tool once.
    - After receiving the tool result, produces a final response.
    """

    # If a tool has already been executed, the agent has observed
    # its result and should finish this deterministic test flow.
    if state.last_tool_result is not None:
        return {
            "final_response": (
                "I found matching running products "
                "from the catalog."
            ),
            "messages": [
                {
                    "role": "assistant",
                    "type": "final",
                    "content": (
                        "I found matching running products "
                        "from the catalog."
                    ),
                }
            ],
        }

    message = state.user_message.lower()

    if "running" in message or "shoe" in message:
        return {
            "messages": [
                {
                    "role": "assistant",
                    "type": "tool_call",
                    "tool_name": "search_products",
                    "arguments": {
                        "query": "running shoes",
                        "limit": 5,
                    },
                }
            ]
        }

    return {
        "final_response": (
            "I can help you search products, "
            "compare them, and build a cart."
        ),
        "messages": [
            {
                "role": "assistant",
                "type": "final",
                "content": (
                    "I can help you search products, "
                    "compare them, and build a cart."
                ),
            }
        ],
    }


def tool_node(state: BuyerAgentState) -> dict[str, Any]:
    """
    Execute the tool requested by the reasoning node.
    """

    messages = state.messages

    if not messages:
        return {}

    last_message = messages[-1]

    if last_message.get("type") != "tool_call":
        return {}

    tool_name = last_message["tool_name"]
    arguments = last_message.get("arguments", {})

    result = run_tool(tool_name, arguments)

    return {
        "last_tool_result": {
            "tool_name": tool_name,
            "result": result,
        },
        "tool_history": [
            {
                "tool_name": tool_name,
                "arguments": arguments,
                "result": result,
            }
        ],
    }


def route_after_agent(state: BuyerAgentState) -> str:
    """
    Decide whether the graph should execute a tool or finish.
    """

    if not state.messages:
        return END

    last_message = state.messages[-1]

    if last_message.get("type") == "tool_call":
        return "tool"

    return END


def build_buyer_graph():
    """
    Build and compile the Buyer Agent LangGraph.
    """

    graph = StateGraph(BuyerAgentState)

    graph.add_node("agent", agent_node)
    graph.add_node("tool", tool_node)

    graph.add_edge(START, "agent")

    graph.add_conditional_edges(
        "agent",
        route_after_agent,
        {
            "tool": "tool",
            END: END,
        },
    )

    graph.add_edge("tool", "agent")

    return graph.compile()