from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolCall:
    """A structured request from the model to execute a tool."""

    tool_name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class ModelResponse:
    """Normalized response returned by an LLM provider."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        """Return whether the model requested any tools."""

        return bool(self.tool_calls)


class BuyerModel(ABC):
    """
    Provider-independent interface for the Buyer Agent model.

    The agent depends on this interface rather than directly
    depending on Gemini, OpenAI, Groq, or another provider.
    """

    @abstractmethod
    def invoke(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        """Generate the next model response."""
        raise NotImplementedError


class MockBuyerModel(BuyerModel):
    """
    Deterministic model used for local development and testing.

    This intentionally does not use an external API.
    """

    def invoke(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        """Return deterministic behavior for graph testing."""

        last_message = messages[-1] if messages else {}
        content = str(last_message.get("content", "")).lower()

        if "running" in content or "shoe" in content:
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        tool_name="search_products",
                        arguments={
                            "query": "running shoes",
                            "limit": 5,
                        },
                    )
                ]
            )

        return ModelResponse(
            content=(
                "I can help you search products, "
                "compare them, and build a cart."
            )
        )