# Phase 1 Plan: Foundations

Status: **draft, waiting for review**. No code is written until this plan is approved.

This plan comes from the design questions we went through together. Section 1
lists every decision, so nothing is hidden. Section 3 is the work, in order.

---

## 1. Decisions

### What Phase 1 includes

- A bigger AI model (OpenAI API).
- The fake ShopEasy database (SQLite).
- Tool calling, with limits.
- Two agents: a **supervisor** (talks to the customer) and an **orders agent**
  (a specialist that works in the background).
- Fixed first steps of the call, written in plain code: find the customer, then
  check their identity.
- A trace (log line) for everything that happens.
- Automated text tests (YAML scenarios), so we don't have to test by voice every time.

### What Phase 1 does NOT include (later phases)

- `request_refund`, the human approval list, the refund checking (reflection).
- Other specialist agents (Refunds, FAQ…).
- AI-judge tests.
- Guardrails and deeper safety work. Examples: prompt-injection defences (a
  customer trying to trick the AI with "ignore your rules"), the speaking checks,
  and the "two layers of protection" idea. Phase 1 only does the simple,
  natural version (see "Safety in Phase 1" below).

### The models

| Agent | Model | Reasoning effort | Why |
| --- | --- | --- | --- |
| Supervisor | `gpt-5.4-mini` | low | It talks to the customer, so it must start speaking fast. |
| Orders agent | `gpt-5.5` | medium | It works in the background and must follow the rules carefully. |

- Both models are set in each agent's `config.yaml`, so we can change a model by
  changing one line.
- "Reasoning effort" tells a GPT-5 model how long to think before answering.
  Lower means faster.
- The GPU stays in use for speech-to-text, text-to-speech, voice detection and
  turn detection. vLLM (the server that runs open models on our own GPU) is no
  longer needed for the AI model, but we keep its Docker file.
- Note: we found no `gpt-5.5-mini` on OpenAI's model pages, so the supervisor
  uses `gpt-5.4-mini`.

### How a call works

```
Customer speaks
   │
   ▼
[Code] Step 1: "What's your phone number?"  → keep only the digits → find the customer
[Code] Step 2: "Am I speaking with Sara Benali?" → yes / no
        (3 failed tries → offer to transfer to a human)
   │
   ▼  identity verified
[Supervisor AI]  ── fast tools (wait for result) ──→ search_faq, get_return_policy,
   │                                                 create_ticket, transfer_to_human
   │
   └── ask_orders_agent (runs in the BACKGROUND) ──→ [Orders agent AI]
           │                                            list_my_orders, get_order,
           │                                            track_delivery, get_return_policy
           ▼
        returns  done / needs_info / cannot  →  back to the supervisor
```

- **Identity comes first.** Before steps 1 and 2 are done, the AI does nothing.
- **The supervisor is always in the middle.** The orders agent never talks to
  the customer. It only answers the supervisor.
- **Background calls:** only calls to an *agent* run in the background. Database
  tools take milliseconds, so the supervisor just waits for them. When it calls
  the orders agent, the supervisor gets "started" right away and can keep
  talking ("Let me check that, it'll take a few seconds").
- **When the background result comes back,** it waits until nobody is speaking.
  Then the supervisor starts a new turn by itself and gives the answer. Only one
  orders job runs at a time. If a job takes more than 20 seconds, the supervisor
  says it is taking longer than usual and offers a ticket. If the customer hangs
  up, the job is cancelled.
- **Filler:** the supervisor model writes its own filler sentence. As a safety
  net, if a fast tool ever takes longer than 1 second, plain code speaks a short
  fixed sentence, so the customer never hears silence.
- **Risky requests always go to a human.** For example, a customer who asks for
  a refund is transferred with `transfer_to_human`.

### The orders agent's answer

The orders agent always returns JSON (structured data) in one of three shapes:

```json
{"status": "done",       "message": "Order SE-1042 is out for delivery, arriving Thursday 12 Nov.", "data": {...}}
{"status": "needs_info", "message": "The customer has 3 orders. Which one: SE-1042 (headphones), SE-1051 (shoes), SE-1060 (lamp)?"}
{"status": "cannot",     "message": "Order SE-1099 is not on this customer's account."}
```

### Limits

| Limit | Value | What happens when it is reached |
| --- | --- | --- |
| Tool calls each time the supervisor answers | 5 | One last model call with tools turned off, so the model must answer in words. |
| Tool calls per orders job | 5 | Same; the job returns `cannot` with what it found so far. |
| Whole phone call | 15 min | At 14 minutes the agent wraps up politely and offers a ticket. At 15 minutes the call ends. |

All limits are config values. Reaching a limit always writes a trace line.

### Safety in Phase 1 (simple version only)

