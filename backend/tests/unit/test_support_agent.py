import asyncio
import json
from datetime import date

import pytest

from agents.support.agent import SupportAgent
from agents.support.supervisor import Supervisor, SupervisorSettings
from core.models import AgentResult, SessionContext
from core.trace import Tracer
from fakes import FakeChatModel, call, say
from shop.db import ShopDB
from shop.seed import build_database

TODAY = date(2026, 11, 8)


def session(reason="user_turn_completed"):
    return SessionContext(session_id="call-1", agent_name="support", metadata={"reason": reason})


def run(coroutine):
    return asyncio.run(coroutine)


def spoken(result: AgentResult) -> str:
    assert result.action == "stream"
    return "".join(result.stream())


@pytest.fixture
def agent(tmp_path):
    db = ShopDB(build_database(tmp_path / "shop.db", today=TODAY))
    supervisor_llm = FakeChatModel()
    orders_llm = FakeChatModel()

    def factory(session_id):
        return Supervisor(
            supervisor_llm, orders_llm, db, Tracer(session_id, tmp_path), session_id,
            SupervisorSettings(), today=TODAY,
        )

    support = SupportAgent(config={}, orders_config={}, supervisor_factory=factory)
    support.supervisor_llm = supervisor_llm
    support.orders_llm = orders_llm
    return support


def test_stream_result_is_lazy():
    started = []

    def stream():
        started.append(True)
        yield "hi"

    result = AgentResult.speak_stream(stream, label="x")
    assert not result.is_empty
    assert started == []  # nothing runs until the pipeline starts speaking
    assert "".join(result.stream()) == "hi"


def test_greeting_then_identity(agent):
    assert "phone number" in spoken(run(agent.run_turn("", session("session_ready"))))
    assert spoken(run(agent.run_turn("07700900101", session()))).startswith("Thank you. Am I speaking with Sara")
    assert spoken(run(agent.run_turn("yes", session()))) == "Thanks, Sara. How can I help you today?"
    assert agent.supervisor.tracer.path.name == "call-1.jsonl"


def test_other_empty_turns_are_ignored(agent):
    assert run(agent.run_turn("", session("other"))).is_empty


def test_idle_turn_gives_the_background_result(agent):
    agent.supervisor_llm.add(
        call("ask_orders_agent", request="Where is SE-1042?"),
        say("Let me check."),
        say("It arrives Tuesday."),
    )
    agent.orders_llm.add(say(json.dumps({"status": "done", "message": "Tuesday", "order_ids": ["SE-1042"]})))
    for text in ["07700900101", "yes"]:
        spoken(run(agent.run_turn(text, session())))
    assert run(agent.idle_turn(session("idle"))).is_empty

    spoken(run(agent.run_turn("Where is SE-1042?", session())))
    agent.supervisor.wait_for_jobs(5)
    result = run(agent.idle_turn(session("idle")))
    assert spoken(result) == "It arrives Tuesday."
    assert run(agent.idle_turn(session("idle"))).is_empty


def test_idle_turn_finishes_after_a_transfer(agent):
    agent.supervisor_llm.add(call("transfer_to_human", reason="refund"), say("Passing you to a colleague."))
    for text in ["07700900101", "yes"]:
        spoken(run(agent.run_turn(text, session())))
    assert spoken(run(agent.run_turn("I want a refund", session()))) == "Passing you to a colleague."
    assert run(agent.idle_turn(session("idle"))).action == "finish"
    assert run(agent.run_turn("hello?", session())).is_empty


def test_close_session_writes_call_end(agent):
    run(agent.run_turn("", session("session_ready")))
    run(agent.close_session(None, "client_disconnected"))
    run(agent.close_session(None, "client_disconnected"))  # only once
    lines = agent.supervisor.tracer.read()
    assert [line["kind"] for line in lines].count("call_end") == 1
    assert lines[0]["kind"] == "call_start"
    assert lines[-1]["input"] == "client_disconnected"
