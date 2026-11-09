"""Shared LangGraph building blocks for the agents.

Every agent is a small graph:

    model --(asks for tools)--> tools --> model --(answers in words)--> END

``add_tool_agent`` adds those two nodes to a graph. The tool-call limit lives in
the graph state: after ``max_tool_calls`` the model node switches tools off, so
the model has to answer in words.

Two kinds of record are kept for every run:
- LangSmith (when ``LANGSMITH_TRACING=true``): LangChain sends it automatically.
- Our own trace file (``core/trace.py``): ``TraceHandler`` writes one ``llm_call``
  line per model call, and ``run_tool`` writes the ``tool_call`` lines. The
  scenario tests read this file.
"""
from __future__ import annotations

import json
import time
from typing import Annotated, Any, Callable, TypedDict
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from core.trace import Tracer

LIMIT_REACHED = {
    "error": "Tool call limit reached. Answer now with what you already know, "
    "or offer a ticket or a transfer to a colleague."
}


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    tool_calls_made: int  # reset to 0 at the start of each answer
    limit_hit: bool


ToolRunner = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


def add_tool_agent(
    graph: StateGraph,
    *,
    agent: str,
    model: BaseChatModel,
    tools: list[dict[str, Any]],
    run_tool: ToolRunner,
    system_prompt: Callable[[dict[str, Any]], str],
    max_tool_calls: int,
    tracer: Callable[[], Tracer | None] = lambda: None,
    response_format: Any = None,
) -> None:
    """Add the ``model`` and ``tools`` nodes, and the edges between them.

    ``run_tool(tool_call, state)`` runs one tool call and returns a dict.
    The caller connects ``START`` (or another node) to ``"model"``.
    """

    def call_model(state: dict[str, Any]) -> dict[str, Any]:
        tools_allowed = state.get("tool_calls_made", 0) < max_tool_calls
        bind_kwargs: dict[str, Any] = {"tool_choice": "auto" if tools_allowed else "none"}
        if response_format is not None:
            bind_kwargs["response_format"] = response_format
        bound = model.bind_tools(tools, **bind_kwargs)
        reply = bound.invoke([SystemMessage(system_prompt(state)), *state["messages"]])
        return {"messages": [reply]}

    def call_tools(state: dict[str, Any]) -> dict[str, Any]:
        made = state.get("tool_calls_made", 0)
        results = []
        for tool_call in state["messages"][-1].tool_calls:
            if made >= max_tool_calls:
                result = LIMIT_REACHED
            else:
                made += 1
                result = run_tool(tool_call, state)
            results.append(
                ToolMessage(
                    content=json.dumps(result, default=str),
                    tool_call_id=tool_call["id"],
                    name=tool_call["name"],
                )
            )

        update: dict[str, Any] = {"messages": results, "tool_calls_made": made}
        if made >= max_tool_calls and not state.get("limit_hit"):
            update["limit_hit"] = True
            active = tracer()
            if active:
                active.event(
                    "limit_hit",
                    agent,
                    input={"limit": "tool_calls", "max": max_tool_calls},
                    output="Tools switched off for the next model call.",
                )
        return update

    def after_model(state: dict[str, Any]) -> str:
        return "tools" if getattr(state["messages"][-1], "tool_calls", None) else END

    graph.add_node("model", call_model)
    graph.add_node("tools", call_tools)
    graph.add_conditional_edges("model", after_model, ["tools", END])
    graph.add_edge("tools", "model")


class TraceHandler(BaseCallbackHandler):
    """Writes one ``llm_call`` line to our trace file for each model call of ``agent``.

    LangChain passes callbacks down to nested runs, so a handler also sees the
    model calls of agents started inside a tool. The ``agent`` value in the
    run's metadata says whose call it is; calls of other agents are skipped.
    """

    def __init__(self, tracer: Tracer, agent: str, parent_id: str | None = None):
        self.tracer = tracer
        self.agent = agent
        self.parent_id = parent_id
        self._started: dict[UUID, dict[str, Any]] = {}

    def on_chat_model_start(self, serialized, messages, *, run_id: UUID, metadata=None, **kwargs: Any) -> None:
        if (metadata or {}).get("agent") != self.agent:
            return
        params = kwargs.get("invocation_params") or {}
        self._started[run_id] = {
            "time": time.perf_counter(),
            "model": params.get("model") or params.get("model_name") or (metadata or {}).get("ls_model_name"),
            "messages": len(messages[0]) if messages else 0,
            "tool_choice": params.get("tool_choice"),
        }

    def on_llm_end(self, response, *, run_id: UUID, **kwargs: Any) -> None:
        started = self._started.pop(run_id, None)
        if started is None:
            return
        message = response.generations[0][0].message
        self.tracer.event(
            "llm_call",
            self.agent,
            input={"messages": started["messages"], "tools_allowed": started["tool_choice"] != "none"},
            output={
                "text": message.text,
                "tool_calls": [{"name": c["name"], "arguments": c["args"]} for c in getattr(message, "tool_calls", [])],
            },
            model_or_tool=started["model"],
            duration_ms=(time.perf_counter() - started["time"]) * 1000,
            parent_id=self.parent_id,
            usage=getattr(message, "usage_metadata", None) or {},
        )

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        if self._started.pop(run_id, None) is not None:
            self.tracer.event("error", self.agent, output=f"{type(error).__name__}: {error}", parent_id=self.parent_id)
