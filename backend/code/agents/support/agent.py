"""ShopEasy support agent: plugs the supervisor into the shared voice runtime.

The voice runtime builds one ``SupportAgent`` per WebSocket call. Each turn is
returned as ``AgentResult.speak_stream(...)``: the pipeline speaks whatever the
supervisor's generator yields, while the supervisor runs its own model calls,
tools and background jobs inside it.
"""
from __future__ import annotations

from typing import Any, Callable

from agents.base import BaseAgent
from agents.support.supervisor import Supervisor, build_supervisor
from core.config import load_agent_config
from core.models import AgentResult, SessionContext


class SupportAgent(BaseAgent):
    system_prompt = None
    conversation_history: list[dict[str, str]] = []

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        orders_config: dict[str, Any] | None = None,
        supervisor_factory: Callable[[str], Supervisor] | None = None,
    ):
        self.config = config if config is not None else load_agent_config("support")
        self.orders_config = orders_config if orders_config is not None else load_agent_config("orders")
        self._supervisor_factory = supervisor_factory or (
            lambda session_id: build_supervisor(session_id, self.config, self.orders_config)
        )
        self.supervisor: Supervisor | None = None

    def _get_supervisor(self, session: SessionContext) -> Supervisor:
        if self.supervisor is None:
            self.supervisor = self._supervisor_factory(session.session_id)
        return self.supervisor

    async def run_turn(self, text: str, session: SessionContext) -> AgentResult:
        supervisor = self._get_supervisor(session)
        user_turn = str(text or "").strip()

        if not user_turn:
            if session.metadata.get("reason") == "session_ready":
                return AgentResult.speak_stream(supervisor.greeting, label="[greeting]")
            return AgentResult.ignore()
        if supervisor.finished:
            return AgentResult.ignore()
        return AgentResult.speak_stream(lambda: supervisor.respond(user_turn), label=user_turn)

    async def idle_turn(self, session: SessionContext) -> AgentResult:
        supervisor = self.supervisor
        if supervisor is None:
            return AgentResult.ignore()
        if supervisor.finished:
            # The goodbye has been spoken (nobody is speaking any more): end the call.
            return AgentResult.finish()
        if supervisor.has_background_results():
            return AgentResult.speak_stream(supervisor.respond_to_background, label="[background result]")
        if supervisor.call_time_due():
            return AgentResult.speak_stream(supervisor.call_time_check, label="[call time]")
        return AgentResult.ignore()

    async def close_session(self, conn_state: Any, reason: str) -> None:
        if self.supervisor is not None:
            self.supervisor.close(reason)


def build_support_agent(context: dict[str, Any] | None = None) -> SupportAgent:
    return SupportAgent()
