from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCall:
    tool_name: str
    arguments: dict[str, Any]
    tool_call_id: str = "agentpay_tool_call"


@dataclass
class ModelResponse:
    content: str | None = None
    tool_calls: list[ToolCall] | None = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class BuyerModel:
    """Provider-independent interface for the AgentPay Buyer Agent."""

    def invoke(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        raise NotImplementedError


class MockBuyerModel(BuyerModel):
    """
    Deterministic model used by the local test suite.

    The mock intentionally does not depend on the supplied tool
    definitions. Its purpose is to simulate model intent so that
    the graph can be tested without an external LLM.
    """

    def invoke(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        user_message = self._latest_user_message(messages)

        if "cart" in user_message and any(
            phrase in user_message
            for phrase in ("what", "show", "view", "see", "check")
        ):
            if self._has_tool_result_after_latest_user(messages, "get_cart"):
                return ModelResponse(content="Here is what is currently in your cart.")

            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        tool_name="get_cart",
                        arguments={},
                    )
                ]
            )

        if "compare" in user_message:
            if self._has_tool_result(messages, "compare_products"):
                return ModelResponse(
                    content="I compared the first two matching products."
                )

            product_ids = self._search_product_ids(messages)[:2]
            if len(product_ids) >= 2:
                return ModelResponse(
                    tool_calls=[
                        ToolCall(
                            tool_name="compare_products",
                            arguments={"product_ids": product_ids},
                        )
                    ]
                )

        if any(
            phrase in user_message
            for phrase in ("add ", "put ", "remove ", "take ")
        ) and ("cart" in user_message or "back" in user_message or "remove" in user_message):
            if self._has_tool_result_after_latest_user(messages, "add_to_cart") or self._has_tool_result_after_latest_user(messages, "remove_from_cart"):
                return ModelResponse(
                    content="I updated your cart."
                )

            product_ids = self._search_product_ids(messages)
            product_id = product_ids[0] if product_ids else None
            if "second" in user_message and len(product_ids) > 1:
                product_id = product_ids[1]
            if product_id:
                action = "remove_from_cart" if "remove" in user_message or "take " in user_message else "add_to_cart"
                arguments = {"product_id": product_id}
                if action == "add_to_cart":
                    arguments["quantity"] = 1
                return ModelResponse(
                    tool_calls=[
                        ToolCall(
                            tool_name=action,
                            arguments=arguments,
                        )
                    ]
                )

        # If the graph has already executed a tool, the model
        # should produce a final response rather than repeatedly
        # requesting another tool.
        if any(
            message.get("type") == "tool_result"
            for message in messages
        ):
            return ModelResponse(
                content=(
                    "I found matching running shoes "
                    "from the UrbanRun catalog."
                )
            )

        # Simulate the model deciding that a catalog search
        # is required.
        if (
            "running shoes" in user_message
            or "shoes" in user_message
            or "product" in user_message
        ):
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        tool_name="search_products",
                        arguments={
                            "query": "running shoes",
                            "max_price": 5000,
                        },
                    )
                ]
            )

        # Normal conversational response.
        return ModelResponse(
            content="Hello! How can I help you?"
        )

    @staticmethod
    def _latest_user_message(
        messages: list[dict[str, Any]],
    ) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return str(message.get("content", "")).lower()
        return ""

    @classmethod
    def _search_product_ids(
        cls,
        messages: list[dict[str, Any]],
    ) -> list[str]:
        result = cls._latest_tool_result(messages, "search_products")
        if not result:
            return []

        return [
            str(item["product_id"])
            for item in result.get("items", [])
            if isinstance(item, dict) and "product_id" in item
        ]

    @staticmethod
    def _has_tool_result(
        messages: list[dict[str, Any]],
        tool_name: str,
    ) -> bool:
        return any(
            message.get("type") == "tool_result"
            and message.get("tool_name") == tool_name
            for message in messages
        )

    @staticmethod
    def _has_tool_result_after_latest_user(
        messages: list[dict[str, Any]],
        tool_name: str,
    ) -> bool:
        latest_user = max(
            (index for index, message in enumerate(messages) if message.get("role") == "user"),
            default=-1,
        )
        return any(
            message.get("type") == "tool_result"
            and message.get("tool_name") == tool_name
            for message in messages[latest_user + 1 :]
        )

    @staticmethod
    def _latest_tool_result(
        messages: list[dict[str, Any]],
        tool_name: str,
    ) -> dict[str, Any] | None:
        for message in reversed(messages):
            if (
                message.get("type") != "tool_result"
                or message.get("tool_name") != tool_name
            ):
                continue

            content = message.get("content", "")
            if not isinstance(content, str):
                return None

            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                try:
                    parsed = ast.literal_eval(content)
                except (SyntaxError, ValueError):
                    return None

            return parsed if isinstance(parsed, dict) else None

        return None

    @staticmethod
    def _latest_cart_id(
        messages: list[dict[str, Any]],
    ) -> str | None:
        for message in reversed(messages):
            if (
                message.get("type") == "tool_result"
                and message.get("tool_name") == "create_cart"
            ):
                match = re.search(
                    r"['\"]cart_id['\"]:\s*['\"]([^'\"]+)['\"]",
                    str(message.get("content", "")),
                )
                if match:
                    return match.group(1)
        return None