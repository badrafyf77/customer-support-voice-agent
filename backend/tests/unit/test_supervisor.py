import json
import threading
from datetime import date

import pytest

from agents.support.supervisor import (
    CALL_LIMIT_END_TEXT,
    CALL_LIMIT_WARNING_TEXT,
    INTERRUPTED_MARK,
    SLOW_JOB_TEXT,
    Supervisor,
    SupervisorSettings,
)
from core.trace import Tracer
from fakes import FakeChatModel, call, say
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
            FakeChatModel(replies=list(supervisor_replies)),
            FakeChatModel(replies=list(orders_replies)),
            db,
            Tracer("s1", tmp_path),
            "s1",
            SupervisorSettings(**settings),
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
    assert sup.model.requests == []  # no AI before identity is verified
    assert speak(sup.respond("yes")) == "Thanks, Sara. How can I help you today?"
    assert sup.graph.get_state(sup.config).values["customer"]["customer_id"] == "C001"


def test_the_model_knows_the_customer(make):
    sup = make([say("Hello!")])
    verify(sup)
    speak(sup.respond("Hi"))
    assert "Sara Benali" in sup.model.requests[0]["messages"][0].text


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
    tools = [line["model_or_tool"] for line in sup.tracer.read() if line["kind"] == "tool_call"]
    assert "search_faq" in tools


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
    assert speak(sup.respond_to_background()) == "Your headphones arrive on Tuesday 10 November."
    assert not sup.has_background_results()

    # The supervisor model saw the orders result as a system message.
    last_seen = sup.model.requests[-1]["messages"][-1]
    assert last_seen.type == "system" and '"status": "done"' in last_seen.text

    lines = sup.tracer.read()
    agent_call = next(line for line in lines if line["kind"] == "agent_call")
    orders_tool = next(line for line in lines if line["kind"] == "tool_call" and line["agent"] == "orders")
    assert orders_tool["parent_id"] == agent_call["event_id"]
    assert orders_tool["input"] == {"order_id": "SE-1042"}


def test_orders_agent_gets_the_verified_customer(make):
    sup = make(
        [call("ask_orders_agent", request="List my orders"), say("Checking.")],
        [call("list_my_orders"), orders_answer("done", "ok")],
    )
    verify(sup)
    speak(sup.respond("What did I order?"))
    sup.wait_for_jobs(5)
    tool_line = next(line for line in sup.tracer.read() if line["kind"] == "tool_call" and line["agent"] == "orders")
    assert [order["id"] for order in tool_line["output"]["orders"]] == ["SE-1042"]


def test_orders_agent_can_run_inside_the_tool_call(make):
    sup = make(
        [call("ask_orders_agent", request="Where is SE-1042?"), say("It arrives Tuesday.")],
        [call("track_delivery", order_id="SE-1042"), orders_answer("done", "Tuesday", ["SE-1042"])],
        orders_in_background=False,
    )
    verify(sup)
    assert speak(sup.respond("Where is SE-1042?")) == "It arrives Tuesday."
    tool_result = json.loads(sup.model.requests[1]["messages"][-1].content)
    assert tool_result["status"] == "done"
    assert not sup.has_background_results()


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
    assert json.loads(sup.model.requests[2]["messages"][-1].content)["status"] == "busy"
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
    assert sup.messages[-1].text == SLOW_JOB_TEXT
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
    assert speak(sup.respond("yes")) == "Thanks, Sara. Let me check that."
    note = sup.model.requests[0]["messages"][-1]
    assert note.type == "system" and "my parcel SE-1042 is late" in note.text
    sup.wait_for_jobs(5)


def test_interrupted_answer_keeps_only_what_was_heard(make):
    sup = make([say("Your parcel is ", "on its way and ", "arrives Tuesday.")])
    verify(sup)
    stream = sup.respond("Where is my parcel?")
    assert next(stream) == "Your parcel is "
    stream.close()  # the customer started talking
    assert sup.messages[-1].text == "Your parcel is " + INTERRUPTED_MARK
    spoken = [line for line in sup.tracer.read() if line["kind"] == "spoken"][-1]
    assert spoken["interrupted"] is True


def test_call_time_limits(make):
    sup = make()
    verify(sup)
    assert speak(sup.call_time_check()) == ""
    sup.clock_value.now = 14 * 60
    assert sup.call_time_due()
    assert speak(sup.call_time_check()) == CALL_LIMIT_WARNING_TEXT
    assert speak(sup.call_time_check()) == ""  # warn only once
    sup.clock_value.now = 15 * 60
    assert speak(sup.call_time_check()) == CALL_LIMIT_END_TEXT
    assert sup.finished and sup.finish_reason == "call_time_limit"


def test_model_error_gives_a_spoken_apology(make):
    def broken(messages):
        raise ConnectionError("down")

    sup = make([broken])
    verify(sup)
    assert "technical problem" in speak(sup.respond("Hello?"))
    assert "error" in kinds(sup)


def test_every_customer_turn_and_answer_is_traced(make):
    sup = make([say("Hello!")])
    verify(sup)
    speak(sup.respond("Hi"))
    sup.close("test_done")
    lines = sup.tracer.read()
    assert [line["input"] for line in lines if line["kind"] == "user_said"] == [SARA_PHONE, "yes", "Hi"]
    assert [line["output"] for line in lines if line["kind"] == "spoken"][-1] == "Hello!"
    assert lines[0]["kind"] == "call_start" and lines[-1]["kind"] == "call_end"
    assert lines[-1]["output"]["customer_id"] == "C001"