- Order tools receive the verified customer from **code**, not from the AI.
  `list_my_orders` needs this anyway, and `get_order` / `track_delivery` say "not
  found" for orders that belong to someone else. That's all for Phase 1. Deeper
  safety comes in a later phase.

### Traces

- **One file per call:** `backend/logs/traces/<session_id>.jsonl`. One JSON object
  per line, one line per event.
- Every line has: `ts` (time), `session_id`, `turn_id`, `event_id`, `parent_id`,
  `agent` (`code` / `supervisor` / `orders`), `kind`, `input`, `output`,
  `model_or_tool`, `duration_ms`, plus extras (for example token counts).
- `kind` is one of: `call_start`, `user_said`, `identity_step`, `llm_call`,
  `tool_call`, `agent_call`, `agent_result`, `filler`, `limit_hit`, `spoken`,
  `error`, `call_end`.
- `parent_id` links the lines into a tree. For example, the orders agent's
  `tool_call` lines point to the supervisor's `agent_call` line. The Phase 5
  "agent brain" screen can read this tree.

### Tests

- **Unit tests** (pytest, no AI, fast, free): database, tools, identity steps,
  reading phone numbers from text, limits, trace file, and the tool loop with a
  *fake* model.
- **Scenario tests** (YAML, real OpenAI model, costs a few cents): each scenario
  is a short conversation with the exact actions we expect. Each scenario runs 3
  times, and we report the pass rate.

---

## 2. New and changed files (overview)

```
backend/
  code/
    agents/
      support/            ← was agents/chat/ (renamed: this is now the supervisor)
        agent.py          ← plugs the supervisor into the voice runtime
        identity.py       ← steps 1 and 2, plain code
        supervisor.py     ← the supervisor's tool loop + background jobs
        prompt.md         ← supervisor instructions
        config.yaml
      orders/
        agent.py          ← orders agent loop, returns done/needs_info/cannot
        prompt.md
        config.yaml
    shop/
      schema.sql          ← tables
      seed.py             ← builds a fresh shop.db with the fake data
      db.py               ← small query helpers
      tools.py            ← the tool functions + their descriptions for the AI
    core/
      trace.py            ← writes the trace file
      models.py           ← new AgentResult action: "stream"
      pipeline.py         ← can speak text from the agent's generator
      session.py          ← background results, call time limit
    services/
      llm.py              ← tool calling + GPT-5 reasoning settings
  data/shop.db            ← generated, not committed
  logs/traces/            ← generated, not committed
  tests/
    unit/...
    scenarios/*.yaml
    test_scenarios.py
    text_runner.py        ← runs the "agent brain" with text only
  pytest.ini
  requirements-dev.txt    ← pytest
```

The supervisor, identity steps, orders agent, tools and traces form the **agent
brain**. It knows nothing about audio. It takes customer text and gives back
text through a generator (a Python function that hands out pieces of text one at
a time). The voice pipeline and the text test runner both use the same brain, so
the tests check the real code.

---

## 3. Steps

Each step is one commit on a `phase-1` branch. Every step ends with a "Done when"
check.

### Step 1: Update the goal documents

- `docs/goals/roadmap.md`: rewrite Phase 1 with the new scope (orders agent and
  text scenario tests move here). Add a clear "Safety and guardrails" part to
  the later phases: prompt injection, two layers of protection, speaking
  checks, and limits on what each tool may do.
- `docs/goals/01-foundations.md`: add the 8-step table (who does each step: AI,
  code or human).
- `docs/goals/03-tools.md`: fix the model section (OpenAI, not a bigger Qwen) and
  the tool list per agent.

**Done when:** the documents match this plan.

### Step 2: Switch to the OpenAI GPT-5 models

- `services/llm.py`: GPT-5 models don't accept `temperature`,
  `frequency_penalty` or `presence_penalty`, which the code sends on every call
  today. Only send them to models that accept them. Add a `reasoning_effort`
  setting.
- Each agent's `config.yaml` gets `llm_model` and `reasoning_effort`.
- `.env.example` and `docker-compose.openai.yml`: default to OpenAI +
  `gpt-5.4-mini`.
- Keep the `prewarm` and `measure_inference_time` functions working (they warm
  up the connection and measure speed at start-up).

**Done when:** unit test: the request settings are correct for GPT-5 and for
older models. Manual: the server starts and prewarm succeeds with a real key.

### Step 3: Traces

- `core/trace.py`: a `Tracer` for each call. `tracer.event(kind, ...)` writes
  one line. `tracer.span(...)` is used with `with`: it measures `duration_ms`
  and sets `parent_id` automatically.
- Writing to the file is thread-safe (several threads can write without mixing
  lines up), because the voice pipeline and background jobs run in threads.
