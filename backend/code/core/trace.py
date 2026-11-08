"""Per-call trace: one JSON line for every step of a call.

Each call gets one file, ``logs/traces/<session_id>.jsonl``. Every line has the
same fields, so a reader (tests, or the Phase 5 "agent brain" screen) can rebuild
the tree of what happened using ``event_id`` and ``parent_id``.

A span (``with tracer.span(...)``) is written when it ends, so it can record its
duration and output. Lines that happen inside it are written first and point to
it with ``parent_id``.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from core.config import CODE_ROOT, get_env

TRACE_KINDS = {
    "call_start",
    "user_said",
    "identity_step",
    "llm_call",
    "tool_call",
    "agent_call",
    "agent_result",
    "filler",
    "limit_hit",
    "spoken",
    "error",
    "call_end",
}


def default_trace_dir() -> Path:
    configured = get_env("TRACE_DIR")
    return Path(configured) if configured else CODE_ROOT.parent / "logs" / "traces"


class Span:
    """A step that is still running. Set ``output`` and ``extra`` before it ends."""

    def __init__(self, event_id: str, parent_id: str | None):
        self.event_id = event_id
        self.parent_id = parent_id
        self.output: Any = None
        self.extra: dict[str, Any] = {}


class Tracer:
    """Writes the trace file of one call. Safe to use from several threads."""

    def __init__(self, session_id: str, directory: Path | str | None = None):
        self.session_id = session_id
        self.directory = Path(directory) if directory is not None else default_trace_dir()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / f"{session_id}.jsonl"
        self.turn_id = 0
        self._write_lock = threading.Lock()
        self._local = threading.local()

    def new_turn(self) -> int:
        self.turn_id += 1
        return self.turn_id

    def _stack(self) -> list[str]:
        if not hasattr(self._local, "stack"):
            self._local.stack = []
        return self._local.stack

    def current_parent(self) -> str | None:
        stack = self._stack()
        return stack[-1] if stack else None

    def _write(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, default=str, ensure_ascii=False)
        with self._write_lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def _record(
        self,
        event_id: str,
        kind: str,
        agent: str,
        parent_id: str | None,
        turn_id: int | None,
        input: Any,
        output: Any,
        model_or_tool: str | None,
        duration_ms: float | None,
        extra: dict[str, Any],
    ) -> None:
        if kind not in TRACE_KINDS:
            raise ValueError(f"Unknown trace kind '{kind}'")
        self._write(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "session_id": self.session_id,
                "turn_id": self.turn_id if turn_id is None else turn_id,
                "event_id": event_id,
                "parent_id": parent_id,
                "agent": agent,
                "kind": kind,
                "input": input,
                "output": output,
                "model_or_tool": model_or_tool,
                "duration_ms": None if duration_ms is None else round(duration_ms, 1),
                **extra,
            }
        )

    def event(
        self,
        kind: str,
        agent: str,
        input: Any = None,
        output: Any = None,
        model_or_tool: str | None = None,
        duration_ms: float | None = None,
        parent_id: str | None = None,
        turn_id: int | None = None,
        **extra: Any,
    ) -> str:
        """Write one line now and return its ``event_id``."""
        event_id = uuid.uuid4().hex[:12]
        self._record(
            event_id,
            kind,
            agent,
            parent_id if parent_id is not None else self.current_parent(),
            turn_id,
            input,
            output,
            model_or_tool,
            duration_ms,
            extra,
        )
        return event_id

    @contextmanager
    def span(
        self,
        kind: str,
        agent: str,
        input: Any = None,
        model_or_tool: str | None = None,
        parent_id: str | None = None,
        turn_id: int | None = None,
        **extra: Any,
    ) -> Iterator[Span]:
        """Time a step. Lines written inside it get it as their parent.

        Pass ``parent_id`` when the step runs in another thread than its parent.
        """
        span = Span(uuid.uuid4().hex[:12], parent_id if parent_id is not None else self.current_parent())
        span.extra.update(extra)
        stack = self._stack()
        stack.append(span.event_id)
        started = time.perf_counter()
        try:
            yield span
        except Exception as exc:
            span.extra["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            stack.pop()
            self._record(
                span.event_id,
                kind,
                agent,
                span.parent_id,
                turn_id,
                input,
                span.output,
                model_or_tool,
                (time.perf_counter() - started) * 1000,
                span.extra,
            )

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
