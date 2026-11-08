"""The ShopEasy tools: plain functions the agents are allowed to call.

The AI never runs anything itself. It asks for a tool by name, and
``run_tool`` runs it with a ``ToolContext`` that our code fills in. The
verified customer comes from that context, never from the AI, so order tools
only ever see the caller's own orders.

Each tool returns a small dictionary. Problems come back as ``{"error": ...}``
so the AI can explain them instead of the call crashing.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable

from core.trace import Tracer
from shop.db import ShopDB
from shop.seed import RETURN_WINDOW_DAYS

TICKET_NUMBER_START = 4800


@dataclass
class ToolContext:
    db: ShopDB
    session_id: str = "no-session"
    customer_id: str | None = None
    tracer: Tracer | None = None
    today: date = field(default_factory=date.today)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    func: Callable[..., dict[str, Any]]

    def schema(self) -> dict[str, Any]:
        """The tool in the format the OpenAI API expects."""
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


def _params(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": False,
    }


def run_tool(tool: Tool, ctx: ToolContext, args: dict[str, Any] | str | None, agent: str) -> dict[str, Any]:
    """Run one tool call from an agent, trace it, and never raise."""
    if isinstance(args, str):
        try:
            args = json.loads(args or "{}")
        except json.JSONDecodeError:
            args = None
    if not isinstance(args, dict):
        result: dict[str, Any] = {"error": "The tool arguments were not valid JSON."}
        if ctx.tracer:
            ctx.tracer.event("tool_call", agent, model_or_tool=tool.name, output=result)
        return result

    allowed = tool.parameters.get("properties", {})
    clean_args = {key: value for key, value in args.items() if key in allowed}
    missing = [key for key in tool.parameters.get("required", []) if clean_args.get(key) in (None, "")]

    def call() -> dict[str, Any]:
        if missing:
            return {"error": f"Missing argument(s): {', '.join(missing)}."}
        try:
            return tool.func(ctx, **clean_args)
        except Exception as exc:  # a broken tool must not end the call
            return {"error": f"The {tool.name} tool failed: {type(exc).__name__}."}

    if not ctx.tracer:
        return call()
    with ctx.tracer.span("tool_call", agent, input=clean_args, model_or_tool=tool.name) as span:
        result = call()
        span.output = result
    return result


# --- Helpers -------------------------------------------------------------------


def normalize_phone(text: str) -> str:
    return re.sub(r"\D", "", text or "")


def normalize_order_id(text: str) -> str | None:
    """Accept "SE-1042", "se 1042", "1042" or "order number one zero four two" digits."""
    digits = re.sub(r"\D", "", text or "")
    return f"SE-{digits}" if len(digits) == 4 else None


def spoken_date(iso_date: str | None) -> str | None:
    """2026-11-10 -> "Tuesday 10 November" (easy for the agent to say)."""
    if not iso_date:
        return None
    value = date.fromisoformat(iso_date)
    return f"{value.strftime('%A')} {value.day} {value.strftime('%B')}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_customer(ctx: ToolContext) -> dict[str, Any] | None:
    if not ctx.customer_id:
        return {"error": "The customer's identity has not been verified yet."}
    return None


def _own_order(ctx: ToolContext, order_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return (order, error). Orders of other customers look exactly like missing ones."""
    normalized = normalize_order_id(order_id)
    if not normalized:
        return None, {"error": f"'{order_id}' is not a valid order number. Order numbers look like SE-1042."}
    order = ctx.db.query_one(
        "SELECT * FROM orders WHERE id = ? AND customer_id = ?", (normalized, ctx.customer_id)
    )
    if not order:
        return None, {"error": f"Order {normalized} was not found on this customer's account."}
    return order, None


def _delivery_info(row: dict[str, Any]) -> dict[str, Any]:
    info = {
        "status": row["status"],
        "carrier": row["carrier"],
        "tracking_number": row["tracking_number"],
        "shipped_date": row["shipped_date"],
        "expected_date": row["expected_date"],
        "expected_date_spoken": spoken_date(row["expected_date"]),
        "delivered_date": row["delivered_date"],
        "delivered_date_spoken": spoken_date(row["delivered_date"]),
        "last_location": row["last_location"],
        "last_update": row["last_update"],
    }
    if row["status"] == "delayed":
        info["original_date"] = row["original_date"]
        info["original_date_spoken"] = spoken_date(row["original_date"])
    return {key: value for key, value in info.items() if value is not None}


