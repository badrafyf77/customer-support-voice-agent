"""Fake model used by the unit tests, so they need no network and cost nothing."""
from __future__ import annotations

import copy
import json
from typing import Any

from services.llm import StreamEnd, TextDelta, ToolCall, ToolCalls


def say(*pieces: str) -> dict[str, Any]:
    """A scripted reply made of text pieces."""
    return {"text": list(pieces), "calls": []}


def call(name: str, call_id: str | None = None, text: str = "", **arguments: Any) -> dict[str, Any]:
    """A scripted reply that asks for one tool (optionally after some text)."""
    return calls((name, call_id, arguments), text=text)


def calls(*specs: tuple[str, str | None, dict[str, Any]], text: str = "") -> dict[str, Any]:
    tool_calls = [
        ToolCall(call_id or f"call_{name}_{i}", name, json.dumps(arguments))
        for i, (name, call_id, arguments) in enumerate(specs)
    ]
    return {"text": [text] if text else [], "calls": tool_calls}


class FakeLLM:
    """Plays back scripted replies and remembers every request it got."""

    def __init__(self, replies: list[dict[str, Any]] | None = None, model: str = "fake-model"):
        self.model = model
        self.replies = list(replies or [])
        self.requests: list[dict[str, Any]] = []

    def add(self, *replies: dict[str, Any]) -> None:
        self.replies.extend(replies)

    def stream_chat(self, messages, tools=None, **kwargs):
        self.requests.append({"messages": copy.deepcopy(messages), "tools": tools, **kwargs})
        if not self.replies:
            raise AssertionError("FakeLLM ran out of scripted replies")
        reply = self.replies.pop(0)
        if callable(reply):
            reply = reply(messages)
        for piece in reply["text"]:
            yield TextDelta(piece)
        if reply["calls"]:
            yield ToolCalls(reply["calls"])
        yield StreamEnd(finish_reason="tool_calls" if reply["calls"] else "stop", usage={"total_tokens": 10})
