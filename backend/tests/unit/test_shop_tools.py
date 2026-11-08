from datetime import date

import pytest

from core.trace import Tracer
from shop import tools
from shop.db import ShopDB
from shop.seed import build_database

TODAY = date(2026, 11, 8)


@pytest.fixture
def db(tmp_path):
    return ShopDB(build_database(tmp_path / "shop.db", today=TODAY))


@pytest.fixture
def ctx(db, tmp_path):
    """Context for James Carter (C002, three orders)."""
    return tools.ToolContext(db=db, session_id="s1", customer_id="C002", tracer=Tracer("s1", tmp_path), today=TODAY)


def run(tool, ctx, **args):
    return tools.run_tool(tool, ctx, args, agent="orders")


def test_normalize_order_id():
    assert tools.normalize_order_id("SE-1042") == "SE-1042"
    assert tools.normalize_order_id("se 1042") == "SE-1042"
    assert tools.normalize_order_id("1042") == "SE-1042"
    assert tools.normalize_order_id("10") is None


def test_spoken_date():
    assert tools.spoken_date("2026-11-10") == "Tuesday 10 November"


def test_lookup_customer_by_phone(ctx):
    found = tools.run_tool(tools.LOOKUP_CUSTOMER, ctx, {"phone": "07700 900 101"}, agent="code")
    assert found == {"found": True, "customer_id": "C001", "first_name": "Sara", "last_name": "Benali"}
    missing = tools.run_tool(tools.LOOKUP_CUSTOMER, ctx, {"phone": "0123"}, agent="code")
    assert missing["found"] is False


def test_list_my_orders_only_shows_own_orders(ctx):
    result = run(tools.LIST_MY_ORDERS, ctx)
    assert result["count"] == 3
    assert {order["id"] for order in result["orders"]} == {"SE-1051", "SE-1052", "SE-1053"}


def test_get_order_of_someone_else_is_not_found(ctx):
    result = run(tools.GET_ORDER, ctx, order_id="SE-1042")  # Sara's order
    assert "not found" in result["error"]


def test_get_order_return_check_inside_window(ctx):
    result = run(tools.GET_ORDER, ctx, order_id="1051")
    check = result["return_check"]
    assert check["delivered_days_ago"] == 10
    assert check["within_window"] is True
    assert check["can_return"] is True
    assert check["return_deadline"] == "2026-11-28"


def test_get_order_return_check_too_late(ctx):
    check = run(tools.GET_ORDER, ctx, order_id="SE-1053")["return_check"]
    assert check["delivered_days_ago"] == 45
    assert check["within_window"] is False
    assert check["can_return"] is False


def test_get_order_return_check_not_delivered(ctx):
    check = run(tools.GET_ORDER, ctx, order_id="SE-1052")["return_check"]
    assert check == {"can_return": False, "reason": "The order has not been delivered yet."}


def test_non_returnable_items_are_listed(db, ctx):
    ctx.customer_id = "C005"
    check = run(tools.GET_ORDER, ctx, order_id="SE-1081")["return_check"]
    assert check["non_returnable_items"] == ["Cotton boxer briefs, 3-pack"]
    assert check["returnable_items"] == ["Linen shirt"]


def test_track_delayed_delivery_shows_both_dates(ctx):
    ctx.customer_id = "C003"
    result = run(tools.TRACK_DELIVERY, ctx, order_id="SE-1061")
    assert result["status"] == "delayed"
    assert result["original_date"] == "2026-11-05"
    assert result["expected_date_spoken"] == "Tuesday 10 November"


def test_order_tools_need_a_verified_customer(ctx):
    ctx.customer_id = None
    assert "not been verified" in run(tools.LIST_MY_ORDERS, ctx)["error"]
    assert "not been verified" in run(tools.TRACK_DELIVERY, ctx, order_id="SE-1051")["error"]


def test_search_faq(ctx):
    result = run(tools.SEARCH_FAQ, ctx, query="how much is shipping")
    assert result["results"][0]["question"] == "How much does delivery cost?"
    assert run(tools.SEARCH_FAQ, ctx, query="zzz")["results"] == []


def test_get_return_policy(ctx):
    assert list(run(tools.GET_RETURN_POLICY, ctx, topic="window")["policy"]) == ["window"]
    assert len(run(tools.GET_RETURN_POLICY, ctx)["policy"]) >= 5


def test_create_ticket_numbers_go_up(db, ctx):
    first = run(tools.CREATE_TICKET, ctx, subject="Broken lamp", details="Arrived broken", order_id="1052")
    second = run(tools.CREATE_TICKET, ctx, subject="Other", details="Other")
    assert first["ticket_number"] == 4801
    assert second["ticket_number"] == 4802
    row = db.query_one("SELECT * FROM tickets WHERE number = 4801")
    assert row["customer_id"] == "C002"
    assert row["order_id"] == "SE-1052"
    assert row["session_id"] == "s1"


def test_transfer_to_human_saves_a_handoff(db, ctx):
    result = run(tools.TRANSFER_TO_HUMAN, ctx, reason="Wants a refund")
    assert result["status"] == "waiting"
    assert db.query_one("SELECT reason FROM handoffs")["reason"] == "Wants a refund"


def test_bad_arguments_return_errors(ctx):
    assert "Missing" in run(tools.GET_ORDER, ctx)["error"]
    assert "not valid JSON" in tools.run_tool(tools.GET_ORDER, ctx, "{oops", agent="orders")["error"]
    assert "not a valid order number" in run(tools.GET_ORDER, ctx, order_id="abc")["error"]
    # Unknown arguments are dropped, not passed to the function.
    assert run(tools.GET_ORDER, ctx, order_id="SE-1051", customer_id="C001")["order_id"] == "SE-1051"


def test_every_tool_call_is_traced_with_its_duration(ctx):
    run(tools.TRACK_DELIVERY, ctx, order_id="SE-1051")
    [line] = ctx.tracer.read()
    assert line["kind"] == "tool_call"
    assert line["model_or_tool"] == "track_delivery"
    assert line["input"] == {"order_id": "SE-1051"}
    assert line["output"]["status"] == "delivered"
    assert line["duration_ms"] < 1000


def test_tool_schemas_have_openai_shape():
    for tool in tools.SUPERVISOR_TOOLS + tools.ORDERS_TOOLS:
        schema = tool.schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == tool.name
        assert schema["function"]["parameters"]["type"] == "object"
