"""Agent interfaces consumed by the shared voice runtime."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.models import AgentResult, SessionContext


class BaseAgent(ABC):
    """Stable runtime contract for any agent implementation."""

    system_prompt: str | None = None
    conversation_history: list[dict[str, str]] = []

    @abstractmethod
    async def run_turn(self, text: str, session: SessionContext) -> AgentResult:
        """Return the next agent result.

        ``text`` is the finished user turn, or an empty string when the runtime
        asks for an agent-initiated turn (for example when the session starts).
        """
        ...

    async def finish_session(self, conn_state: Any, message_queue: Any, reason: str) -> None:
        """End the session and tell the client it is finished."""
        conn_state.session_finished = True
        await message_queue.put({"type": "finish_complete", "success": True})

    async def save_progress(self, conn_state: Any) -> None:
        """Persist the session when the client disconnects. No-op by default."""
        return None
