"""Simple conversational voice agent.

This agent intentionally has no database, auth, exam, or evaluation behavior.
It only turns each finalized user transcript into the next LLM prompt.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any

from agents.base import BaseAgent
from core.models import AgentResult, SessionContext


SYSTEM_PROMPT = """
You are a helpful, concise voice assistant.
Speak naturally in short responses unless the user asks for detail.
Do not mention exams, grading, attempts, rubrics, or authentication.
""".strip()


DARIJA_SYSTEM_PROMPT = """
نتا مساعد صوتي كتعاون المستخدم. جاوب بالدارجة المغربية بالحروف العربية.
خلي الجواب قصير وطبيعي وساهل يتقال، إلا طلب المستخدم التفاصيل.
إلا ما فهمتيش ولا ما عندكش المعلومة، قولها بوضوح وسول سؤال قصير باش توضح.
ما تخترعش معلومات. حافظ على الأسامي الأجنبية وأرقام التليفون وأرقام الطلبات
والمقادير كيف ما عطاهم المستخدم، بلا ما تبدل الأرقام لحروف.
إلا استعمل المستخدم كلمات بالفرنسية ولا بالإنجليزية، بقى جاوب بالدارجة
وبلا ما تقلب الجواب للفرنسية ولا للإنجليزية. ما تستعملش علامات التنسيق ولا تسميات الأدوار.
""".strip()


@dataclass(frozen=True)
class PlannedChatTurn:
    kind: str
    control_prompt: str
    expects_control_block: bool = False
    question_number: int | None = None
    history_override: list[dict[str, str]] | None = None
    should_auto_finish: bool = False


class ChatAgentBrain(BaseAgent):
    """Minimal brain adapter consumed by the shared streaming session."""

    system_prompt = SYSTEM_PROMPT
    conversation_history: list[dict[str, str]] = []

    def __init__(self, profile: str = "english") -> None:
        if profile not in {"english", "darija"}:
            raise ValueError("Unknown chat voice profile")
        self.system_prompt = DARIJA_SYSTEM_PROMPT if profile == "darija" else SYSTEM_PROMPT
        self.conversation_history = []
        self._lock = Lock()
        self._pending_user_turn = ""

    def reset_session_state(self):
        with self._lock:
            self._pending_user_turn = ""
        self.conversation_history = []

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

    async def run_turn(self, text: str, session: SessionContext) -> AgentResult:
        if text:
            self.queue_student_turn(text)

        planned_turn = self.plan_student_turn_response(session.conversation_history)
        return AgentResult.from_planned_turn(planned_turn)


def build_chat_agent(context: dict[str, Any] | None = None) -> tuple[ChatAgentBrain, dict[str, Any]]:
    brain = ChatAgentBrain(profile=(context or {}).get("profile", "english"))
    return brain, brain.initial_state
