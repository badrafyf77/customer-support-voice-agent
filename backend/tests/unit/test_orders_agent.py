import json
from datetime import date

import pytest

from agents.orders.agent import RESULT_FORMAT, OrdersAgent, parse_result
from core.trace import Tracer
from fakes import FakeLLM, call, say
from shop.db import ShopDB
from shop.seed import build_database
from shop.tools import ToolContext

TODAY = date(2026, 11, 8)


def answer(status, message, order_ids=()):
    return say(json.dumps({"status": status, "message": message, "order_ids": list(order_ids)}))


@pytest.fixture
def ctx(tmp_path):
    db = ShopDB(build_database(tmp_path / "shop.db", today=TODAY))
    return ToolContext(db=db, session_id="s1", customer_id="C002", tracer=Tracer("s1", tmp_path), today=TODAY)


def test_done_after_a_tool(ctx):
    llm = FakeLLM([
        call("track_delivery", order_id="SE-1052"),
        answer("done", "SE-1052 is being prepared and should arrive Thursday 12 November.", ["SE-1052"]),
    ])
    result = OrdersAgent(llm, ctx).run_job("Where is order SE-1052?")

    assert result.status == "done"
    assert result.order_ids == ["SE-1052"]
    assert result.tool_calls == 1
    # The real tool ran: the model saw the delivery data.
    tool_message = llm.requests[1]["messages"][-1]
    assert json.loads(tool_message["content"])["status"] == "preparing"
    assert llm.requests[0]["response_format"] == RESULT_FORMAT


def test_needs_info(ctx):
    llm = FakeLLM([
        call("list_my_orders"),
        answer("needs_info", "The customer has 3 orders: SE-1052 desk lamp, SE-1051 speaker, SE-1053 shoes."),
    ])
    result = OrdersAgent(llm, ctx).run_job("Where is my order?")
    assert result.status == "needs_info"
    assert json.loads(llm.requests[1]["messages"][-1]["content"])["count"] == 3


def test_cannot_for_someone_elses_order(ctx):
    llm = FakeLLM([
        call("get_order", order_id="SE-1042"),
        answer("cannot", "Order SE-1042 is not on this customer's account."),
    ])
    result = OrdersAgent(llm, ctx).run_job("Tell me about SE-1042")
    assert result.status == "cannot"
    assert "not found" in json.loads(llm.requests[1]["messages"][-1]["content"])["error"]


def test_tool_limit(ctx):
    llm = FakeLLM([call("list_my_orders") for _ in range(2)] + [answer("cannot", "I could not finish.")])
    result = OrdersAgent(llm, ctx, max_tool_calls=2).run_job("Check everything")
    assert result.status == "cannot"
    assert result.tool_calls == 2
    assert llm.requests[-1]["tool_choice"] == "none"


def test_unknown_tool_is_an_error_not_a_crash(ctx):
    llm = FakeLLM([call("request_refund", order_id="SE-1051"), answer("cannot", "Refunds are handled by a colleague.")])
    result = OrdersAgent(llm, ctx).run_job("Refund SE-1051")
    assert result.status == "cannot"
    assert "no tool called request_refund" in llm.requests[1]["messages"][-1]["content"]


def test_model_failure_returns_cannot(ctx):
    class BrokenLLM(FakeLLM):
        def stream_chat(self, *args, **kwargs):
            raise ConnectionError("network down")
            yield  # pragma: no cover

    result = OrdersAgent(BrokenLLM(), ctx).run_job("Where is SE-1052?")
    assert result.status == "cannot"
    assert "error" in [line["kind"] for line in ctx.tracer.read()]


def test_parse_result_rejects_bad_json():
    assert parse_result("not json", 0).status == "cannot"
    assert parse_result('{"status": "maybe", "message": "x"}', 0).status == "cannot"
    assert parse_result('{"status": "done", "message": " ok ", "order_ids": []}', 1).message == "ok"


def test_trace_lines_hang_under_the_supervisor_call(ctx):
    tracer = ctx.tracer
    llm = FakeLLM([call("track_delivery", order_id="SE-1052"), answer("done", "ok", ["SE-1052"])])
    with tracer.span("agent_call", "supervisor", model_or_tool="ask_orders_agent") as parent:
        OrdersAgent(llm, ctx).run_job("Where is SE-1052?")

    lines = tracer.read()
    agent_call = next(line for line in lines if line["kind"] == "agent_call")
    llm_calls = [line for line in lines if line["kind"] == "llm_call"]
    tool_call = next(line for line in lines if line["kind"] == "tool_call")
    result = next(line for line in lines if line["kind"] == "agent_result")

    assert all(line["parent_id"] == parent.event_id for line in llm_calls)
    assert tool_call["parent_id"] == parent.event_id
    assert result["parent_id"] == parent.event_id
    assert result["output"]["status"] == "done"
    assert agent_call["parent_id"] is None


def test_prompt_has_todays_date(ctx):
    assert "Sunday 8 November (2026-11-08)" in OrdersAgent(FakeLLM(), ctx).system_prompt()
