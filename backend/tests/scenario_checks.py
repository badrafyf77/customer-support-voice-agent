"""Check one scenario turn against what really happened (its trace lines).

A scenario turn can expect:

- ``expect_calls``: tools and agent calls, in this order. Harmless extra calls in
  between are allowed. ``supervisor: name`` or ``orders: name``; the name can be
  a list meaning "any of these". ``args`` must match the tool's arguments (the
  expected text must appear in the real value, ignoring case).
- ``must_not_call``: tool or agent call names that must not appear at all.
- ``orders_result``: the status the orders agent returned (the last one in the turn).
- ``answer_contains``: text the customer must hear. An item that is a list means
  "any one of these". ``{day+2}`` becomes the weekday two days from today and
  ``{date+2}`` becomes "10 November" for that day.
- ``expect_finished``: whether the call ended in this turn (after a transfer).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

PLACEHOLDER = re.compile(r"\{(day|date)([+-]\d+)\}")


def fill_dates(text: str, today: date) -> str:
    def replace(match: re.Match) -> str:
        value = today + timedelta(days=int(match.group(2)))
        return value.strftime("%A") if match.group(1) == "day" else f"{value.day} {value.strftime('%B')}"

    return PLACEHOLDER.sub(replace, text)


def calls_in(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The tool and agent calls of a turn, in the order they started."""
    calls = []
    for event in events:
        if event["kind"] == "agent_call":
            calls.append({"agent": event["agent"], "name": event["model_or_tool"], "args": {"request": event["input"]}, "ts": event["ts"]})
        elif event["kind"] == "tool_call" and event["agent"] in {"supervisor", "orders"}:
            # Spans are written when they end, so sort by start time = end - duration.
            calls.append({"agent": event["agent"], "name": event["model_or_tool"], "args": event["input"] or {}, "ts": event["ts"], "duration_ms": event.get("duration_ms") or 0})
    return sorted(calls, key=_start_time)


def _start_time(call: dict[str, Any]) -> float:
    return datetime.fromisoformat(call["ts"]).timestamp() - call.get("duration_ms", 0) / 1000


def _matches(expected: dict[str, Any], call: dict[str, Any]) -> bool:
    agent = "supervisor" if "supervisor" in expected else "orders"
    names = expected[agent]
    names = names if isinstance(names, list) else [names]
    if call["agent"] != agent or call["name"] not in names:
        return False
    for key, value in (expected.get("args") or {}).items():
        if str(value).lower() not in str(call["args"].get(key, "")).lower():
            return False
    return True


def _plain(text: str) -> str:
    """Lower case, with curly quotes made straight ("can’t" == "can't")."""
    return text.lower().replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')


def check_turn(turn: dict[str, Any], run, today: date) -> list[str]:
    """Return a list of problems (empty when the turn passed)."""
    problems: list[str] = []
    calls = calls_in(run.events)
    names = [call["name"] for call in calls]

    position = 0
    for expected in turn.get("expect_calls") or []:
        while position < len(calls) and not _matches(expected, calls[position]):
            position += 1
        if position == len(calls):
            problems.append(f"expected call {expected} not found in order; calls were {names}")
            break
        position += 1

    for name in turn.get("must_not_call") or []:
        if name in names:
            problems.append(f"{name} must not be called; calls were {names}")

    if "orders_result" in turn:
        results = [event for event in run.events if event["kind"] == "agent_result" and event["agent"] == "orders"]
        status = results[-1]["output"]["status"] if results else None
        if status != turn["orders_result"]:
            problems.append(f"orders_result should be {turn['orders_result']}, got {status}")

    heard = _plain(run.all_spoken)
    for item in turn.get("answer_contains") or []:
        options = item if isinstance(item, list) else [item]
        options = [fill_dates(str(option), today) for option in options]
        if not any(_plain(option) in heard for option in options):
            problems.append(f"answer should contain {' or '.join(repr(o) for o in options)}; heard {run.all_spoken!r}")

    if "expect_finished" in turn and bool(turn["expect_finished"]) != run.finished:
        problems.append(f"expect_finished={turn['expect_finished']} but the call finished={run.finished}")

    return problems
