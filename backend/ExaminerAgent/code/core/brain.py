"""Agent bridge abstractions used by the shared voice pipeline."""
from __future__ import annotations

import asyncio
from typing import Any, Protocol

from core.models import AgentResult, SessionContext

EXAM_CONTROL_DELIMITER = "§CTRL§"


class SupportsAInvoke(Protocol):
    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        ...


class AgentBrain:
    """
    Generic LangGraph bridge.

    It owns per-session graph state, accepts finalized user transcripts, and
    cancels an in-flight graph run when a newer transcript arrives.
    """

    def __init__(self, graph: SupportsAInvoke, initial_state: dict[str, Any]):
        self.graph = graph
        self.state = initial_state
        self._current_task: asyncio.Task | None = None

    async def handle_transcript(self, text: str) -> str:
        if self._current_task:
            self._current_task.cancel()
        self._current_task = asyncio.create_task(self._run(text))
        return await self._current_task

    async def run_turn(self, text: str, session: SessionContext) -> AgentResult:
        reply = await self.handle_transcript(text)
        return AgentResult(text=reply, kind="graph", action="respond")

    async def _run(self, text: str) -> str:
        result = await self.graph.ainvoke({**self.state, "user_input": text})
        self.state = result
        return result["reply"]


class PlannedAgentTurn(Protocol):
    kind: str
    control_prompt: str
    expects_control_block: bool
    question_number: int | None
    history_override: list[dict[str, str]] | None
    should_auto_finish: bool


class StreamingSessionBrain(Protocol):
    """Duck-typed interface used by the current streaming speech session."""

    system_prompt: str | None

    @property
    def has_pending_student_turn(self) -> bool:
        ...

    def queue_student_turn(self, turn_text: str) -> str:
        ...

    def plan_next_turn(self, conversation_history: list[dict[str, str]] | None = None) -> PlannedAgentTurn | None:
        ...

    def plan_resume_turn(self, conversation_history: list[dict[str, str]] | None = None) -> PlannedAgentTurn | None:
        ...

    def plan_student_turn_response(self, conversation_history: list[dict[str, str]] | None = None) -> PlannedAgentTurn | None:
        ...

    async def run_turn(self, text: str, session: SessionContext) -> AgentResult:
        ...

    def should_silence_completed_turn(self, control_payload: Any, *, forced: bool = False) -> bool:
        ...

    def mark_assistant_turn_delivered(
        self,
        spoken_text: str,
        control_payload: Any = None,
        *,
        forced: bool = False,
    ) -> PlannedAgentTurn | None:
        ...

    async def finish_session(self, conn_state: Any, message_queue: asyncio.Queue, reason: str) -> None:
        ...

    async def save_progress(self, conn_state: Any) -> None:
        ...
