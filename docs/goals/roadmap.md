# Roadmap

The work is split into 5 phases. Do them in this order. Phases 1 and 2 already
cover Chapters 1–3. Phases 3 and 4 are what make the project stand out.

Tick a box (`[x]`) when a task is done.

## Phase 0: Clean the project ✅

- [x] Remove the exam agent (`backend/code/agents/exam/`).
- [x] Remove old exam code from `core/brain.py`, `core/pipeline.py` and `core/session.py`.
- [x] Remove the exam database code (Supabase) and the voice-check code.
- [x] Remove the Darija files and go back to the English turn detector.

## Phase 1: Basics

- [ ] Switch to a bigger AI model that can use tools well (the current
      Qwen 1.5B is too small). See [03-tools.md](./03-tools.md).
- [ ] Build the fake ShopEasy database (customers, orders, deliveries, return
      policy, FAQ). See [README.md](./README.md#the-fake-company).
- [ ] Add tool calling to the AI, with a limit of 5 tool calls per question.
- [ ] Build the first tools: `lookup_customer`, `get_order`, `track_delivery`,
      `get_return_policy`, `search_faq`, `create_ticket`, `transfer_to_human`.
- [ ] Add the "One moment, I'm checking…" filler while a tool runs.
- [ ] Add the fixed first steps of a call: find the customer, then check their
      identity. See [01-foundations.md](./01-foundations.md).
- [ ] Save a log line (trace) for every step.

## Phase 2: Safety and quality

- [ ] Add the human approval list for risky actions (`request_refund`).
- [ ] Add reflection before refunds: a second AI checks the refund against the
      real order and the return policy. See [02-reflection.md](./02-reflection.md).
- [ ] Add the speaking checks (no competitor names, not too long, no lists or
      symbols).
- [ ] Add a text-only test mode (no voice), so tests run fast.
- [ ] Write 30+ test calls with the correct expected results.
- [ ] Add code tests and AI-judge tests (yes/no questions).
- [ ] Measure: scores with and without reflection.

## Phase 3: MCP

- [ ] Move the shop tools into an MCP server. See [04-mcp.md](./04-mcp.md).
- [ ] Use all three MCP parts: tools, resources and prompts.
- [ ] Split it into a read-only server and a server that can change data.
- [ ] Protect the servers with a token, and run them in Docker.
- [ ] Demo: connect the same server to Claude Desktop.

## Phase 4: Agent team and plans

- [ ] Main agent plus helper agents (Orders, Refunds, FAQ). See
      [05-multi-agent.md](./05-multi-agent.md).
- [ ] Plans in JSON for complicated requests, checked by code before running.
- [ ] Ask "Are you sure?" before any risky step.
- [ ] Analytics agent for the manager (writes Python, runs it in Docker).
- [ ] After-call checker that grades each call.

## Phase 5: Screens and report

- [ ] Live "agent brain" screen during a call. See [presentation.md](./presentation.md).
- [ ] Manager page: approval list, call summaries, test scores.
- [ ] Diagrams in the professor's color style.
- [ ] Final report with the numbers from the tests.
