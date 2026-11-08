"""The tool loop shared by every agent.

stream the model's reply -> if it asks for tools, run them -> add the results
-> stream again, until the model answers in words. After ``max_tool_calls`` the
model is called once more with tools switched off, so it has to answer.

The loop is a generator of spoken text, so the voice pipeline can start speaking
the first words while the rest is still being written.
"""
from __future__ import annotations

import json
import threading
from typing import Any, Callable, Iterator

from core.trace import Tracer
from services.llm import LLM, StreamEnd, TextDelta, ToolCall, ToolCalls

ToolRunner = Callable[[ToolCall], dict[str, Any]]

LIMIT_REACHED = {
    "error": "Tool call limit reached. Answer now with what you already know, "
    "or offer a ticket or a transfer to a colleague."
}


class ToolLoop:
    def __init__(
        self,
        llm: LLM,
        agent: str,
        tools: list[dict[str, Any]],
        run_tool: ToolRunner,
        tracer: Tracer | None = None,
        max_tool_calls: int = 5,
        slow_tool_seconds: float | None = None,
        slow_tool_filler: str = "Let me check that, it'll take a few seconds.",
        **llm_kwargs: Any,
    ):
        self.llm = llm
        self.agent = agent
        self.tools = tools
        self.run_tool = run_tool
        self.tracer = tracer
        self.max_tool_calls = max_tool_calls
        self.slow_tool_seconds = slow_tool_seconds
        self.slow_tool_filler = slow_tool_filler
        self.llm_kwargs = llm_kwargs
        self.tool_calls_made = 0
        self.final_text = ""
        self.limit_hit = False

    def run(self, messages: list[dict[str, Any]]) -> Iterator[str]:
        """Yield the reply text. ``messages`` gets the new assistant and tool messages."""
        while True:
            tools_allowed = self.tool_calls_made < self.max_tool_calls
            text, calls = yield from self._one_model_call(messages, tools_allowed)

            assistant: dict[str, Any] = {"role": "assistant", "content": text or None}
            if calls:
                assistant["tool_calls"] = [call.as_message() for call in calls]
            messages.append(assistant)

            if not calls:
                self.final_text = text
                return

            for call in calls:
                if self.tool_calls_made >= self.max_tool_calls:
                    result = LIMIT_REACHED
                else:
                    self.tool_calls_made += 1
                    result = yield from self._run_tool(call)
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, default=str)}
                )

            if self.tool_calls_made >= self.max_tool_calls and not self.limit_hit:
                self.limit_hit = True
                if self.tracer:
                    self.tracer.event(
                        "limit_hit",
                        self.agent,
                        input={"limit": "tool_calls", "max": self.max_tool_calls},
                        output="Tools switched off for the next model call.",
                    )

    def _one_model_call(self, messages: list[dict[str, Any]], tools_allowed: bool):
        kwargs = dict(self.llm_kwargs)
        if self.tools:
            # Keep the tools defined (the history may contain tool calls) but
            # forbid new ones once the limit is reached.
            kwargs["tool_choice"] = "auto" if tools_allowed else "none"
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        end = StreamEnd()

        def stream():
            nonlocal calls, end
            for event in self.llm.stream_chat(messages, tools=self.tools or None, **kwargs):
                if isinstance(event, TextDelta):
                    text_parts.append(event.text)
                    yield event.text
                elif isinstance(event, ToolCalls):
                    calls = event.calls
                elif isinstance(event, StreamEnd):
                    end = event

        if not self.tracer:
            yield from stream()
            return "".join(text_parts), calls

        with self.tracer.span(
            "llm_call",
            self.agent,
            input={"messages": len(messages), "last": _short(messages[-1]), "tools_allowed": tools_allowed},
            model_or_tool=self.llm.model,
        ) as span:
            try:
                yield from stream()
            except GeneratorExit:
                span.extra["interrupted"] = True
                raise
            finally:
                span.output = {
                    "text": "".join(text_parts),
                    "tool_calls": [{"name": c.name, "arguments": c.arguments} for c in calls],
                }
                span.extra["finish_reason"] = end.finish_reason
                span.extra["usage"] = end.usage
        return "".join(text_parts), calls

    def _run_tool(self, call: ToolCall):
        """Run one tool. If it is slow, speak a short filler while waiting."""
        if not self.slow_tool_seconds:
            return self.run_tool(call)

        box: dict[str, Any] = {}
        parent_id = self.tracer.current_parent() if self.tracer else None

        def work():
            try:
                if self.tracer:
                    # Keep the trace tree intact across the helper thread.
                    with self.tracer.parent(parent_id):
                        box["result"] = self.run_tool(call)
                else:
                    box["result"] = self.run_tool(call)
            except Exception as exc:
                box["result"] = {"error": f"The {call.name} tool failed: {type(exc).__name__}."}

        worker = threading.Thread(target=work, name=f"tool-{call.name}", daemon=True)
        worker.start()
        worker.join(self.slow_tool_seconds)
        if worker.is_alive():
            if self.tracer:
                self.tracer.event("filler", self.agent, output=self.slow_tool_filler, model_or_tool="code")
            yield " " + self.slow_tool_filler + " "
            worker.join()
        return box["result"]


def _short(message: dict[str, Any]) -> str:
    content = message.get("content")
    text = content if isinstance(content, str) else json.dumps(content, default=str)
    return text if len(text) <= 200 else text[:200] + "…"
