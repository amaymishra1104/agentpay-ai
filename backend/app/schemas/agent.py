from pydantic import BaseModel, Field


class AgentMessage(BaseModel):
    role: str = Field(min_length=1)
    content: str = Field(min_length=1)


class AgentTurn(BaseModel):
    session_id: str = Field(min_length=1)
    messages: list[AgentMessage] = Field(default_factory=list)