- Add `logs/` and `data/*.db` to `.gitignore`.

**Done when:** unit test: nested spans give the right `parent_id`; every line
is valid JSON; one file per session.

### Step 4: The ShopEasy database

- `shop/schema.sql`: `customers` (id, name, phone, email, postcode),
  `orders` (id like `SE-1042`, customer, date, status, total),
  `order_items` (product, quantity, price, `returnable`), `deliveries`
  (carrier, tracking number, status, expected date, delivered date, last
  location), `return_policy` (text sections), `faq` (question, answer, keywords),
  `tickets`, `handoffs`.
- `shop/seed.py`: about 10 customers and 25 orders. They are built on purpose to
  cover: on time, late, lost, being prepared, cancelled, delivered 10 days ago
  (can return), delivered 45 days ago (too late), a customer with several orders,
  a customer with one order, and an item that can't be returned. Dates are
  counted **from today**, so "10 days ago" stays true whenever we run it.
  Plus the return policy and 12–15 FAQ entries.
- `shop/db.py`: open the database, small query helpers.

**Done when:** unit tests: the seed runs twice with no errors, and each tricky
case exists.

### Step 5: The tools

- `shop/tools.py`: plain Python functions plus a clear description for the AI.
  The AI reads the description to decide when to use each tool.
  - Code only: `lookup_customer(phone)`
  - Supervisor: `search_faq(query)`, `get_return_policy(topic?)`,
    `create_ticket(subject, details)`, `transfer_to_human(reason)`
  - Orders agent: `list_my_orders()`, `get_order(order_id)`,
    `track_delivery(order_id)`, `get_return_policy(topic?)`
- Each tool gets a `ToolContext` (verified customer id, database, tracer) from
  code. The AI never chooses the customer.
- Each tool returns a small dictionary. Errors are returned as data (`{"error":
  "order not found"}`); they don't crash the call.
- Every tool call is traced, with its duration. This shows whether tools really
  take only milliseconds.

**Done when:** unit tests for each tool, including "the order belongs to someone
else → not found" and "ticket saved, ticket number returned".

### Step 6: Tool calling in `services/llm.py`

- New function `stream_chat(messages, tools, ...)`. It streams the answer and
  gives back events: `TextDelta` (a piece of text) or `ToolCalls` (the model
  wants to run tools). While streaming, it puts the tool-call pieces together
  into complete calls.
- A small reusable **tool loop** (used by both agents):
  stream → if the model asks for tools, run them → add the results → stream
  again. It stops at the limit and makes one last call with tools turned off.
- Cancelling still works, so the customer can still interrupt the agent.

**Done when:** unit tests with a fake model: text only; one tool then text;
several tools; limit reached → tools turned off; tool error goes back to the
model.

### Step 7: Identity steps (plain code)

- `agents/support/identity.py`: a small **state machine** (code that moves through
  fixed stages one after another): `ask_phone` → `confirm_name` → `verified`, or
  `failed` → offer a transfer.
- Turning spoken text into a phone number: keep only the digits, and turn
  number words into digits ("double five" → 55, "oh" → 0, "zero").
- "Am I speaking with Sara Benali?" → read yes / no from the reply ("yes",
  "yeah", "that's me" / "no", "nope", "wrong").
- 3 tries at each stage. Every stage writes an `identity_step` trace line.
- The sentences it speaks are fixed text (no AI), so these turns are instant.

**Done when:** unit tests: different ways of saying a number, yes/no answers,
3 failures → `failed`, a wrong person → ask again.

### Step 8: The orders agent

- `agents/orders/agent.py`: `run_job(request, ctx) -> OrdersResult`. Model:
  `gpt-5.5`, its own prompt, its 4 tools, limit of 5 tool calls.
- The final answer must use the `done` / `needs_info` / `cannot` JSON shape. We
  use OpenAI's **structured output** (the model is forced to answer in that
  exact JSON shape), so the JSON is always valid.
- `prompt.md`: what it can do (order status, delivery, whether a return is
  allowed) and what it can't (refunds, changing orders, other customers'
  orders). It asks for missing information through `needs_info` instead of
  guessing.

**Done when:** unit tests with a fake model: each of the 3 statuses; the limit
is reached; all lines are traced under the parent `agent_call`.

### Step 9: The supervisor

- `agents/support/supervisor.py`: `respond(text) -> generator of text`.
  - Before identity is verified: hand the text to `identity.py`.
  - After that: the tool loop with the supervisor tools, using `gpt-5.4-mini`.
  - `ask_orders_agent(request)` starts the orders job in a background thread
    and returns `{"status": "started"}` right away. Only one job at a time.
  - When the job ends, the result goes into a queue. `respond_to_background()`
    gives that result to the model, which tells the customer.
  - After 20 seconds, the "this is taking longer than usual" message plays.
  - `transfer_to_human` → speak the goodbye, then mark the call as finished.
