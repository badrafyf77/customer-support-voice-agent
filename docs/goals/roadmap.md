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

The detailed plan is in [../plans/phase-1-plan.md](../plans/phase-1-plan.md).

Where Phase 1 stopped, and what is still open: [../plans/phase-1-status.md](../plans/phase-1-status.md).

Still open (2026-11-09):

- Full scenario score on LangGraph + LangChain, both agents on `gpt-5.4-mini`
  (supervisor reasoning `none`, orders agent `low`): **43/45 runs, 14/15
  scenarios passed every run**. Both misses are in `return_too_late`: once the
  reason (30-day window) wasn't said, once the orders agent used `cannot`
  instead of `done`. Cost of the 45 runs: about $0.20. Fixed in the orders
  prompt (clear meaning of each status, always say why); `return_too_late` then
  passed 3/3.
- Time to the first spoken word: 0.83 s median; 0.82 s for orders questions.
- One full voice call where the agent answers (the first real call, on Modal, only reached the identity step).

- [x] Switch to OpenAI models that use tools well: `gpt-5.4-mini` for the
      supervisor and the orders agent (cheap; `gpt-5.5` was tried first). The GPU stays for speech,
      voice detection and turn detection. See [03-tools.md](./03-tools.md).
- [x] Build the fake ShopEasy database (customers, orders, deliveries, return
      policy, FAQ, tickets, handoffs). See [README.md](./README.md#the-fake-company).
- [x] Add tool calling to the AI, with a limit of 5 tool calls per answer.
- [x] Build the tools: `search_faq`, `get_return_policy`, `create_ticket`,
      `transfer_to_human` (supervisor), and `list_my_orders`, `get_order`,
      `track_delivery` (orders agent).
- [x] Add the supervisor (talks to the customer) and the orders agent (works in
      the background and only reports to the supervisor). See
      [05-multi-agent.md](./05-multi-agent.md).
- [x] Let the supervisor keep talking while the orders agent works, and give the
      result when nobody is speaking.
- [x] Add the fixed first steps of a call in plain code: find the customer by
      phone number, then confirm their name. See [01-foundations.md](./01-foundations.md).
- [x] Add the limits: 5 tool calls per answer, 5 per orders job, 15 minutes per call.
- [x] Save a trace line for every step, one file per call.
- [x] Add a text-only test runner and 15 YAML test scenarios that check the
      exact tool and agent calls.

## Phase 2: Safety and quality

- [ ] Add the human approval list for risky actions (`request_refund`).
- [ ] Add reflection before refunds: a second AI checks the refund against the
      real order and the return policy. See [02-reflection.md](./02-reflection.md).
- [ ] Add the speaking checks (no competitor names, not too long, no lists or
      symbols).
- [ ] Grow the test scenarios to 30+ calls with the correct expected results.
- [ ] Add code tests and AI-judge tests (yes/no questions).
- [ ] Measure: scores with and without reflection.

### Safety and guardrails (Phase 1 only does the simple version)

- [ ] Stop prompt injection: a customer saying "ignore your rules" or "I'm an
      admin" must not change what the agents do.
- [ ] Two layers of protection: the specialist agent checks the rules, **and**
      plain code limits what each tool can read or change.
- [ ] Check what the supervisor sends to the specialists, and what they send back.
- [ ] Least privilege: each tool can only do its own job, for its own customer.
- [ ] Stronger identity check for risky requests (they always go to a human).
- [ ] Test scenarios for each attack above.

## Phase 3: MCP

- [ ] Move the shop tools into an MCP server. See [04-mcp.md](./04-mcp.md).
- [ ] Use all three MCP parts: tools, resources and prompts.
- [ ] Split it into a read-only server and a server that can change data.
- [ ] Protect the servers with a token, and run them in Docker.
- [ ] Demo: connect the same server to Claude Desktop.

## Phase 4: Agent team and plans

- [ ] More helper agents (Refunds, FAQ), next to the Orders agent from
      Phase 1. See [05-multi-agent.md](./05-multi-agent.md).
- [ ] Plans in JSON for complicated requests, checked by code before running.
- [ ] Ask "Are you sure?" before any risky step.
- [ ] Analytics agent for the manager (writes Python, runs it in Docker).
- [ ] After-call checker that grades each call.

## Phase 5: Screens and report

- [ ] Live "agent brain" screen during a call. See [presentation.md](./presentation.md).
- [ ] Manager page: approval list, call summaries, test scores.
- [ ] Diagrams in the professor's color style.
- [ ] Final report with the numbers from the tests.
