"""The supervisor: the only agent that talks to the customer.

It knows nothing about audio. It takes the customer's text and gives back the
text to speak, as a generator. The voice pipeline and the text test runner both
use it.

A call goes:
1. Identity steps in plain code (``identity.py``). The AI does nothing before.
2. Then the AI answers with its tools. Calls to the orders agent run in a
   background thread. The result waits in a queue until the runtime asks for
   it with ``respond_to_background()``, which it does when nobody is speaking.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterator

from agents.orders.agent import OrdersAgent, OrdersResult
from agents.support.identity import FAILED, VERIFIED, IdentityCheck
from agents.tool_loop import ToolLoop
from core.trace import Tracer
from services.llm import LLM, ToolCall
from shop.db import ShopDB
from shop.tools import (
    LOOKUP_CUSTOMER,
    SUPERVISOR_TOOLS,
    TRANSFER_TO_HUMAN,
    ToolContext,
    run_tool,
    spoken_date,
)

PROMPT_PATH = Path(__file__).with_name("prompt.md")

ASK_ORDERS_AGENT = {
    "type": "function",
    "function": {
        "name": "ask_orders_agent",
        "description": (
            "Send a question about the customer's orders, deliveries or returns to the Orders "
            "specialist. It runs in the background: this returns 'started' at once, and the "
            "answer arrives later as a system message. Include every detail the customer gave."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "request": {
                    "type": "string",
                    "description": "The full question, e.g. 'Where is order SE-1042 and when will it arrive?'",
                }
            },
            "required": ["request"],
            "additionalProperties": False,
        },
    },
}

SLOW_JOB_TEXT = (
    "Sorry, this is taking a bit longer than usual. I can keep waiting, "
    "or open a ticket so our team follows up by email."
)
CALL_LIMIT_WARNING_TEXT = (
    "Just so you know, we're almost at the time limit for this call. If anything is "
    "left, I can open a support ticket so our team follows up by email."
)
CALL_LIMIT_END_TEXT = "We've reached the time limit for this call. Thank you for calling ShopEasy, goodbye."


@dataclass
class SupervisorSettings:
    max_tool_calls: int = 5
    orders_max_tool_calls: int = 5
    slow_tool_seconds: float = 1.0
    job_timeout_seconds: float = 20.0
    call_warning_seconds: float = 14 * 60
    call_limit_seconds: float = 15 * 60


@dataclass
class OrdersJob:
    job_id: int
    request: str
    call_event_id: str | None
    thread: threading.Thread | None = None
    done: bool = False


class Supervisor:
    def __init__(
        self,
        llm: LLM,
        orders_llm: LLM,
        db: ShopDB,
        tracer: Tracer,
        session_id: str,
        settings: SupervisorSettings | None = None,
        on_background_ready: Callable[[], None] | None = None,
        today: date | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.llm = llm
        self.tracer = tracer
        self.settings = settings or SupervisorSettings()
        self.on_background_ready = on_background_ready
        self.clock = clock
        self.started_at = clock()
        self.call_warning_given = False

        self.ctx = ToolContext(db=db, session_id=session_id, tracer=tracer, today=today or date.today())
        self.orders_agent = OrdersAgent(orders_llm, self.ctx, self.settings.orders_max_tool_calls)
        self.identity = IdentityCheck(self._lookup_customer, tracer)
        self.tools = {tool.name: tool for tool in SUPERVISOR_TOOLS}
        self.tool_schemas = [tool.schema() for tool in SUPERVISOR_TOOLS] + [ASK_ORDERS_AGENT]
        self.messages: list[dict[str, Any]] = []

        self.finished = False
        self.finish_reason: str | None = None
        self.closed = False
        self.job: OrdersJob | None = None
        self.job_count = 0
        self.background: queue.Queue[dict[str, Any]] = queue.Queue()

    # --- What the runtime calls ---------------------------------------------------

    def greeting(self) -> Iterator[str]:
        text = self.identity.greeting()
        self._spoken(text)
        yield text

    def respond(self, text: str) -> Iterator[str]:
        """Answer one finished customer turn."""
        self.tracer.new_turn()
        self.tracer.event("user_said", "code", input=text)
        if self.finished:
            return

        if not self.identity.done:
            yield from self._identity_turn(text)
            return

        self.messages.append({"role": "user", "content": text})
        yield from self._ai_turn()

    def has_background_results(self) -> bool:
        return not self.background.empty()

    def respond_to_background(self) -> Iterator[str]:
        """Speak the background results that arrived while the customer was busy."""
        items = []
        while not self.background.empty():
            items.append(self.background.get_nowait())
        if not items or self.finished:
            return
        self.tracer.new_turn()

        fixed_texts = [item["text"] for item in items if item["kind"] == "fixed"]
        results = [item for item in items if item["kind"] == "orders_result"]
        for text in fixed_texts:
            self.messages.append({"role": "assistant", "content": text})
            self._spoken(text)
            yield text + " "
        if results:
            for item in results:
                self.messages.append({"role": "system", "content": item["message"]})
            yield from self._ai_turn()

    def call_time_check(self) -> Iterator[str]:
        """Speak the call-limit warning or the goodbye when it is time. Empty otherwise."""
        elapsed = self.clock() - self.started_at
        if self.finished:
            return
        if elapsed >= self.settings.call_limit_seconds:
            self.tracer.event("limit_hit", "code", input={"limit": "call_seconds", "max": self.settings.call_limit_seconds})
            self._finish("call_time_limit")
            self._spoken(CALL_LIMIT_END_TEXT)
            yield CALL_LIMIT_END_TEXT
        elif elapsed >= self.settings.call_warning_seconds and not self.call_warning_given:
            self.call_warning_given = True
            self.tracer.event("limit_hit", "code", input={"limit": "call_warning_seconds", "max": self.settings.call_warning_seconds})
            self.messages.append({"role": "assistant", "content": CALL_LIMIT_WARNING_TEXT})
            self._spoken(CALL_LIMIT_WARNING_TEXT)
            yield CALL_LIMIT_WARNING_TEXT

    def close(self) -> None:
        """The customer hung up: forget any running job."""
        self.closed = True
        if self.job and not self.job.done:
            self.tracer.event("agent_result", "code", input=self.job.request, output="cancelled: the call ended")

    # --- Identity -----------------------------------------------------------------

    def _lookup_customer(self, phone: str) -> dict[str, Any]:
        return run_tool(LOOKUP_CUSTOMER, self.ctx, {"phone": phone}, agent="code")

    def _identity_turn(self, text: str) -> Iterator[str]:
        reply = self.identity.handle(text)

        if reply.stage == VERIFIED:
            customer = reply.customer or {}
            self.ctx.customer_id = customer["customer_id"]
            self.messages = [{"role": "system", "content": self._system_prompt(customer)}]
            early = self.identity.early_requests
            if early:
                # They told us their problem before giving their number: answer it now.
                self.messages.append({"role": "user", "content": " ".join(early)})
                self._spoken(reply.say)
                yield reply.say + " "
                yield from self._ai_turn()
                return
            text_out = f"{reply.say} How can I help you today?"
            self.messages.append({"role": "assistant", "content": text_out})
            self._spoken(text_out)
            yield text_out
            return

        self._spoken(reply.say)
        yield reply.say
        if reply.stage == FAILED:
            run_tool(TRANSFER_TO_HUMAN, self.ctx, {"reason": "Identity could not be confirmed."}, agent="code")
            self._finish("identity_failed")

    def _system_prompt(self, customer: dict[str, Any]) -> str:
        today = self.ctx.today.isoformat()
        return (
            PROMPT_PATH.read_text(encoding="utf-8")
            .replace("{today}", f"{spoken_date(today)} ({today})")
            .replace("{customer_name}", f"{customer['first_name']} {customer['last_name']}")
        )

    # --- AI turns -----------------------------------------------------------------

    def _ai_turn(self) -> Iterator[str]:
        loop = ToolLoop(
            self.llm,
            "supervisor",
            self.tool_schemas,
            self._run_tool,
            tracer=self.tracer,
            max_tool_calls=self.settings.max_tool_calls,
            slow_tool_seconds=self.settings.slow_tool_seconds,
        )
        spoken: list[str] = []
        interrupted = False
        try:
            for piece in loop.run(self.messages):
                spoken.append(piece)
                yield piece
        except GeneratorExit:
            interrupted = True
            if loop.pending_text:
                self.messages.append({"role": "assistant", "content": loop.pending_text + " [interrupted by the customer]"})
            raise
        except Exception as exc:
            self.tracer.event("error", "supervisor", output=f"{type(exc).__name__}: {exc}")
            sorry = "Sorry, I'm having a technical problem. Could you say that again, please?"
            spoken.append(sorry)
            yield sorry
        finally:
            self._spoken("".join(spoken), interrupted=interrupted)

    def _run_tool(self, call: ToolCall) -> dict[str, Any]:
        if call.name == "ask_orders_agent":
            try:
                args = json.loads(call.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            return self._start_orders_job(str(args.get("request") or "").strip())

        tool = self.tools.get(call.name)
        if tool is None:
            return {"error": f"There is no tool called {call.name}."}
        result = run_tool(tool, self.ctx, call.arguments, agent="supervisor")
        if call.name == "transfer_to_human" and "error" not in result:
            self._finish("transferred_to_human")
        return result

    # --- Background orders jobs ---------------------------------------------------

    def _start_orders_job(self, request: str) -> dict[str, Any]:
        if not request:
            return {"error": "Missing argument: request."}
        if self.job and not self.job.done:
            return {
                "status": "busy",
                "message": "An orders request is already running. Wait for its answer before asking another.",
            }

        self.job_count += 1
        call_event_id = self.tracer.event(
            "agent_call",
            "supervisor",
            input=request,
            output={"status": "started", "job_id": self.job_count},
            model_or_tool="ask_orders_agent",
        )
        job = OrdersJob(self.job_count, request, call_event_id)
        job.thread = threading.Thread(target=self._run_orders_job, args=(job,), name=f"orders-job-{job.job_id}", daemon=True)
        self.job = job
        job.thread.start()
        if self.settings.job_timeout_seconds:
            timer = threading.Timer(self.settings.job_timeout_seconds, self._job_is_slow, args=(job,))
            timer.daemon = True
            timer.start()
        return {
            "status": "started",
            "job_id": job.job_id,
            "note": "The Orders specialist is working on it. Tell the customer you're checking. "
            "The answer will come back to you automatically.",
        }

    def _run_orders_job(self, job: OrdersJob) -> None:
        result: OrdersResult = self.orders_agent.run_job(job.request, parent_id=job.call_event_id)
        job.done = True
        if self.closed:
            return
        self.background.put(
            {
                "kind": "orders_result",
                "message": (
                    f"Orders specialist answer for job {job.job_id} (your request: \"{job.request}\"): "
                    f"{json.dumps({'status': result.status, 'message': result.message, 'order_ids': result.order_ids})} "
                    "Tell the customer now."
                ),
            }
        )
        self._notify()

    def _job_is_slow(self, job: OrdersJob) -> None:
        if job.done or self.closed or self.finished:
            return
        self.tracer.event("limit_hit", "code", input={"limit": "orders_job_seconds", "max": self.settings.job_timeout_seconds, "job_id": job.job_id})
        self.background.put({"kind": "fixed", "text": SLOW_JOB_TEXT})
        self._notify()

    def wait_for_jobs(self, timeout: float = 60.0) -> None:
        """Block until the running orders job is done (used by the text runner)."""
        if self.job and self.job.thread:
            self.job.thread.join(timeout)

    def _notify(self) -> None:
        if self.on_background_ready:
            try:
                self.on_background_ready()
            except Exception:
                pass

    # --- Helpers ------------------------------------------------------------------

    def _finish(self, reason: str) -> None:
        self.finished = True
        self.finish_reason = reason

    def _spoken(self, text: str, interrupted: bool = False) -> None:
        if text or interrupted:
            self.tracer.event("spoken", "supervisor", output=text, interrupted=interrupted)


def build_supervisor(
    session_id: str,
    config: dict[str, Any],
    orders_config: dict[str, Any],
    db: ShopDB | None = None,
    tracer: Tracer | None = None,
    on_background_ready: Callable[[], None] | None = None,
    today: date | None = None,
) -> Supervisor:
    from agents.orders.agent import build_orders_llm
    from shop.db import open_shop_db

    llm = LLM(
        backend=config.get("llm_provider") or "openai",
        model=config.get("llm_model") or "gpt-5.4-mini",
        reasoning_effort=config.get("reasoning_effort") or None,
    )
    settings = SupervisorSettings(
        max_tool_calls=int(config.get("max_tool_calls") or 5),
        orders_max_tool_calls=int(orders_config.get("max_tool_calls") or 5),
        call_warning_seconds=float(config.get("call_warning_seconds") or 14 * 60),
        call_limit_seconds=float(config.get("call_limit_seconds") or 15 * 60),
    )
    return Supervisor(
        llm,
        build_orders_llm(orders_config),
        db or open_shop_db(),
        tracer or Tracer(session_id),
        session_id,
        settings,
        on_background_ready,
        today,
    )