- The supervisor keeps its **own full history**, with tool calls and results.
  The session's history stays as the visible transcript.
- `prompt.md`: ShopEasy, English only, short spoken sentences, no lists or
  symbols, always use the tools for facts, risky requests go to a human, what
  to say while an orders job runs.
- **Done when:** unit tests with a fake model and a fake orders agent: a
  background result arrives; a second question is answered while the job runs;
  only one job at a time.

### Step 10: Connect the brain to the voice runtime

- `core/models.py`: a new `AgentResult.stream(generator)` action: "speak whatever
  this generator gives".
- `core/pipeline.py`: for a `stream` result, use the agent's generator instead
  of calling `llm.generate` directly. The quick-answer and text-to-speech logic
  stay the same.
- `core/session.py`:
  - When the brain says a background result is ready, wait until the customer
    is not talking and the agent is not playing audio. Then start an
    agent-initiated turn (this already exists for the greeting).
  - The 14/15-minute call limit timer.
  - Cancel background jobs when the customer disconnects.
  - Write `call_start` / `call_end` trace lines.
- `agents/chat/` → `agents/support/`; `server.py` builds the support agent.
- Interrupting: if the customer cuts the agent off, the supervisor's history
  keeps only what was actually spoken.

**Done when:** manual voice call: the greeting, identity, a delivery question
answered from the background, an FAQ question, a transfer. The trace file
shows the whole tree.

### Step 11: Text runner and scenario tests

- `tests/text_runner.py`: runs the same supervisor with text only. For each
  customer line: collect the spoken text, wait for background jobs, then also
  collect the background answer. Gives back the transcript and the path to the
  trace file.
- Scenario format (`tests/scenarios/*.yaml`):

  ```yaml
  name: track_single_order
  customer_phone: "0612345678"     # used by the identity steps
  turns:
    - say: "zero six one two three four five six seven eight"
    - say: "yes that's me"
    - say: "Where is my order SE-1042?"
      expect_calls:                 # in this order; harmless extra calls allowed
        - supervisor: ask_orders_agent
        - orders: track_delivery
          args: {order_id: "SE-1042"}
      orders_result: done
      must_not_call: [transfer_to_human, create_ticket]
      answer_contains: ["Thursday"]
  ```

- `tests/test_scenarios.py`: pytest reads the trace file and checks each rule.
  Each scenario runs 3 times. At the end we print a pass-rate table (for example
  "14/15 scenarios, 43/45 runs"). Marked `@pytest.mark.llm`, so the free unit
  tests can run alone.
- First scenarios (15):
  1. Identity OK → greeted by name
  2. Wrong phone number 3 times → offer a transfer
  3. "No, that's not me" → asked again
  4. Track a single order (the example above)
  5. Customer with several orders: "Where's my order?" → `needs_info` →
     supervisor asks which one → customer picks one → `done`
  6. Late delivery → explains the new date
  7. Lost package → orders agent → supervisor creates a ticket
  8. Return delivered 10 days ago → allowed
  9. Return delivered 45 days ago → not allowed, says why
  10. Item that can't be returned → not allowed, says why
  11. Shipping cost question → `search_faq` only, no `ask_orders_agent`
  12. General return-policy question → `get_return_policy`
  13. "Let me talk to a person" → `transfer_to_human`
  14. Refund request → `transfer_to_human` (risky requests go to a human)
  15. Another customer's order number → orders agent `cannot`

**Done when:** all scenarios run; the pass-rate table is printed; we look at the
failures together and fix the prompts.

### Step 12: Finish

- Update `backend/code/ARCHITECTURE.md` and the backend README (how to seed
  the database and how to run each kind of test).
- Tick the Phase 1 boxes in the roadmap.

**Done when:** a fresh clone can seed the database, run the unit tests and run
the scenarios by following the README.

---

## 4. Risks to watch

- **Speed:** how fast `gpt-5.4-mini` starts speaking (time to the first word),
  even with low reasoning effort. We measure it in the traces at Step 10. If it's
  too slow, we try a smaller model or reasoning effort `minimal`.
- **Streaming with tool calls:** the current quick-answer logic expects text
  from the very first piece. When the model asks for a tool first, the first
  words are delayed. We check this at Step 10.
- **Threads:** the pipeline runs in threads, and background jobs add more
  threads. Trace writing and the result queue must be thread-safe (covered at
  Steps 3 and 9).
- **Scenario flakiness:** AI models don't always answer the same way. That's
  why each scenario runs 3 times. We keep `answer_contains` to short key facts.
