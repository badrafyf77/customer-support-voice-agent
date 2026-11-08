"""Simple conversational voice agent.

This agent has no database, tools, or authentication behavior.
It only turns each finalized user transcript into the next LLM prompt.
"""
from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from core.models import AgentResult, SessionContext


SYSTEM_PROMPT = """
You are a helpful, concise voice assistant.
Speak naturally in short responses unless the user asks for detail.
""".strip()


class ChatAgent(BaseAgent):
    """Minimal agent consumed by the shared streaming session."""

    system_prompt = SYSTEM_PROMPT
    conversation_history: list[dict[str, str]] = []

    async def run_turn(self, text: str, session: SessionContext) -> AgentResult:
        user_turn = str(text or "").strip()
        if not user_turn:
            return AgentResult.ignore()
        return AgentResult.generate(user_turn)


def build_chat_agent(context: dict[str, Any] | None = None) -> ChatAgent:
    return ChatAgent()
