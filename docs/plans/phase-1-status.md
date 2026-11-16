# Phase 1 Status (stopped on 16 November 2026)

Where Phase 1 stands, what was tested, what is still open, and how to start
again. The plan itself is in [phase-1-plan.md](./phase-1-plan.md).

Everything is on the `phase-1` branch. Nothing is running: the Modal app is
stopped and no frontend or backend is running locally.

---

## 1. What was built

| Part | Where | Notes |
| --- | --- | --- |
| Fake ShopEasy database | `backend/code/shop/` | SQLite, 10 customers, 25 orders, dates counted from today. `python -m shop.seed` rebuilds it. |
| Shop tools | `backend/code/shop/tools.py` | The verified customer comes from code, never from the AI. |
| Identity steps (plain code) | `backend/code/agents/support/identity.py` | Phone number, then "Am I speaking with…?". 3 tries, then a human. |
| Supervisor (talks to the customer) | `backend/code/agents/support/supervisor.py` | LangGraph graph: `identity -> model <-> tools`. `gpt-5.4-mini`, reasoning `none`. |
| Orders agent (background) | `backend/code/agents/orders/agent.py` | LangGraph graph: `model <-> tools`. `gpt-5.4-mini`, reasoning `low`. Answers `done` / `needs_info` / `cannot`. |
| Shared graph pieces | `backend/code/agents/graph.py` | Tool-call limit (5), our trace handler. |
| Traces | `backend/code/core/trace.py` | One JSON line per step, one file per call (`logs/traces/`). Also LangSmith (EU project `shopeasy-voice-agent`). |
| Voice connection | `backend/code/core/session.py`, `pipeline.py` | The pipeline speaks what the supervisor streams; an idle watcher gives background answers. |
| Text tests | `backend/tests/` | 113 free unit tests (fake models) and 15 YAML scenarios (real models). |
| LangGraph Studio | `backend/code/studio.py`, `backend/langgraph.json` | `langgraph dev` to watch the graphs run. |
| Modal (GPU in the cloud) | `backend/modal_app.py` | Same backend on an L4. Replaces Lightning AI, which is down. |
| Spoken test client | `backend/tests/voice_call.py` | Plays macOS `say` speech into the WebSocket like a microphone. |
| Frontend fixes | `frontend/src/app/page.tsx` | Asks for the microphone at the Start click, shows its state and a level bar. |

## 2. What was tested, with results

- **Unit tests:** 113 pass (`.venv/bin/pytest` in `backend`). Free, no AI.
- **Scenarios with the real models:** full run 43/45 runs, 14/15 scenarios every
  run. The one weak scenario (`return_too_late`) was fixed and passed 3/3. The
  full 3-run score has **not** been repeated since that last prompt fix.
  Cost of a full run: about $0.20 of OpenAI.
- **Speed (text):** first spoken word 0.83 s median; 0.82 s for orders questions.
- **Modal:** the image builds, the server starts on an L4 and answers
  `"status":"ok"`. A cold start took 2 to 8 minutes. Modal credits used so far:
  $1.10 of $30, billed $0.
- **Real voice call (your browser, 16 November):** the microphone works in Chrome /
  Safari (not in the Claude app's built-in browser, which can't use the
  microphone). Speech-to-text, turn ends, the identity step and text-to-speech
  all worked. The agent used the accurate transcript, not the quick one (the
  `session.py` fix works).

## 3. Still open (start here next time)

1. **Test that the agent answers correctly by voice.** Not done yet: the test
   call never got past the identity step. Do one full call: phone number, "yes",
   an order question, an FAQ question, a transfer.
2. **Phone numbers spoken with a pause fail the identity step.** The server ends
   the turn at the pause, so the agent hears "0770789" and asks again, and the
   rest of the number arrives as a new turn. Fix idea: in `identity.py`, when a
   turn has too few digits, keep them and add the digits from the next turn
   (and say "Go on" instead of "I only heard…").
3. **The call doesn't end after the identity check fails (or after a transfer).**
   The agent stops answering, as planned, but the call stays open until the
   customer hangs up. The idle watcher in `core/session.py`
   (`watch_idle_agent_turns`) never saw "nobody is speaking" in the real browser
   call. Check `silence_active` and `tts_client_playing` with a real microphone.
4. **Re-run the full scenario score once** after the last prompt changes
   (about $0.20).
5. **Docker compose is untested** (Lightning AI was down). Modal is the tested
   way to run the voice backend for now.
6. **Optional:**
   - Modal cold starts are slow (2–8 min). `min_containers=1` in `modal_app.py`
     would keep one GPU always on, but that costs about $0.80 an hour.
   - The spoken test client (`tests/voice_call.py`) once left a turn open
     forever when it sent digital silence after speech. Real microphones didn't
     do this.
   - Modal says the workspace uses its "legacy image builder" (an account
     setting in Modal). `modal_app.py` already works around its old
     `typing_extensions`.

## 4. How to start again

All commands from `backend` unless said otherwise.

```bash
# Free unit tests (fake models)
.venv/bin/pytest

# One real scenario, once (costs a little)
SCENARIO_RUNS=1 .venv/bin/pytest -m llm -k track_single_order

# Watch the graphs in LangGraph Studio
.venv/bin/langgraph dev

# Start the voice backend on Modal (prints the https://…modal.run address)
.venv/bin/modal deploy modal_app.py

# Wake it up and wait for "status 200" (cold start: 2–8 minutes)
curl -sL -w "\nstatus %{http_code} in %{time_total}s\n" https://badreddine-afyf1-etu--shopeasy-voice-agent-web.us-east.modal.run/
```

Then, in `frontend`: `npm run dev`, open **http://localhost:3000 in Chrome,
Safari or Firefox**, enter the Modal address as the server URL, click Start.

When you are done:

```bash
.venv/bin/modal app stop --yes shopeasy-voice-agent
```

and stop `npm run dev` with Ctrl+C.

Test phone numbers: Sara Benali `07700900101` (one order, SE-1042), James Carter
`07700900102` (three orders); the rest are in `backend/code/shop/seed.py`.

Keys live in `backend/.env` (OpenAI, LangSmith with the EU address). Never
commit that file.
