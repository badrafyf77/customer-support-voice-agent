"""The orders agent: a specialist that answers order questions for the supervisor.

It never talks to the customer. ``run_job`` takes the supervisor's request, uses
its own tools (with at most ``max_tool_calls`` calls), and always returns one of
three answers: ``done``, ``needs_info`` or ``cannot``.
"""
from __future__ import annotations

import json
from contextlib import nullcontext
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from agents.tool_loop import ToolLoop
from core.config import load_agent_config
from services.llm import LLM, ToolCall
from shop.tools import ORDERS_TOOLS, ToolContext, run_tool, spoken_date

PROMPT_PATH = Path(__file__).with_name("prompt.md")
STATUSES = ("done", "needs_info", "cannot")

# Structured output: the model must answer in exactly this JSON shape.
RESULT_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "orders_result",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": list(STATUSES)},
                "message": {"type": "string"},
                "order_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["status", "message", "order_ids"],
            "additionalProperties": False,
        },
    },
}


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


def build_orders_llm(config: dict[str, Any] | None = None) -> LLM:
    config = config or load_agent_config("orders")
    return LLM(
        backend=config.get("llm_provider") or "openai",
        model=config.get("llm_model") or "gpt-5.5",
        reasoning_effort=config.get("reasoning_effort") or None,
    )


class OrdersAgent:
    def __init__(self, llm: LLM, ctx: ToolContext, max_tool_calls: int = 5):
        self.llm = llm
        self.ctx = ctx
        self.max_tool_calls = max_tool_calls
        self.tools = {tool.name: tool for tool in ORDERS_TOOLS}

    def system_prompt(self) -> str:
        today = self.ctx.today.isoformat()
        return PROMPT_PATH.read_text(encoding="utf-8").replace("{today}", f"{spoken_date(today)} ({today})")

    def _run_tool(self, call: ToolCall) -> dict[str, Any]:
        tool = self.tools.get(call.name)
        if tool is None:
            return {"error": f"There is no tool called {call.name}."}
        return run_tool(tool, self.ctx, call.arguments, agent="orders")

    def run_job(self, request: str, parent_id: str | None = None) -> OrdersResult:
        """Answer one request from the supervisor. Safe to run in a background thread."""
        tracer = self.ctx.tracer
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt()},
            {"role": "user", "content": request},
        ]
        loop = ToolLoop(
            self.llm,
            "orders",
            [tool.schema() for tool in ORDERS_TOOLS],
            self._run_tool,
            tracer=tracer,
            max_tool_calls=self.max_tool_calls,
            response_format=RESULT_FORMAT,
        )

        with tracer.parent(parent_id) if tracer else nullcontext():
            try:
                text = "".join(loop.run(messages))
            except Exception as exc:
                if tracer:
                    tracer.event("error", "orders", input=request, output=f"{type(exc).__name__}: {exc}")
                text = ""
            result = parse_result(text, loop.tool_calls_made)
            if tracer:
                tracer.event("agent_result", "orders", input=request, output=result.as_dict(), model_or_tool=self.llm.model)
        return result
