import json
from datetime import date

import pytest

from agents.orders.agent import OrdersAgent, OrdersAnswer, parse_result
from core.trace import Tracer
from fakes import FakeChatModel, call, say
from shop.db import ShopDB
from shop.seed import build_database

TODAY = date(2026, 11, 8)


def answer(status, message, order_ids=()):
    return say(json.dumps({"status": status, "message": message, "order_ids": list(order_ids)}))


@pytest.fixture
def make(tmp_path):
    db = ShopDB(build_database(tmp_path / "shop.db", today=TODAY))
    tracer = Tracer("s1", tmp_path)

    def build(*replies, max_tool_calls=5):
        model = FakeChatModel(replies=list(replies))
        agent = OrdersAgent(model, db, tracer, max_tool_calls, TODAY, "s1")
        agent.fake = model
        return agent

    return build


def tool_result(agent, request_index):
    """The tool message the model saw in request number ``request_index``."""
    return json.loads(agent.fake.requests[request_index]["messages"][-1].content)


def test_done_after_a_tool(make):
    agent = make(
        call("track_delivery", order_id="SE-1052"),
        answer("done", "SE-1052 is being prepared and should arrive Thursday 12 November.", ["SE-1052"]),
    )
    result = agent.run_job("Where is order SE-1052?", "C002")

    assert result.status == "done"
    assert result.order_ids == ["SE-1052"]
    assert result.tool_calls == 1
    assert tool_result(agent, 1)["status"] == "preparing"  # the real tool ran
    assert agent.fake.requests[0]["response_format"] is OrdersAnswer


def test_needs_info(make):
    agent = make(call("list_my_orders"), answer("needs_info", "Which one: SE-1052 lamp, SE-1051 speaker or SE-1053 shoes?"))
    assert agent.run_job("Where is my order?", "C002").status == "needs_info"
    assert tool_result(agent, 1)["count"] == 3


def test_cannot_for_someone_elses_order(make):
    agent = make(call("get_order", order_id="SE-1042"), answer("cannot", "Order SE-1042 is not on this customer's account."))
    assert agent.run_job("Tell me about SE-1042", "C002").status == "cannot"
    assert "not found" in tool_result(agent, 1)["error"]


def test_the_customer_comes_from_code_not_the_ai(make):
    agent = make(call("list_my_orders"), answer("done", "ok"))
    agent.run_job("List my orders", "C001")
    assert [o["id"] for o in tool_result(agent, 1)["orders"]] == ["SE-1042"]


def test_tool_limit(make):
    agent = make(call("list_my_orders"), call("list_my_orders"), answer("cannot", "I could not finish."), max_tool_calls=2)
    result = agent.run_job("Check everything", "C002")
    assert result.status == "cannot"
    assert result.tool_calls == 2
    assert agent.fake.requests[-1]["tool_choice"] == "none"


def test_unknown_tool_is_an_error_not_a_crash(make):
    agent = make(call("request_refund", order_id="SE-1051"), answer("cannot", "Refunds are handled by a colleague."))
    assert agent.run_job("Refund SE-1051", "C002").status == "cannot"
    assert "no tool called request_refund" in tool_result(agent, 1)["error"]


def test_model_failure_returns_cannot(make):
    def broken(messages):
        raise ConnectionError("network down")

    agent = make(broken)
    assert agent.run_job("Where is SE-1052?", "C002").status == "cannot"
    assert "error" in [line["kind"] for line in agent.tracer.read()]


def test_parse_result_rejects_bad_json():
    assert parse_result("not json", 0).status == "cannot"
    assert parse_result('{"status": "maybe", "message": "x"}', 0).status == "cannot"
    assert parse_result('{"status": "done", "message": " ok ", "order_ids": []}', 1).message == "ok"


def test_trace_lines_hang_under_the_supervisor_call(make):
    agent = make(call("track_delivery", order_id="SE-1052"), answer("done", "ok", ["SE-1052"]))
    parent = agent.tracer.event("agent_call", "supervisor", model_or_tool="ask_orders_agent")
    agent.run_job("Where is SE-1052?", "C002", parent_id=parent)

    lines = agent.tracer.read()
    for kind in ("llm_call", "tool_call", "agent_result"):
        matching = [line for line in lines if line["kind"] == kind]
        assert matching and all(line["parent_id"] == parent for line in matching), kind
    assert next(line for line in lines if line["kind"] == "agent_result")["output"]["status"] == "done"


def test_prompt_has_todays_date(make):
    assert "Sunday 8 November (2026-11-08)" in make().system_prompt()
