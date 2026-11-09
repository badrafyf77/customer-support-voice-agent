# Orders Agent

A specialist that answers order questions for the [supervisor](../support).
It never talks to the customer.

- A LangGraph graph (`model <-> tools`), model `gpt-5.5` with medium reasoning
  effort, because it works in the background and must follow the rules carefully.
- Tools: `list_my_orders`, `get_order`, `track_delivery`, `get_return_policy`.
  They only see the verified customer's orders; the customer comes from code,
  never from the AI.
- At most 5 tool calls per job.
- Always answers in one JSON shape (forced with structured output):
  `{"status": "done" | "needs_info" | "cannot", "message": "...", "order_ids": [...]}`.

| File | Purpose |
| --- | --- |
| `agent.py` | `OrdersAgent.run_job(request)`. |
| `prompt.md` | What it can and can't do, and how to answer. |
| `config.yaml` | Model, reasoning effort, tool-call limit. |
