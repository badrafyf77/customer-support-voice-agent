import json
import threading
from datetime import date

import pytest

from agents.support.supervisor import (
    CALL_LIMIT_END_TEXT,
    CALL_LIMIT_WARNING_TEXT,
    SLOW_JOB_TEXT,
    Supervisor,
    SupervisorSettings,
)
from core.trace import Tracer
from fakes import FakeLLM, call, say
from shop.db import ShopDB
from shop.seed import build_database

TODAY = date(2026, 11, 8)
SARA_PHONE = "07700900101"


def orders_answer(status, message, order_ids=()):
    return say(json.dumps({"status": status, "message": message, "order_ids": list(order_ids)}))


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def make(tmp_path):
    db = ShopDB(build_database(tmp_path / "shop.db", today=TODAY))

    def build(supervisor_replies=(), orders_replies=(), **settings):
        ready = threading.Event()
        clock = Clock()
        sup = Supervisor(
            FakeLLM(list(supervisor_replies)),
            FakeLLM(list(orders_replies)),
            db,
            Tracer("s1", tmp_path),
            "s1",
            SupervisorSettings(slow_tool_seconds=0, **settings),
            on_background_ready=ready.set,
            today=TODAY,
            clock=clock,
        )
        sup.ready = ready
        sup.clock_value = clock
        return sup

    build.db = db
    return build


def speak(generator):
    return "".join(generator)


def verify(sup):
    speak(sup.greeting())
    speak(sup.respond(SARA_PHONE))
    return speak(sup.respond("yes"))


def kinds(sup):
    return [line["kind"] for line in sup.tracer.read()]


def test_identity_comes_first_and_the_ai_waits(make):
    sup = make()
    assert "phone number" in speak(sup.greeting())
    assert speak(sup.respond(SARA_PHONE)) == "Thank you. Am I speaking with Sara Benali?"
    assert sup.llm.requests == []  # no AI before identity is verified
    assert speak(sup.respond("yes")) == "Thanks, Sara. How can I help you today?"
    assert sup.ctx.customer_id == "C001"
    assert "Sara Benali" in sup.messages[0]["content"]


def test_failed_identity_transfers_and_finishes(make):
    sup = make()
    for _ in range(3):
        last = speak(sup.respond("01234 567890"))
    assert "colleague" in last
    assert sup.finished and sup.finish_reason == "identity_failed"
    assert make.db.query_one("SELECT reason FROM handoffs")["reason"] == "Identity could not be confirmed."
    assert speak(sup.respond("hello?")) == ""


def test_faq_answer_uses_the_tool(make):
    sup = make([call("search_faq", query="delivery cost"), say("Standard delivery is 3 pounds 99.")])
    verify(sup)
    assert speak(sup.respond("How much is delivery?")) == "Standard delivery is 3 pounds 99."
    tool_names = [line["model_or_tool"] for line in sup.tracer.read() if line["kind"] == "tool_call"]
    assert "search_faq" in tool_names


def test_orders_question_runs_in_the_background(make):
    sup = make(
        supervisor_replies=[
            call("ask_orders_agent", request="Where is order SE-1042?"),
            say("Let me check that for you, it'll take a few seconds."),
            say("Your headphones arrive on Tuesday 10 November."),
        ],
        orders_replies=[
            call("track_delivery", order_id="SE-1042"),
            orders_answer("done", "SE-1042 arrives Tuesday 10 November.", ["SE-1042"]),
        ],
    )
    verify(sup)
    assert speak(sup.respond("Where is my order SE-1042?")) == "Let me check that for you, it'll take a few seconds."

    assert sup.ready.wait(5), "the background result never arrived"
    assert sup.has_background_results()
    assert speak(sup.respond_to_background()) == "Your headphones arrive on Tuesday 10 November."
    assert not sup.has_background_results()

    # The supervisor model saw the orders result as a system message.
    last_request = sup.llm.requests[-1]["messages"]
    assert last_request[-1]["role"] == "system"
    assert '"status": "done"' in last_request[-1]["content"]

    lines = sup.tracer.read()
    agent_call = next(line for line in lines if line["kind"] == "agent_call")
    orders_tool = next(line for line in lines if line["kind"] == "tool_call" and line["agent"] == "orders")
    assert orders_tool["parent_id"] == agent_call["event_id"]
    assert orders_tool["model_or_tool"] == "track_delivery"


