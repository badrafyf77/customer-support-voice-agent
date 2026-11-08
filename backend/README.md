# Voice Agent Backend

FastAPI backend for realtime voice-agent sessions. It receives microphone audio
over WebSocket, transcribes speech, runs the selected agent, streams TTS audio
back to the client, and exposes a few support endpoints.

This README stays project-level and agent-neutral. Agent-specific behavior lives
inside each folder under [`code/agents`](./code/agents).

## Runtime Flow

```text
Browser microphone
  -> FastAPI WebSocket /ws
  -> core/transport/websocket.py
  -> core/nodes/stt/faster_whisper.py
  -> core/session.py
  -> agents/support/agent.py   (identity steps, supervisor, orders agent, shop tools)
  -> core/pipeline.py          (speaks the text the supervisor streams)
  -> core/nodes/tts/realtime.py
  -> WebSocket tts_chunk messages
```

For the detailed file-by-file map, see [`code/ARCHITECTURE.md`](./code/ARCHITECTURE.md).

## Important Files

```text
code/
├── server.py                    # FastAPI app and agent selection
├── config/global.yaml           # shared defaults
├── agents/
│   ├── base.py                  # BaseAgent.run_turn(...) contract
│   ├── tool_loop.py             # shared model -> tools -> model loop
│   ├── support/                 # supervisor: talks to the customer
│   └── orders/                  # orders specialist (background)
├── shop/                        # fake ShopEasy database and its tools
├── core/
│   ├── session.py               # WebSocket session lifecycle
│   ├── trace.py                 # one trace file per call
│   ├── pipeline.py              # LLM -> TTS orchestration
│   ├── voice_runtime_pool.py    # warmed runtime leasing/reuse
│   ├── transport/websocket.py   # audio packet handling/resampling
│   └── nodes/
│       ├── stt/faster_whisper.py
│       └── tts/realtime.py
└── services/
    └── llm.py                   # vLLM/OpenAI-compatible LLM client
```

## Docker Quick Start

From `backend`:

```bash
cp .env.example .env   # then set OPENAI_API_KEY
docker compose -f docker-compose.openai.yml up -d --build
```

The agents use the OpenAI API; the GPU runs speech-to-text, text-to-speech,
voice detection and turn detection. `docker-compose.yml` still starts a local
vLLM server if you want to try an open model instead.

Default port: backend app on `http://localhost:8080`.

Useful checks:

```bash
docker compose -f docker-compose.openai.yml logs -f app
curl http://localhost:8080/
```

The first build/start can take a while because Docker downloads Python
dependencies and model assets.

## Agent Selection

All voice sessions use the same WebSocket endpoint:

```text
/ws
```

Current selection logic lives in [`code/server.py`](./code/server.py):

| Connection | Agent |
| --- | --- |
| `/ws` | `support` (change it with the `VOICE_AGENT` variable) |

The selected agent is built in `server.py`, then passed into
`core/session.py::run_session(...)`. The session and pipeline only depend on the
shared `BaseAgent.run_turn(...)` interface.

To change which agent runs:

1. Edit `code/server.py::ws_endpoint`.
2. Import the target agent builder, for example `build_support_agent`.
3. Load the matching config with `load_agent_config("<agent_name>")`.
4. Pass the built agent and config to `run_session(...)`.

To add a new agent:

1. Create `code/agents/<name>/`.
2. Add `agent.py`, `config.yaml`, and `README.md`.
3. Implement a builder that returns a `BaseAgent`.
4. Keep prompts, tools, and agent-only helpers inside that folder.
5. Register the agent selection branch in `code/server.py`.

## Existing Agents

| Agent | Folder | Purpose |
| --- | --- | --- |
| `support` | [`code/agents/support`](./code/agents/support) | ShopEasy supervisor: identity steps, then answers with tools. Talks to the customer. |
| `orders` | [`code/agents/orders`](./code/agents/orders) | Orders specialist. Runs in the background for the supervisor; never talks to the customer. |

