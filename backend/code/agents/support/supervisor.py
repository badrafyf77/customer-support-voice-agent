"""The supervisor: the only agent that talks to the customer.

It is a LangGraph graph:

    START -> identity --(not verified yet)--> END
                     \\--(verified)--> model <-> tools --> END

- ``identity`` is plain code (``identity.py``): steps 1 and 2 of the call. The AI
  can't skip it, because the graph only reaches ``model`` once it passes.
- ``model`` / ``tools`` is the AI with its tools (``agents/graph.py``).
- ``ask_orders_agent`` starts the orders agent (its own graph) in a background
  thread. The result waits in a queue until the runtime calls
  ``respond_to_background()``, which it does when nobody is speaking.

The class knows nothing about audio. ``respond()`` yields the text to speak, and
both the voice pipeline and the text test runner use it. The conversation is kept
by LangGraph's checkpointer, one thread per call.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterator

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langsmith.run_helpers import get_current_run_tree, tracing_context

from agents.graph import AgentState, TraceHandler, add_tool_agent
from agents.orders.agent import OrdersAgent, OrdersResult
from agents.support.identity import FAILED, VERIFIED, IdentityCheck
from core.trace import Tracer
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
INTERRUPTED_MARK = " [interrupted by the customer]"


class SupportState(AgentState, total=False):
    identity: dict[str, Any]  # IdentityCheck state (plain data)
    customer: dict[str, Any] | None  # set by code once the identity is verified
    next_step: str  # where the identity node sends the call: "model" or "end"


@dataclass
class SupervisorSettings:
    max_tool_calls: int = 5
    orders_max_tool_calls: int = 5
    job_timeout_seconds: float = 20.0
    call_warning_seconds: float = 14 * 60
    call_limit_seconds: float = 15 * 60
    # False runs the orders agent inside the tool call (used by LangGraph Studio,
    # so you can watch the whole run in one place).
    orders_in_background: bool = True


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
        model: BaseChatModel,
        orders_model: BaseChatModel,
        db: ShopDB,
        tracer: Tracer,
        session_id: str,
        settings: SupervisorSettings | None = None,
        on_background_ready: Callable[[], None] | None = None,
        today: date | None = None,
        clock: Callable[[], float] = time.monotonic,
        checkpointer: Any = "memory",
    ):
        self.model = model
        self.db = db
        self.tracer = tracer
        self.session_id = session_id
        self.settings = settings or SupervisorSettings()
        self.on_background_ready = on_background_ready
        self.today = today or date.today()
        self.clock = clock
        self.started_at = clock()
        self.call_warning_given = False

        self.orders_agent = OrdersAgent(
            orders_model, db, tracer, self.settings.orders_max_tool_calls, self.today, session_id
        )
        self.tools = {tool.name: tool for tool in SUPERVISOR_TOOLS}
        self.tool_schemas = [tool.schema() for tool in SUPERVISOR_TOOLS] + [ASK_ORDERS_AGENT]
        # LangGraph Studio brings its own persistence, so it passes checkpointer=None.
        self.graph = self.build_graph().compile(
            checkpointer=InMemorySaver() if checkpointer == "memory" else checkpointer,
            name="support_agent",
        )
        self.config: dict[str, Any] = {
            "configurable": {"thread_id": session_id},
            "run_name": "support_agent",
            # session_id groups every run of this call into one LangSmith thread.
            "metadata": {"agent": "supervisor", "session_id": session_id},
            "recursion_limit": 2 * self.settings.max_tool_calls + 6,
            "callbacks": [TraceHandler(tracer, "supervisor")],
        }

        self.finished = False
        self.finish_reason: str | None = None
        self.closed = False
        self.job: OrdersJob | None = None
        self.job_count = 0
        self.background: queue.Queue[dict[str, Any]] = queue.Queue()
        self.tracer.event(
            "call_start",
            "code",
            model_or_tool=getattr(model, "model_name", None),
            orders_model=getattr(orders_model, "model_name", None),
            settings=vars(self.settings),
        )

    # --- The graph ------------------------------------------------------------

    def build_graph(self) -> StateGraph:
        graph = StateGraph(SupportState)
        graph.add_node("identity", self._identity_node)
        add_tool_agent(
            graph,
            agent="supervisor",
            model=self.model,
            tools=self.tool_schemas,
            run_tool=self._run_tool,
            system_prompt=self._system_prompt,
            max_tool_calls=self.settings.max_tool_calls,
            tracer=lambda: self.tracer,
            after_tools=self._after_tools,
        )
        graph.add_edge(START, "identity")
        graph.add_conditional_edges(
            "identity", lambda state: "model" if state.get("next_step") == "model" else END, ["model", END]
        )
        return graph

    def _identity_node(self, state: dict[str, Any]) -> dict[str, Any]:
        """Steps 1 and 2 in plain code. Once verified, every turn goes straight to the AI.

        It runs first on every turn, so it also resets the per-answer tool-call count.
        """
        new_turn = {"tool_calls_made": 0, "limit_hit": False}
        if state.get("customer"):
            return {**new_turn, "next_step": "model"}

        check = IdentityCheck.from_state(state.get("identity"), self._lookup_customer, self.tracer)
        heard = next((m.text for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)), "")
        reply = check.handle(heard)
        update: dict[str, Any] = {**new_turn, "identity": check.to_state(), "next_step": "end"}
        say = reply.say
        notes: list[SystemMessage] = []

        if reply.stage == VERIFIED:
            update["customer"] = reply.customer
            if check.early_requests:
                # They told us their problem before giving their number: answer it now.
                update["next_step"] = "model"
                notes.append(
                    SystemMessage(
                        "The customer's identity is now verified. Before that they said: "
                        + json.dumps(" ".join(check.early_requests))
                        + ". Answer that now."
                    )
                )
            else:
                say = f"{say} How can I help you today?"
        elif reply.stage == FAILED:
            ctx = ToolContext(db=self.db, session_id=self.session_id, tracer=self.tracer, today=self.today)
            run_tool(TRANSFER_TO_HUMAN, ctx, {"reason": "Identity could not be confirmed."}, agent="code")
            self._finish("identity_failed")

        update["messages"] = [AIMessage(say), *notes]
        return update

    @staticmethod
    def _after_tools(state: dict[str, Any]) -> str:
        """Stop when the model already told the customer it is checking and only started a job.

        The model says "Let me check that for you" and calls ``ask_orders_agent`` in
        the same reply, so the customer hears words at once. Calling the model again
        after "started" would only repeat that sentence, so the turn ends here; the
        answer comes later from ``respond_to_background()``.
        """
        messages = state.get("messages", [])
        results = []
        for message in reversed(messages):
            if not isinstance(message, ToolMessage):
                break
            results.append(message)
        asked = messages[-len(results) - 1] if results and len(messages) > len(results) else None
        if not isinstance(asked, AIMessage) or not asked.text.strip():
            return "model"
        only_started_jobs = all(m.name == "ask_orders_agent" and '"status": "started"' in m.text for m in results)
        return END if only_started_jobs else "model"

    def _system_prompt(self, state: dict[str, Any]) -> str:
        customer = state.get("customer") or {}
        today = self.today.isoformat()
        return (
            PROMPT_PATH.read_text(encoding="utf-8")
            .replace("{today}", f"{spoken_date(today)} ({today})")
            .replace("{customer_name}", f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip())
        )

    def _lookup_customer(self, phone: str) -> dict[str, Any]:
        ctx = ToolContext(db=self.db, session_id=self.session_id, tracer=self.tracer, today=self.today)
        return run_tool(LOOKUP_CUSTOMER, ctx, {"phone": phone}, agent="code")

    def _run_tool(self, tool_call: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        customer_id = (state.get("customer") or {}).get("customer_id")
        args = tool_call.get("args") or {}
        if tool_call["name"] == "ask_orders_agent":
            return self._start_orders_job(str(args.get("request") or "").strip(), customer_id)

        tool = self.tools.get(tool_call["name"])
        if tool is None:
            return {"error": f"There is no tool called {tool_call['name']}."}
        ctx = ToolContext(db=self.db, session_id=self.session_id, customer_id=customer_id, tracer=self.tracer, today=self.today)
        result = run_tool(tool, ctx, args, agent="supervisor")
        if tool_call["name"] == "transfer_to_human" and "error" not in result:
            self._finish("transferred_to_human")
        return result

    # --- What the runtime calls -----------------------------------------------

    @property
    def messages(self) -> list:
        """The conversation as LangGraph keeps it for this call."""
        return list(self.graph.get_state(self.config).values.get("messages", []))

    def greeting(self) -> Iterator[str]:
        text = IdentityCheck(self._lookup_customer, self.tracer).greeting()
        self._spoken(text)
        yield text

    def respond(self, text: str) -> Iterator[str]:
        """Answer one finished customer turn."""
        self.tracer.new_turn()
        self.tracer.event("user_said", "code", input=text)
        if self.finished:
            return
        if self._elapsed() >= self.settings.call_limit_seconds:
            yield from self.call_time_check()
            return
        yield from self._run_graph({"messages": [HumanMessage(text)]})

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

        for item in items:
            if item["kind"] == "fixed":
                self._remember(item["text"])
                self._spoken(item["text"])
                yield item["text"] + " "
        results = [SystemMessage(item["message"]) for item in items if item["kind"] == "orders_result"]
        if results:
            yield from self._run_graph({"messages": results})

    def _elapsed(self) -> float:
        return self.clock() - self.started_at

    def call_time_due(self) -> bool:
        """True when ``call_time_check()`` has something to say."""
        if self.finished:
            return False
        elapsed = self._elapsed()
        return elapsed >= self.settings.call_limit_seconds or (
            elapsed >= self.settings.call_warning_seconds and not self.call_warning_given
        )

    def call_time_check(self) -> Iterator[str]:
        """Speak the call-limit warning or the goodbye when it is time. Empty otherwise."""
        elapsed = self._elapsed()
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
            self._remember(CALL_LIMIT_WARNING_TEXT)
            self._spoken(CALL_LIMIT_WARNING_TEXT)
            yield CALL_LIMIT_WARNING_TEXT

    def close(self, reason: str = "call_ended") -> None:
        """The call is over: forget any running job and write the last trace line."""
        if self.closed:
            return
        self.closed = True
        if self.job and not self.job.done:
            self.tracer.event("agent_result", "code", input=self.job.request, output="cancelled: the call ended")
        customer = self.graph.get_state(self.config).values.get("customer") or {}
        self.tracer.event(
            "call_end",
            "code",
            input=reason,
            output={"finish_reason": self.finish_reason, "customer_id": customer.get("customer_id")},
            duration_ms=self._elapsed() * 1000,
        )

    # --- Running the graph and streaming its words ----------------------------

    def _run_graph(self, graph_input: dict[str, Any]) -> Iterator[str]:
        """Yield the words to speak: fixed identity text, and the model's text as it streams."""
        spoken: list[str] = []
        pending = ""  # text of the model call that is streaming right now
        pending_id = None
        interrupted = False
        after_fixed_text = False  # a space is needed before the model's first word
        stream = self.graph.stream(graph_input, self.config, stream_mode=["messages", "updates"])
        try:
            for mode, data in stream:
                if mode == "updates":
                    for node, update in (data or {}).items():
                        if node == "identity" and update:
                            for message in update.get("messages", []):
                                if isinstance(message, AIMessage) and message.text:
                                    piece = (" " if spoken else "") + message.text
                                    spoken.append(piece)
                                    after_fixed_text = True
                                    yield piece
                        elif node == "model":
                            pending, pending_id = "", None  # that model call is saved now
                    continue

                message, metadata = data
                if metadata.get("langgraph_node") != "model" or not isinstance(message, AIMessageChunk):
                    continue
                if message.id != pending_id:
                    pending, pending_id = "", message.id
                piece = message.text
                if piece:
                    if after_fixed_text:
                        piece, after_fixed_text = " " + piece.lstrip(), False
                    pending += piece
                    spoken.append(piece)
                    yield piece
        except GeneratorExit:
            interrupted = True
            stream.close()
            if pending:
                self._remember(pending + INTERRUPTED_MARK)
            raise
        except Exception as exc:
            self.tracer.event("error", "supervisor", output=f"{type(exc).__name__}: {exc}")
            sorry = "Sorry, I'm having a technical problem. Could you say that again, please?"
            spoken.append(sorry)
            yield sorry
        finally:
            self._spoken("".join(spoken).strip(), interrupted=interrupted)

    def _remember(self, text: str) -> None:
        """Add something we said outside the model (fixed text) to the conversation."""
        try:
            self.graph.update_state(self.config, {"messages": [AIMessage(text)]}, as_node="model")
        except Exception as exc:
            self.tracer.event("error", "code", input="remember", output=f"{type(exc).__name__}: {exc}")

    # --- Orders jobs ------------------------------------------------------------

    def _start_orders_job(self, request: str, customer_id: str | None) -> dict[str, Any]:
        if not request:
            return {"error": "Missing argument: request."}
        if self.job and not self.job.done:
            return {
                "status": "busy",
                "message": "An orders request is already running. Wait for its answer before asking another.",
            }

        self.job_count += 1
        background = self.settings.orders_in_background
        call_event_id = self.tracer.event(
            "agent_call",
            "supervisor",
            input=request,
            output={"status": "started" if background else "running", "job_id": self.job_count},
            model_or_tool="ask_orders_agent",
        )
        job = OrdersJob(self.job_count, request, call_event_id)
        self.job = job

        if not background:
            result = self.orders_agent.run_job(request, customer_id, parent_id=call_event_id)
            job.done = True
            return {"status": result.status, "message": result.message, "order_ids": result.order_ids}

        # Keep the LangSmith tree: the job's runs hang under this tool call.
        parent_run = get_current_run_tree()
        job.thread = threading.Thread(
            target=self._run_orders_job,
            args=(job, customer_id, parent_run),
            name=f"orders-job-{job.job_id}",
            daemon=True,
        )
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

    def _run_orders_job(self, job: OrdersJob, customer_id: str | None, parent_run: Any) -> None:
        with tracing_context(parent=parent_run) if parent_run else nullcontext():
            result: OrdersResult = self.orders_agent.run_job(job.request, customer_id, parent_id=job.call_event_id)
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

    # --- Helpers ----------------------------------------------------------------

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
    checkpointer: Any = "memory",
    **settings_overrides: Any,
) -> Supervisor:
    from agents.models import build_chat_model
    from agents.orders.agent import build_orders_model
    from shop.db import open_shop_db

    settings = SupervisorSettings(
        max_tool_calls=int(config.get("max_tool_calls") or 5),
        orders_max_tool_calls=int(orders_config.get("max_tool_calls") or 5),
        call_warning_seconds=float(config.get("call_warning_seconds") or 14 * 60),
        call_limit_seconds=float(config.get("call_limit_seconds") or 15 * 60),
        **settings_overrides,
    )
    return Supervisor(
        build_chat_model(config, "gpt-5.4-mini"),
        build_orders_model(orders_config),
        db or open_shop_db(),
        tracer or Tracer(session_id),
        session_id,
        settings,
        on_background_ready,
        today,
        checkpointer=checkpointer,
    )
