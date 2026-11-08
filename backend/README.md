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
  -> agents/<agent>/agent.py
  -> core/pipeline.py
  -> services/llm.py
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
│   └── chat/                    # simple chat agent
├── core/
│   ├── session.py               # WebSocket session lifecycle
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
cp .env.example .env
docker compose up -d --build
```

Default ports:

- Backend app: `http://localhost:8080`
- vLLM OpenAI-compatible server: `http://localhost:8000`

Useful checks:

```bash
docker compose logs -f app
docker compose logs -f vllm
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
| `/ws` | `chat` |

The selected agent is built in `server.py`, then passed into
`core/session.py::run_session(...)`. The session and pipeline only depend on the
shared `BaseAgent.run_turn(...)` interface.

To change which agent runs:

1. Edit `code/server.py::ws_endpoint`.
2. Import the target agent builder, for example `build_chat_agent`.
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
| `chat` | [`code/agents/chat`](./code/agents/chat) | General conversational voice assistant. |

## Configuration

Copy [`.env.example`](./.env.example) to `.env`.

Common variables:

| Variable | Purpose |
| --- | --- |
| `LLM_PROVIDER` | `vllm` or `openai`. Docker default is `vllm`. |
| `LLM_MODEL` | Model name sent to the configured LLM provider. |
| `VLLM_BASE_URL` | OpenAI-compatible vLLM URL, usually `http://vllm:8000/v1` in Docker. |
| `OPENAI_API_KEY` | Required only when `LLM_PROVIDER=openai`. |
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

For OpenAI-only local development, set:

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=...
LLM_MODEL=gpt-5
```

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
