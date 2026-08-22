from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from app.agents.graph import build_buyer_graph
from app.agents.model_provider import GroqBuyerModel
from app.agents.state import BuyerAgentState
from app.config import get_settings
from app.services.agent_session_service import (
    get_session,
    get_messages,
    get_or_create_session,
    save_message,
    update_cart_id,
)
from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    AgentToolResult,
)
import logging

logger = logging.getLogger("agentpay")


router = APIRouter(
    prefix="/agent",
    tags=["agent"],
)


def _build_model():
    """
    Select the configured Buyer Agent model.

    Groq is used when configured.
    The deterministic mock remains available when
    running without an LLM provider.
    """

    settings = get_settings()

    if settings.llm_provider.lower() == "groq":
        return GroqBuyerModel()

    from app.agents.model import MockBuyerModel

    return MockBuyerModel()


def _json_default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(
        f"Object of type {type(value).__name__} is not JSON serializable"
    )


def _serialize_content(value: Any) -> str:
    return json.dumps(value, default=_json_default)


def _message_from_record(message: Any) -> dict[str, Any]:
    state_message: dict[str, Any] = {
        "role": message.role,
        "content": message.content,
    }

    if message.message_type != "text":
        state_message["type"] = message.message_type

    if message.tool_name is not None:
        state_message["tool_name"] = message.tool_name

    if message.tool_call_id is not None:
        state_message["tool_call_id"] = message.tool_call_id

    if message.message_type == "tool_call":
        try:
            stored_content = json.loads(message.content)
            state_message["arguments"] = stored_content.get("arguments", {})
        except (TypeError, json.JSONDecodeError):
            state_message["arguments"] = {}

    return state_message


def _persist_generated_messages(
    session_id: str,
    messages: list[dict[str, Any]],
    tool_history: list[dict[str, Any]],
) -> None:
    tool_results = iter(tool_history)

    for message in messages:
        message_type = str(message.get("type", "text"))
        content: Any = message.get("content", "")

        if message_type == "tool_call":
            content = _serialize_content(
                {"arguments": message.get("arguments", {})}
            )
        elif message_type == "tool_result":
            tool_history_item = next(tool_results, None)
            if tool_history_item is not None:
                content = _serialize_content(tool_history_item["result"])

        save_message(
            session_id=session_id,
            role=str(message.get("role", "assistant")),
            content=str(content),
            message_type=message_type,
            tool_name=message.get("tool_name"),
            tool_call_id=message.get("tool_call_id"),
        )


@router.post(
    "/chat",
    response_model=AgentChatResponse,
)
def chat_with_buyer_agent(
    request: AgentChatRequest,
) -> AgentChatResponse:
    """
    Execute one conversational turn with the AgentPay
    Buyer Agent.

    The API owns the transaction orchestration boundary.
    The model may request allowlisted tools, but tools are
    always executed server-side.
    """

    try:
        existing_session = get_session(request.session_id)
        if not request.customer_id and (
            existing_session is None
            or not existing_session.customer_id
        ):
            raise ValueError(
                "customer_id is required when starting a buyer session."
            )

        session = get_or_create_session(
            session_id=request.session_id,
            customer_id=request.customer_id,
        )

        persisted_messages = get_messages(request.session_id)
        conversation = [
            _message_from_record(message)
            for message in persisted_messages
        ]
        conversation.append(
            {
                "role": "user",
                "content": request.message,
            }
        )
        save_message(
            session_id=request.session_id,
            role="user",
            content=request.message,
        )

        model = _build_model()

        graph = build_buyer_graph(
            model=model
        )

        state = BuyerAgentState(
            session_id=request.session_id,
            customer_id=session.customer_id,
            user_message=request.message,
            cart_id=session.cart_id,
            messages=conversation,
        )

        result = graph.invoke(
            state
        )

        generated_messages = result.get("messages", [])[len(conversation) :]
        _persist_generated_messages(
            session_id=request.session_id,
            messages=generated_messages,
            tool_history=result.get("tool_history", []),
        )

        final_response = (
            result.get("final_response")
            or ""
        )

        last_tool_result = result.get(
            "last_tool_result"
        )

        tool_result = None

        if last_tool_result:
            tool_result = AgentToolResult(
                tool_name=str(
                    last_tool_result.get(
                        "tool_name",
                        "",
                    )
                ),
                result=last_tool_result.get(
                    "result"
                ),
            )

        cart_id = result.get("cart_id") or session.cart_id
        tool_values = [
            tool_history_item.get("result")
            for tool_history_item in result.get("tool_history", [])
        ]
        if cart_id is None and last_tool_result:
            tool_values.append(last_tool_result.get("result"))

        if cart_id is None:
            for tool_value in reversed(tool_values):
                if isinstance(tool_value, dict):
                    possible_cart_id = tool_value.get("cart_id")
                    if isinstance(possible_cart_id, str):
                        cart_id = possible_cart_id
                        break

        if isinstance(cart_id, str) and cart_id != session.cart_id:
            update_cart_id(request.session_id, cart_id)

        return AgentChatResponse(
            session_id=request.session_id,
            response=final_response,
            tool_used=(
                tool_result.tool_name
                if tool_result
                else None
            ),
            tool_result=tool_result,
            cart_id=cart_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        # Check if this is an upstream rate-limit exception
        is_429 = False
        class_name = exc.__class__.__name__
        if "RateLimit" in class_name:
            is_429 = True
        elif getattr(exc, "status_code", None) == 429:
            is_429 = True
        elif "429" in str(exc) or "too many requests" in str(exc).lower():
            is_429 = True

        if is_429:
            logger.error("Upstream Groq rate-limit occurred: %s", str(exc))
            raise HTTPException(
                status_code=429,
                detail="Agent service is temporarily unavailable. The AI provider may be rate-limited. Please try again shortly.",
            ) from exc

        logger.exception("Unhandled error in buyer agent: %s", str(exc))
        raise HTTPException(
            status_code=500,
            detail=(
                "Buyer Agent failed to process "
                "the request."
            ),
        ) from exc