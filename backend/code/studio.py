"""The agent graphs for LangGraph Studio, where you can watch them run step by step.

Start it from ``backend``:   langgraph dev

Two graphs are listed (see ``langgraph.json``):
- ``support_agent``: the whole call. Send one customer message per run on the
  same thread: first the phone number (e.g. 07700900101), then "yes", then a
  question. Here the orders agent runs inside the ``ask_orders_agent`` tool
  call (not in the background), so the whole run shows up in one place.
- ``orders_agent``: the specialist alone. Give it ``customer_id`` (e.g. C002) and
  a message like "Where is my order?".

Tool calls write to the real ShopEasy database (``data/shop.db``); rebuild it
with ``python -m shop.seed`` from ``backend/code``.
"""
from agents.support.supervisor import build_supervisor
from core.config import load_agent_config
from core.trace import Tracer

_supervisor = build_supervisor(
    "studio",
    load_agent_config("support"),
    load_agent_config("orders"),
    tracer=Tracer("studio"),
    checkpointer=None,  # Studio keeps the threads itself
    orders_in_background=False,
)

support_graph = _supervisor.graph
orders_graph = _supervisor.orders_agent.graph
