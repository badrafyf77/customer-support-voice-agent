"""Run the real supervisor with text only: no speech-to-text, no text-to-speech.

For each customer line it collects what the agent says, waits for the orders
agent, then collects the background answer too. Each turn keeps the trace lines
written while it ran, so the scenario checks can look at exactly what happened.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from agents.support.supervisor import Supervisor, SupervisorSettings, build_supervisor
from core.config import load_agent_config
from core.trace import Tracer, default_trace_dir
from shop.db import ShopDB
from shop.seed import build_database

MAX_BACKGROUND_ROUNDS = 3


@dataclass
class TurnRun:
    said: str
    spoken: str
    background: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False

    @property
    def all_spoken(self) -> str:
        return " ".join([self.spoken, *self.background]).strip()


@dataclass
class ConversationRun:
    greeting: str
    turns: list[TurnRun]
    trace_path: Path
    supervisor: Supervisor


def run_conversation(
    lines: list[str],
    session_id: str,
    trace_dir: Path | None = None,
    today: date | None = None,
    job_timeout: float = 60.0,
    llm: Any = None,
    orders_llm: Any = None,
) -> ConversationRun:
    """Play ``lines`` as the customer, on a fresh copy of the ShopEasy database.

    Pass ``llm`` and ``orders_llm`` to use fake models instead of the configured ones.
    """
    db = ShopDB(build_database(Path(tempfile.mkdtemp()) / "shop.db", today=today))
    tracer = Tracer(session_id, trace_dir or default_trace_dir() / "scenarios")
    if llm is not None:
        supervisor = Supervisor(llm, orders_llm, db, tracer, session_id, SupervisorSettings(slow_tool_seconds=0), today=today)
    else:
        supervisor = build_supervisor(
            session_id,
            load_agent_config("support"),
            load_agent_config("orders"),
            db=db,
            tracer=tracer,
            today=today,
        )

    greeting = "".join(supervisor.greeting())
    turns: list[TurnRun] = []
    for line in lines:
        start = len(tracer.read())
        turn = TurnRun(said=line, spoken="".join(supervisor.respond(line)))
        for _ in range(MAX_BACKGROUND_ROUNDS):
            supervisor.wait_for_jobs(job_timeout)
            if not supervisor.has_background_results():
                break
            turn.background.append("".join(supervisor.respond_to_background()))
        turn.events = tracer.read()[start:]
        turn.finished = supervisor.finished
        turns.append(turn)
        if supervisor.finished:
            break

    supervisor.close("text_runner_done")
    return ConversationRun(greeting, turns, tracer.path, supervisor)
