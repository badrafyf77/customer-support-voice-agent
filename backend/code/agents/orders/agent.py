"""The orders agent: a specialist that answers order questions for the supervisor.

It never talks to the customer. It is a LangGraph graph (``model`` <-> ``tools``)
with its own tools and at most ``max_tool_calls`` tool calls. ``run_job`` always
returns one of three answers: ``done``, ``needs_info`` or ``cannot``.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.graph import START, StateGraph
from pydantic import BaseModel, Field

from agents.graph import AgentState, TraceHandler, add_tool_agent
from agents.models import build_chat_model
from core.config import load_agent_config
from core.trace import Tracer
from shop.db import ShopDB
from shop.tools import ORDERS_TOOLS, ToolContext, run_tool, spoken_date

PROMPT_PATH = Path(__file__).with_name("prompt.md")
STATUSES = ("done", "needs_info", "cannot")


class OrdersAnswer(BaseModel):
    """Structured output: the model must answer in exactly this JSON shape."""

    status: Literal["done", "needs_info", "cannot"]
    message: str = Field(description="What the supervisor should know, in one to three plain sentences.")
    order_ids: list[str] = Field(description="The order numbers this answer is about.")


class OrdersState(AgentState, total=False):
    customer_id: str  # the verified customer, set by code, never by the AI
    trace_parent: str  # the supervisor's agent_call line in our trace file


@dataclass
class OrdersResult:
    status: str
    message: str
    order_ids: list[str] = field(default_factory=list)
    tool_calls: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_result(text: str, tool_calls: int) -> OrdersResult:
    try:
        data = json.loads(text)
        if data.get("status") not in STATUSES or not isinstance(data.get("message"), str):
            raise ValueError("wrong shape")
        order_ids = [str(order_id) for order_id in data.get("order_ids") or []]
        return OrdersResult(data["status"], data["message"].strip(), order_ids, tool_calls)
    except (ValueError, TypeError, AttributeError):
        return OrdersResult("cannot", "The orders agent gave an answer that could not be read.", [], tool_calls)


def build_orders_model(config: dict[str, Any] | None = None) -> BaseChatModel:
    return build_chat_model(config if config is not None else load_agent_config("orders"), "gpt-5.4-mini")


class OrdersAgent:
    def __init__(
        self,
        model: BaseChatModel,
        db: ShopDB,
        tracer: Tracer | None = None,
        max_tool_calls: int = 5,
        today: date | None = None,
        session_id: str = "no-session",
    ):
        self.model = model
        self.db = db
        self.tracer = tracer
        self.max_tool_calls = max_tool_calls
        self.today = today or date.today()
        self.session_id = session_id
        self.tools = {tool.name: tool for tool in ORDERS_TOOLS}
        self.graph = self.build_graph().compile(name="orders_agent")

    def system_prompt(self, state: dict[str, Any] | None = None) -> str:
        today = self.today.isoformat()
        return PROMPT_PATH.read_text(encoding="utf-8").replace("{today}", f"{spoken_date(today)} ({today})")

    def build_graph(self) -> StateGraph:
        graph = StateGraph(OrdersState)
        add_tool_agent(
            graph,
            agent="orders",
            model=self.model,
            tools=[tool.schema() for tool in ORDERS_TOOLS],
            run_tool=self._run_tool,
            system_prompt=self.system_prompt,
            max_tool_calls=self.max_tool_calls,
            tracer=lambda: self.tracer,
            response_format=OrdersAnswer,
        )
        graph.add_edge(START, "model")
        return graph

    def _run_tool(self, tool_call: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        tool = self.tools.get(tool_call["name"])
        if tool is None:
            return {"error": f"There is no tool called {tool_call['name']}."}
        ctx = ToolContext(
            db=self.db,
            session_id=self.session_id,
            customer_id=state.get("customer_id"),
            tracer=self.tracer,
            today=self.today,
            trace_parent=state.get("trace_parent"),
        )
        return run_tool(tool, ctx, tool_call["args"], agent="orders")

    def run_job(self, request: str, customer_id: str | None, parent_id: str | None = None) -> OrdersResult:
        """Answer one request from the supervisor. Safe to run in a background thread."""
        config: dict[str, Any] = {
            "run_name": "orders_agent",
            "metadata": {"agent": "orders", "session_id": self.session_id, "customer_id": customer_id},
            "recursion_limit": 2 * self.max_tool_calls + 5,
        }
        if self.tracer:
            config["callbacks"] = [TraceHandler(self.tracer, "orders", parent_id)]

        tool_calls = 0
        try:
            final = self.graph.invoke(
                {
                    "messages": [HumanMessage(request)],
                    "customer_id": customer_id,
                    "trace_parent": parent_id,
                    "tool_calls_made": 0,
                },
                config,
            )
            tool_calls = final.get("tool_calls_made", 0)
            text = final["messages"][-1].text
        except Exception as exc:
            if self.tracer:
                self.tracer.event("error", "orders", input=request, output=f"{type(exc).__name__}: {exc}", parent_id=parent_id)
            text = ""

        result = parse_result(text, tool_calls)
        if self.tracer:
            self.tracer.event(
                "agent_result",
                "orders",
                input=request,
                output=result.as_dict(),
                model_or_tool=getattr(self.model, "model_name", None),
                parent_id=parent_id,
            )
        return result
