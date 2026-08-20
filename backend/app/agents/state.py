from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BuyerAgentState:
    """State carried through a single AI buyer interaction."""

    session_id: str

    customer_id: str | None = None

    user_message: str = ""

    intent: dict[str, Any] = field(default_factory=dict)

    candidate_product_ids: list[str] = field(default_factory=list)

    selected_product_ids: list[str] = field(default_factory=list)

    cart_id: str | None = None

    messages: list[dict[str, Any]] = field(default_factory=list)

    tool_history: list[dict[str, Any]] = field(default_factory=list)

    last_tool_result: dict[str, Any] | None = None

    final_response: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)