def test_second_question_is_answered_while_the_job_runs(make):
    release = threading.Event()

    def slow_orders_reply(messages):
        release.wait(5)
        return orders_answer("done", "SE-1042 arrives Tuesday.", ["SE-1042"])

    sup = make(
        supervisor_replies=[
            call("ask_orders_agent", request="Where is SE-1042?"),
            say("I'm checking that now."),
            call("search_faq", query="opening hours"),
            say("We're open every day from 8 am to 8 pm."),
            say("Your order arrives Tuesday."),
        ],
        orders_replies=[slow_orders_reply],
    )
    verify(sup)
    speak(sup.respond("Where is SE-1042?"))
    assert not sup.has_background_results()
    assert speak(sup.respond("Also, when are you open?")) == "We're open every day from 8 am to 8 pm."

    release.set()
    assert sup.ready.wait(5)
    assert speak(sup.respond_to_background()) == "Your order arrives Tuesday."


def test_only_one_orders_job_at_a_time(make):
    release = threading.Event()

    def slow_orders_reply(messages):
        release.wait(5)
        return orders_answer("done", "ok")

    sup = make(
        supervisor_replies=[
            call("ask_orders_agent", request="Where is SE-1042?"),
            call("ask_orders_agent", request="And my other order?"),
            say("Checking."),
        ],
        orders_replies=[slow_orders_reply],
    )
    verify(sup)
    speak(sup.respond("Where are my orders?"))
    second_result = json.loads(sup.llm.requests[2]["messages"][-1]["content"])
    assert second_result["status"] == "busy"
    release.set()
    sup.wait_for_jobs(5)
    assert sup.job_count == 1


def test_slow_job_gets_a_fixed_message(make):
    release = threading.Event()

    def slow_orders_reply(messages):
        release.wait(5)
        return orders_answer("done", "ok")

    sup = make(
        supervisor_replies=[call("ask_orders_agent", request="Where is SE-1042?"), say("Checking.")],
        orders_replies=[slow_orders_reply],
        job_timeout_seconds=0.05,
    )
    verify(sup)
    speak(sup.respond("Where is SE-1042?"))
    assert sup.ready.wait(5)
    assert speak(sup.respond_to_background()).strip() == SLOW_JOB_TEXT
    assert "limit_hit" in kinds(sup)
    release.set()
    sup.wait_for_jobs(5)


def test_transfer_finishes_the_call(make):
    sup = make([call("transfer_to_human", reason="Customer wants a refund"), say("I'll pass you to a colleague now.")])
    verify(sup)
    assert speak(sup.respond("I want a refund")) == "I'll pass you to a colleague now."
    assert sup.finished and sup.finish_reason == "transferred_to_human"


def test_problem_said_before_the_phone_number_is_answered(make):
    sup = make([call("ask_orders_agent", request="My parcel SE-1042 is late"), say("Let me check that.")])
    speak(sup.respond("Hi, my parcel SE-1042 is late"))
    speak(sup.respond(SARA_PHONE))
    out = speak(sup.respond("yes"))
    assert out == "Thanks, Sara. Let me check that."
    assert sup.llm.requests[0]["messages"][1] == {"role": "user", "content": "Hi, my parcel SE-1042 is late"}
    sup.wait_for_jobs(5)


def test_interrupted_answer_keeps_only_what_was_heard(make):
    sup = make([say("Your parcel is ", "on its way and ", "arrives Tuesday.")])
    verify(sup)
    stream = sup.respond("Where is my parcel?")
    assert next(stream) == "Your parcel is "
    stream.close()
    assert sup.messages[-1]["content"] == "Your parcel is  [interrupted by the customer]"
    spoken = [line for line in sup.tracer.read() if line["kind"] == "spoken"][-1]
    assert spoken["interrupted"] is True


def test_call_time_limits(make):
    sup = make()
    verify(sup)
    assert speak(sup.call_time_check()) == ""
    sup.clock_value.now = 14 * 60
    assert speak(sup.call_time_check()) == CALL_LIMIT_WARNING_TEXT
    assert speak(sup.call_time_check()) == ""  # warn only once
    sup.clock_value.now = 15 * 60
    assert speak(sup.call_time_check()) == CALL_LIMIT_END_TEXT
    assert sup.finished and sup.finish_reason == "call_time_limit"


def test_model_error_gives_a_spoken_apology(make):
    class BrokenLLM(FakeLLM):
        def stream_chat(self, *args, **kwargs):
            raise ConnectionError("down")
            yield  # pragma: no cover

    sup = make()
    sup.llm = BrokenLLM()
    verify(sup)
    assert "technical problem" in speak(sup.respond("Hello?"))
    assert "error" in kinds(sup)


def test_every_customer_turn_and_answer_is_traced(make):
    sup = make([say("Hello!")])
    verify(sup)
    speak(sup.respond("Hi"))
    lines = sup.tracer.read()
    said = [line["input"] for line in lines if line["kind"] == "user_said"]
    spoken = [line["output"] for line in lines if line["kind"] == "spoken"]
    assert said == [SARA_PHONE, "yes", "Hi"]
    assert spoken[-1] == "Hello!"
    assert lines[-1]["turn_id"] == 3
