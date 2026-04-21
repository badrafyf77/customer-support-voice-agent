"""Simple conversational voice agent.

This agent intentionally has no database, auth, exam, or evaluation behavior.
It only turns each finalized user transcript into the next LLM prompt.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any


SYSTEM_PROMPT = """
You are a helpful, concise voice assistant.
Speak naturally in short responses unless the user asks for detail.
Do not mention exams, grading, attempts, rubrics, or authentication.
""".strip()


@dataclass(frozen=True)
class PlannedChatTurn:
    kind: str
    control_prompt: str
    expects_control_block: bool = False
    question_number: int | None = None
    history_override: list[dict[str, str]] | None = None
    should_auto_finish: bool = False


class ChatAgentBrain:
    """Minimal brain adapter consumed by the shared streaming session."""

    system_prompt = SYSTEM_PROMPT
    conversation_history: list[dict[str, str]] = []

    def __init__(self) -> None:
        self._lock = Lock()
        self._pending_user_turn = ""

    @property
    def initial_state(self) -> dict[str, Any]:
        return {"agent": "chat"}

    @property
    def has_pending_student_turn(self) -> bool:
        with self._lock:
            return bool(self._pending_user_turn)

    def queue_student_turn(self, turn_text: str) -> str:
        normalized_text = str(turn_text or "").strip()
        if not normalized_text:
            return "ignored"

        with self._lock:
            self._pending_user_turn = normalized_text
        return "queued"

    def plan_next_turn(self, conversation_history: list[dict[str, str]] | None = None) -> None:
        return None

    def plan_resume_turn(self, conversation_history: list[dict[str, str]] | None = None) -> None:
        return None

    def plan_student_turn_response(
        self,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> PlannedChatTurn | None:
        with self._lock:
            user_turn = self._pending_user_turn
            self._pending_user_turn = ""

        if not user_turn:
            return None

        return PlannedChatTurn(kind="chat", control_prompt=user_turn)

    def should_silence_completed_turn(self, control_payload: Any, *, forced: bool = False) -> bool:
        return False

    def mark_assistant_turn_delivered(
        self,
        spoken_text: str,
        control_payload: Any = None,
        *,
        forced: bool = False,
    ) -> None:
        return None

    async def finish_session(self, conn_state: Any, message_queue: Any, reason: str) -> None:
        conn_state.session_finished = True
        await message_queue.put({
            "type": "finish_complete",
            "success": True,
        })

    async def save_progress(self, conn_state: Any) -> None:
        return None


def build_chat_agent(context: dict[str, Any] | None = None) -> tuple[ChatAgentBrain, dict[str, Any]]:
    brain = ChatAgentBrain()
    return brain, brain.initial_state
