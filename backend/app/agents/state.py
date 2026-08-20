from dataclasses import dataclass, field


@dataclass(slots=True)
class AgentSessionState:
    session_id: str
    customer_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