## Configuration

Copy [`.env.example`](./.env.example) to `.env`.

Common variables:

| Variable | Purpose |
| --- | --- |
| `LLM_PROVIDER` | `openai` (default) or `vllm`. Each agent's `config.yaml` can override it. |
| `LLM_MODEL` | Fallback model name. Each agent sets its own in `config.yaml` (`gpt-5.4-mini`, `gpt-5.5`). |
| `VLLM_BASE_URL` | OpenAI-compatible vLLM URL, usually `http://vllm:8000/v1` in Docker. |
| `OPENAI_API_KEY` | Required for the OpenAI models. |
| `SHOP_DB_PATH` | Where the ShopEasy database lives. Default `backend/data/shop.db`. |
| `TRACE_DIR` | Where trace files go. Default `backend/logs/traces`. |
| `VOICE_AGENT` | Which agent `/ws` runs. Default `support`. |
| `STT_MODEL` | Main faster-whisper model, default `medium.en`. |
| `STT_REALTIME_MODEL` | Optional realtime model when not sharing the main STT model. |
| `STT_USE_MAIN_MODEL_FOR_REALTIME` | Use one STT model for both realtime and final transcription. |
| `TURN_DETECTION_DEVICE` | Device for turn detection, usually `cpu` or `cuda`. |
| `VOICE_RUNTIME_MIN_WARM` | Number of warmed voice runtimes to keep ready. |
| `VOICE_RUNTIME_MAX_CONCURRENT` | Maximum concurrent voice sessions. |

Agent config is layered:

1. `code/config/global.yaml`
2. `code/agents/<agent>/config.yaml`
3. supported environment overrides

## HTTP / WebSocket API

### `GET /`

Health/status payload.

### `WS /ws`

Runs a voice session with the selected agent.

## Local Development Without Docker

Local backend runs are useful for quick code iteration, but the Docker stack is
more representative because it handles GPU/runtime dependencies and vLLM.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd code
python server.py
```

For local development, set:

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=...
```

## The ShopEasy Database

A made-up shop with 10 customers and 25 orders, built to cover the tricky
support cases (late, lost, too late to return, items that can't be returned).
Dates are counted from today, so the cases stay true on any day.

The server builds `data/shop.db` on first use. To rebuild it from scratch
(this also removes tickets and handoffs):

```bash
cd backend/code
python -m shop.seed
```

Test phone numbers: Sara Benali `07700900101` (one order), James Carter
`07700900102` (three orders); see `code/shop/seed.py` for the rest.

## Traces

Every call writes `logs/traces/<session_id>.jsonl`, one JSON line per step:
what the customer said, identity steps, every model call (with token counts),
every tool call, calls to the orders agent and their results, fillers, limits
reached, and what was spoken. `parent_id` links the lines into a tree.

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest                         # unit tests: no AI, free, about 2 seconds
pytest -m llm                  # 15 scenarios x 3 runs with the real models (costs a little)
SCENARIO_RUNS=1 pytest -m llm -k track_single_order   # one scenario, once
```

The scenarios are YAML files in `tests/scenarios/`. Each customer turn lists the
tool and agent calls we expect, calls that must not happen, the orders agent's
answer, and facts the customer must hear. The checks read the call's trace, so
they test what really happened. The trace of every scenario run is kept in
`logs/traces/scenarios/`.

## Frontend Integration

The frontend connects to this backend through `NEXT_PUBLIC_VOICE_SERVER_URL`.
For the default Docker backend:

```bash
NEXT_PUBLIC_VOICE_SERVER_URL=http://localhost:8080
```

See [`../frontend/README.md`](../frontend/README.md).

## Boundaries

- `core/` owns runtime flow: session, transport, pipeline, STT/TTS nodes.
- `agents/` owns agent behavior, prompts, tools, and per-agent config.
- `services/` owns external integrations such as LLM API access.
- Provider-specific STT/TTS logic belongs in `core/nodes/`, not `services/`.
