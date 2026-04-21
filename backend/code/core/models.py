"""Small shared runtime models.

Keep this file boring: only data objects and tiny normalization helpers that are
used by both core runtime code and agents.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
import re

ConversationRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ConversationMessage:
    role: ConversationRole
    content: str
    timestamp: str

    @classmethod
    def create(
        cls,
        role: ConversationRole,
        content: str,
        timestamp: datetime | None = None,
    ) -> "ConversationMessage":
        ts = timestamp or datetime.now(timezone.utc)
        return cls(role=role, content=content, timestamp=ts.isoformat())

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content, "timestamp": self.timestamp}


@dataclass
class SessionContext:
    session_id: str
    agent_name: str
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    user_id: str | None = None
    exam_id: str | None = None
    attempt_id: str | None = None
    partial_transcript: str = ""
    call_state: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentResult:
    text: str = ""
    kind: str = "none"
    action: str = "ignore"
    expects_control_block: bool = False
    question_number: int | None = None
    history_override: list[dict[str, str]] | None = None
    should_auto_finish: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return self.action == "ignore" or (not self.text and not self.should_auto_finish)

    @classmethod
    def ignore(cls) -> "AgentResult":
        return cls()

    @classmethod
    def from_planned_turn(cls, planned_turn: Any) -> "AgentResult":
        if planned_turn is None:
            return cls.ignore()
        return cls(
            text=getattr(planned_turn, "control_prompt", "") or "",
            kind=getattr(planned_turn, "kind", "turn") or "turn",
            action="generate",
            expects_control_block=bool(getattr(planned_turn, "expects_control_block", False)),
            question_number=getattr(planned_turn, "question_number", None),
            history_override=getattr(planned_turn, "history_override", None),
            should_auto_finish=bool(getattr(planned_turn, "should_auto_finish", False)),
            metadata={"planned_turn": planned_turn},
        )


def parse_datetime_utc(value: Any) -> datetime | None:
    if value is None:
        return None

    raw = str(value).strip().strip('"').strip("'")
    if not raw:
        return None

    token_match = re.search(
        r"\d{4}-\d{2}-\d{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:?[0-9]{2})?",
        raw,
    )
    candidate = token_match.group(0) if token_match else raw
    if candidate.endswith(("Z", "z")):
        candidate = candidate[:-1] + "+00:00"
    if re.search(r"[+-][0-9]{4}$", candidate):
        candidate = f"{candidate[:-5]}{candidate[-5:-2]}:{candidate[-2:]}"

    frac_match = re.search(r"\.([0-9]+)", candidate)
    if frac_match and len(frac_match.group(1)) > 6:
        candidate = candidate.replace(frac_match.group(0), "." + frac_match.group(1)[:6], 1)

    for attempt in [candidate, candidate.replace(" ", "T", 1), candidate.replace("T", " ", 1)]:
        try:
            parsed = datetime.fromisoformat(attempt)
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def conversation_message(
    role: ConversationRole,
    content: str,
    timestamp: datetime | None = None,
) -> dict[str, str]:
    return ConversationMessage.create(role, content, timestamp).as_dict()


def normalize_conversation_history(history: list | None) -> list[dict[str, str]]:
    normalized_history: list[dict[str, str]] = []
    for item in list(history or []):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant", "system"} or not content:
            continue
        normalized_history.append(conversation_message(role, content, parse_datetime_utc(item.get("timestamp"))))
    return normalized_history
