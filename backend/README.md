# Voice Agent Backend

FastAPI backend for realtime voice-agent sessions. It receives microphone audio
over WebSocket, transcribes speech, runs an agent turn, streams TTS audio back to
the client, and optionally persists oral-exam progress to Supabase.

The backend supports two runtime modes:

- **Exam mode**: `/ws?user_id=...&exam_id=...&attempt_id=...` loads Supabase
  context and runs the LangGraph-backed oral exam agent.
- **Chat mode**: `/ws` without exam query params runs a simple voice chat agent.

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
├── server.py                    # FastAPI app and HTTP/WebSocket routes
├── config/global.yaml           # shared defaults
├── agents/
│   ├── base.py                  # BaseAgent.run_turn(...) contract
│   ├── chat/agent.py            # simple voice chat agent
│   └── exam/                    # oral exam agent, prompts, config
├── core/
│   ├── session.py               # WebSocket session lifecycle
│   ├── pipeline.py              # LLM -> TTS orchestration
│   ├── voice_runtime_pool.py    # warmed runtime leasing/reuse
│   ├── transport/websocket.py   # audio packet handling/resampling
│   └── nodes/
│       ├── stt/faster_whisper.py
│       └── tts/realtime.py
└── services/
    ├── database.py              # Supabase integration
    ├── llm.py                   # vLLM/OpenAI-compatible LLM client
    └── voice_verification.py
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

## Prerequisites For Docker

- Docker Engine and Docker Compose plugin
- NVIDIA GPU drivers if using the default vLLM stack
- NVIDIA Container Toolkit for GPU access inside containers

The compose stack uses named volumes for Hugging Face and Torch caches:

- `huggingface_cache`
- `torch_cache`

## Compose Files

| File | Purpose |
| --- | --- |
| `docker-compose.yml` | Recommended backend + vLLM stack, with healthcheck and runtime pool env vars. |
| `docker-compose.vllm.yml` | Older vLLM compose variant kept for reference. |

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
| `TURN_DETECTION_DEVICE` | Device for turn-detection model, usually `cpu` or `cuda`. |
| `VOICE_RUNTIME_MIN_WARM` | Number of warmed voice runtimes to keep ready. |
| `VOICE_RUNTIME_MAX_CONCURRENT` | Maximum concurrent voice sessions. |
| `SUPABASE_URL` | Required for exam sessions. |
| `SUPABASE_SERVICE_ROLE_KEY` | Required for exam sessions. |

Agent config is layered:

1. `code/config/global.yaml`
2. `code/agents/<agent>/config.yaml`
3. supported environment overrides

## HTTP / WebSocket API

### `GET /`

Health/status payload.

### `GET /voice-reference?user_id=...`

Checks whether a user has a stored voice reference.

### `POST /voice-reference`

Uploads a voice enrollment sample.

Form fields:

- `user_id`
- `audio`

### `WS /ws`

Runs a voice session.

Query params:

- `user_id`
- `exam_id`
- `attempt_id`

When any of those params are present, the backend loads exam context and runs the
exam agent. Without them, it runs the chat agent.

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

## Notes

- STT and TTS runtime logic live under `code/core/nodes/`, not `services/`.
- `services/` is for external integrations such as Supabase, LLM API access, and
  voice verification.
- Oral-attempt evaluation is not triggered here; this backend submits/saves the
  oral attempt and another system should handle evaluation.
