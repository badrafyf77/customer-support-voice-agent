"""Agent interfaces consumed by the shared voice runtime."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.models import AgentResult, SessionContext


class BaseAgent(ABC):
    """Stable runtime contract for any agent implementation."""

    system_prompt: str | None = None
    conversation_history: list[dict[str, str]] = []

    @property
    def initial_state(self) -> dict[str, Any]:
        return {}

    def build_graph(self) -> Any | None:
        """Optional hook for graph-backed agents."""
        return None

    @abstractmethod
    async def run_turn(self, text: str, session: SessionContext) -> AgentResult:
        """Return the next agent result for a completed user turn or runtime event."""
        ...
