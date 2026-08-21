from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentMessage(BaseModel):
    role: str = Field(min_length=1)
    content: str = Field(min_length=1)


class AgentChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    customer_id: str | None = None
    message: str = Field(min_length=1)


class AgentToolResult(BaseModel):
    tool_name: str
    result: Any


class AgentChatResponse(BaseModel):
    session_id: str
    response: str
    tool_used: str | None = None
    tool_result: AgentToolResult | None = None
    cart_id: str | None = None