def _return_check(ctx: ToolContext, order: dict[str, Any], delivery: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    """Work out in code whether a return is possible, so the AI doesn't guess."""
    blocked = [item["product"] for item in items if not item["returnable"]]
    if order["status"] == "cancelled":
        return {"can_return": False, "reason": "The order was cancelled, so there is nothing to return."}
    if not delivery.get("delivered_date"):
        return {"can_return": False, "reason": "The order has not been delivered yet."}

    days = (ctx.today - date.fromisoformat(delivery["delivered_date"])).days
    deadline = date.fromordinal(date.fromisoformat(delivery["delivered_date"]).toordinal() + RETURN_WINDOW_DAYS)
    check = {
        "delivered_days_ago": days,
        "return_window_days": RETURN_WINDOW_DAYS,
        "return_deadline": deadline.isoformat(),
        "return_deadline_spoken": spoken_date(deadline.isoformat()),
        "within_window": days <= RETURN_WINDOW_DAYS,
        "non_returnable_items": blocked,
    }
    returnable = [item["product"] for item in items if item["returnable"]]
    check["can_return"] = check["within_window"] and bool(returnable)
    check["returnable_items"] = returnable if check["within_window"] else []
    return check


# --- Tools for plain code only (identity steps) --------------------------------


def lookup_customer(ctx: ToolContext, phone: str) -> dict[str, Any]:
    digits = normalize_phone(phone)
    row = ctx.db.query_one("SELECT id, first_name, last_name FROM customers WHERE phone = ?", (digits,))
    if not row:
        return {"found": False, "phone": digits}
    return {"found": True, "customer_id": row["id"], "first_name": row["first_name"], "last_name": row["last_name"]}


LOOKUP_CUSTOMER = Tool(
    "lookup_customer",
    "Find a customer by phone number. Used by the identity steps only.",
    _params({"phone": {"type": "string"}}, ["phone"]),
    lookup_customer,
)


# --- Supervisor tools ------------------------------------------------------------


def search_faq(ctx: ToolContext, query: str) -> dict[str, Any]:
    words = set(re.findall(r"[a-z]+", query.lower())) - {"the", "a", "an", "i", "my", "do", "you", "is", "can", "how", "what", "to", "of"}
    scored = []
    for row in ctx.db.query("SELECT question, answer, keywords FROM faq"):
        haystack = set(re.findall(r"[a-z]+", f"{row['keywords']} {row['question']}".lower()))
        score = len(words & haystack)
        if score:
            scored.append((score, row))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = [{"question": row["question"], "answer": row["answer"]} for _, row in scored[:3]]
    if not results:
        return {"results": [], "note": "No FAQ entry matches this question."}
    return {"results": results}


def get_return_policy(ctx: ToolContext, topic: str | None = None) -> dict[str, Any]:
    rows = ctx.db.query("SELECT topic, text FROM return_policy")
    if topic:
        match = [row for row in rows if row["topic"] == topic]
        if match:
            return {"policy": {match[0]["topic"]: match[0]["text"]}}
    return {"policy": {row["topic"]: row["text"] for row in rows}}


def create_ticket(ctx: ToolContext, subject: str, details: str, order_id: str | None = None) -> dict[str, Any]:
    if error := _require_customer(ctx):
        return error
    row_id = ctx.db.execute(
        "INSERT INTO tickets (number, customer_id, order_id, subject, details, session_id, created_at)"
        " VALUES ((SELECT COALESCE(MAX(number), ?) + 1 FROM tickets), ?, ?, ?, ?, ?, ?)",
        (TICKET_NUMBER_START, ctx.customer_id, normalize_order_id(order_id or "") or order_id, subject, details, ctx.session_id, _now()),
    )
    number = ctx.db.query_one("SELECT number FROM tickets WHERE id = ?", (row_id,))["number"]
    return {"ticket_number": number, "status": "open", "message": "Our team will follow up by email within one working day."}


def transfer_to_human(ctx: ToolContext, reason: str) -> dict[str, Any]:
    handoff_id = ctx.db.execute(
        "INSERT INTO handoffs (customer_id, reason, session_id, created_at) VALUES (?, ?, ?, ?)",
        (ctx.customer_id, reason, ctx.session_id, _now()),
    )
    return {"handoff_id": handoff_id, "status": "waiting", "message": "A colleague will take over this call."}


RETURN_POLICY_TOPICS = [
    "window", "condition", "non_returnable", "how_to_return",
    "refunds", "exchanges", "damaged_items", "cancelled_orders",
]

SEARCH_FAQ = Tool(
    "search_faq",
    "Search ShopEasy's FAQ for general questions that are not about a specific order: delivery "
    "costs and times, payment methods, cancelling, changing an address, opening hours, discounts, "
    "gift cards, passwords. Returns up to 3 matching questions with their answers.",
    _params({"query": {"type": "string", "description": "The customer's question in a few words."}}, ["query"]),
    search_faq,
)

GET_RETURN_POLICY = Tool(
    "get_return_policy",
    "Read ShopEasy's return and refund rules. Give a topic to get one section, or leave it out "
    "to get the whole policy.",
    _params({"topic": {"type": "string", "enum": RETURN_POLICY_TOPICS, "description": "Optional section."}}),
    get_return_policy,
)

CREATE_TICKET = Tool(
    "create_ticket",
    "Open a support ticket so the ShopEasy team follows up by email. Use it for problems we "
    "can't solve during the call, such as a lost package or a damaged item. Returns a ticket "
    "number to read to the customer.",
    _params(
        {
            "subject": {"type": "string", "description": "A short title, e.g. 'Lost package SE-1071'."},
            "details": {"type": "string", "description": "What happened and what the customer wants."},
            "order_id": {"type": "string", "description": "The order number, if the ticket is about one order."},
        },
        ["subject", "details"],
    ),
    create_ticket,
)

TRANSFER_TO_HUMAN = Tool(
    "transfer_to_human",
    "Transfer the call to a human colleague. Use it when the customer asks for a person, and "
    "for every risky request such as a refund, a payment problem or an account change. The "
    "call ends for you after this.",
    _params({"reason": {"type": "string", "description": "Why the customer needs a human."}}, ["reason"]),
    transfer_to_human,
)


# --- Orders agent tools ----------------------------------------------------------


def list_my_orders(ctx: ToolContext) -> dict[str, Any]:
    if error := _require_customer(ctx):
        return error
    orders = ctx.db.query(
        "SELECT o.id, o.order_date, o.status, o.total, d.status AS delivery_status, "
        "GROUP_CONCAT(i.product, ', ') AS products "
        "FROM orders o JOIN deliveries d ON d.order_id = o.id JOIN order_items i ON i.order_id = o.id "
        "WHERE o.customer_id = ? GROUP BY o.id ORDER BY o.order_date DESC",
        (ctx.customer_id,),
    )
    return {"orders": orders, "count": len(orders)}


def get_order(ctx: ToolContext, order_id: str) -> dict[str, Any]:
    if error := _require_customer(ctx):
        return error
    order, error = _own_order(ctx, order_id)
    if error:
        return error
    items = ctx.db.query(
        "SELECT product, category, quantity, unit_price, returnable FROM order_items WHERE order_id = ?",
        (order["id"],),
    )
    delivery = ctx.db.query_one("SELECT * FROM deliveries WHERE order_id = ?", (order["id"],))
    delivery_info = _delivery_info(delivery)
    return {
        "order_id": order["id"],
        "order_date": order["order_date"],
        "status": order["status"],
        "total_gbp": order["total"],
        "payment": order["payment"],
        "items": [{**item, "returnable": bool(item["returnable"])} for item in items],
        "delivery": delivery_info,
        "return_check": _return_check(ctx, order, delivery_info, items),
    }


def track_delivery(ctx: ToolContext, order_id: str) -> dict[str, Any]:
    if error := _require_customer(ctx):
        return error
    order, error = _own_order(ctx, order_id)
    if error:
        return error
    delivery = ctx.db.query_one("SELECT * FROM deliveries WHERE order_id = ?", (order["id"],))
    return {"order_id": order["id"], **_delivery_info(delivery)}


LIST_MY_ORDERS = Tool(
    "list_my_orders",
    "List all orders of the verified customer, newest first, with their products and delivery "
    "status. Use it when the customer doesn't give an order number.",
    _params(),
    list_my_orders,
)

GET_ORDER = Tool(
    "get_order",
    "Get the full details of one of the customer's orders: items, total, payment, delivery, and "
    "a return_check that says whether the items can still be returned and why.",
    _params({"order_id": {"type": "string", "description": "Order number like SE-1042."}}, ["order_id"]),
    get_order,
)

TRACK_DELIVERY = Tool(
    "track_delivery",
    "Get the delivery status of one of the customer's orders: carrier, tracking number, where the "
    "parcel is, and the expected or actual delivery date.",
    _params({"order_id": {"type": "string", "description": "Order number like SE-1042."}}, ["order_id"]),
    track_delivery,
)


SUPERVISOR_TOOLS = [SEARCH_FAQ, GET_RETURN_POLICY, CREATE_TICKET, TRANSFER_TO_HUMAN]
ORDERS_TOOLS = [LIST_MY_ORDERS, GET_ORDER, TRACK_DELIVERY, GET_RETURN_POLICY]
