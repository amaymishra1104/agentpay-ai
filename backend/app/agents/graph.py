from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.model import BuyerModel, MockBuyerModel
from app.agents.state import BuyerAgentState
from app.agents.tools import run_tool


def agent_node(
    state: BuyerAgentState,
    model: BuyerModel,
) -> dict[str, Any]:
    """
    Run the Buyer Agent model and translate its response
    into graph state.
    """

    response = model.invoke(
        messages=state.messages,
        tools=[],
    )

    if response.has_tool_calls:
        tool_call = response.tool_calls[0]

        return {
            "messages": [
                {
                    "role": "assistant",
                    "type": "tool_call",
                    "tool_name": tool_call.tool_name,
                    "arguments": tool_call.arguments,
                }
            ]
        }

    return {
        "final_response": response.content or "",
        "messages": [
            {
                "role": "assistant",
                "type": "final",
                "content": response.content or "",
            }
        ],
    }


def tool_node(
    state: BuyerAgentState,
) -> dict[str, Any]:
    """
    Execute the tool requested by the model.
    """

    if not state.messages:
        return {}

    last_message = state.messages[-1]

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
        "messages": [
            {
                "role": "tool",
                "type": "tool_result",
                "tool_name": tool_name,
                "content": str(result),
            }
        ],
    }


def final_response_node(
    state: BuyerAgentState,
) -> dict[str, Any]:
    """
    Produce a deterministic response after a tool execution.

    This node exists only for the mock-agent phase.
    The real LLM will eventually generate the final response
    after observing tool results.
    """

    tool_result = state.last_tool_result

    if tool_result is None:
        return {
            "final_response": (
                "I wasn't able to complete the request."
            )
        }

    tool_name = tool_result["tool_name"]

    if tool_name == "search_products":
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

    return {
        "final_response": (
            "I completed the requested catalog operation."
        ),
        "messages": [
            {
                "role": "assistant",
                "type": "final",
                "content": (
                    "I completed the requested catalog operation."
                ),
            }
        ],
    }


def route_after_agent(
    state: BuyerAgentState,
) -> str:
    """
    Decide whether the graph should execute a tool or finish.
    """

    if not state.messages:
        return END

    last_message = state.messages[-1]

    if last_message.get("type") == "tool_call":
        return "tool"

    return END


def route_after_tool(
    state: BuyerAgentState,
) -> str:
    """
    Route a completed tool execution to the deterministic
    final-response node.
    """

    if state.last_tool_result is not None:
        return "final"

    return END


def create_agent_node(
    model: BuyerModel,
):
    """
    Create a typed LangGraph node bound to a specific model.
    """

    def node(
        state: BuyerAgentState,
    ) -> dict[str, Any]:
        return agent_node(state, model)

    return node


def build_buyer_graph(
    model: BuyerModel | None = None,
):
    """
    Build and compile the Buyer Agent graph.

    A deterministic mock model is used by default so the graph
    remains testable without an external LLM provider.
    """

    if model is None:
        model = MockBuyerModel()

    graph = StateGraph(BuyerAgentState)

    graph.add_node(
        "agent",
        create_agent_node(model),
    )

    graph.add_node(
        "tool",
        tool_node,
    )

    graph.add_node(
        "final",
        final_response_node,
    )

    graph.add_edge(
        START,
        "agent",
    )

    graph.add_conditional_edges(
        "agent",
        route_after_agent,
        {
            "tool": "tool",
            END: END,
        },
    )

    graph.add_conditional_edges(
        "tool",
        route_after_tool,
        {
            "final": "final",
            END: END,
        },
    )

    graph.add_edge(
        "final",
        END,
    )

    return graph.compile()