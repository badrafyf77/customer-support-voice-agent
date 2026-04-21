# Customer Support Voice Agent

Realtime browser-to-backend voice-agent project with:

- a **FastAPI voice backend** in `backend/ExaminerAgent`
- a **Next.js voice chat frontend** in `frontend`
- support for simple voice chat and Supabase-backed oral exam sessions

Despite the repository name, the current backend includes an oral-exam agent and
a simple chat agent. The architecture is intentionally modular so another agent,
such as customer support, can be added under `backend/ExaminerAgent/code/agents/`.

## Project Structure

```text
.
├── backend/
│   └── ExaminerAgent/
│       ├── code/
│       │   ├── agents/          # chat/exam agents
│       │   ├── core/            # session, transport, STT/TTS nodes, pipeline
│       │   ├── services/        # database, LLM API, voice verification
│       │   └── server.py        # FastAPI entrypoint
│       ├── docker-compose.yml   # backend + vLLM stack
│       ├── Dockerfile
│       └── README.md
└── frontend/
    ├── src/app/page.tsx         # voice chat UI
    ├── public/static/           # audio worklets
    └── README.md
```

## How It Works

```text
Browser microphone
  -> frontend audio worklet
  -> backend WebSocket /ws
  -> STT node
  -> active agent
  -> LLM provider
  -> TTS node
  -> streamed audio response
  -> browser playback
```

For a backend file-by-file architecture map, see
[`backend/ExaminerAgent/code/ARCHITECTURE.md`](backend/ExaminerAgent/code/ARCHITECTURE.md).

## Quick Start

### 1. Start The Backend

The default backend stack runs FastAPI plus vLLM.

```bash
cd backend/ExaminerAgent
cp .env.example .env
docker compose up -d --build
```

Backend URLs:

- App: `http://localhost:8080`
- vLLM: `http://localhost:8000`

Check it:

```bash
curl http://localhost:8080/
docker compose logs -f app
```

### 2. Start The Frontend

In another terminal:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

The frontend defaults to:

```bash
NEXT_PUBLIC_VOICE_SERVER_URL=http://localhost:8080
```

## Runtime Modes

### Chat Mode

Connect to `/ws` without query params.

This uses:

- `backend/ExaminerAgent/code/agents/chat/agent.py`

### Exam Mode

Connect to `/ws` with one or more exam identifiers:

```text
/ws?user_id=...&exam_id=...&attempt_id=...
```

This uses:

- `backend/ExaminerAgent/code/agents/exam/agent.py`
- Supabase context from `services/database.py`

Exam mode requires:

```bash
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
```

## Configuration

Backend config is layered:

1. `backend/ExaminerAgent/code/config/global.yaml`
2. `backend/ExaminerAgent/code/agents/<agent>/config.yaml`
3. environment variables from `backend/ExaminerAgent/.env`

Frontend config:

```bash
NEXT_PUBLIC_VOICE_SERVER_URL=http://localhost:8080
```

## LLM Providers

| Provider | Use Case | Required Settings |
| --- | --- | --- |
| `vllm` | Default local/GPU stack | `LLM_PROVIDER=vllm`, `VLLM_BASE_URL=http://vllm:8000/v1` |
| `openai` | External API testing | `LLM_PROVIDER=openai`, `OPENAI_API_KEY=...`, `LLM_MODEL=...` |

## Development Notes

Backend docs:

- [`backend/ExaminerAgent/README.md`](backend/ExaminerAgent/README.md)
- [`backend/ExaminerAgent/code/ARCHITECTURE.md`](backend/ExaminerAgent/code/ARCHITECTURE.md)

Frontend docs:

- [`frontend/README.md`](frontend/README.md)

Useful checks:

```bash
# backend syntax
python3 -m compileall backend/ExaminerAgent/code

# frontend production build
cd frontend
npm run build
```

## Current Boundaries

- `core/` owns runtime flow: session, transport, pipeline, STT/TTS nodes.
- `agents/` owns agent behavior and prompts.
- `services/` owns external integrations: Supabase, LLM API, voice verification.
- `frontend/` owns browser capture/playback and transcript rendering.

Keep provider-specific STT/TTS logic in `core/nodes/`; do not duplicate it under
`services/`.
