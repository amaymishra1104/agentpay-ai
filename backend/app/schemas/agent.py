from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class AgentMessage(BaseModel):
    role: str = Field(min_length=1)
    content: str = Field(min_length=1)


class AgentMessageItem(BaseModel):
    id: int
    session_id: str
    sequence: int
    role: str
    message_type: str
    content: str
    tool_name: str | None = None
    tool_call_id: str | None = None
    created_at: datetime | None = None


class AgentSessionResponse(BaseModel):
    session_id: str
    customer_id: str | None = None
    cart_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    messages: list[AgentMessageItem] = []


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