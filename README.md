# Customer Support Voice Agent

Realtime browser-to-backend voice-agent project with:

- a **FastAPI voice backend** in `backend`
- a **Next.js voice chat frontend** in `frontend`
- support for simple voice chat and Supabase-backed oral exam sessions

The backend includes an oral-exam agent and a simple chat agent. The architecture
is intentionally modular so another agent, such as customer support, can be added
under `backend/code/agents/`.

On the Darija branch, use [the Lightning Docker Compose guide](backend/studio/DOCKER.md):
put the token/settings in `backend/.env`, run Compose on Studio, expose port 8080,
and put its HTTPS URL in `frontend/.env.local` on your local computer.

## Project Structure

```text
.
├── backend/
│   ├── code/
│   │   ├── agents/              # chat/exam agents
│   │   ├── core/                # session, transport, STT/TTS nodes, pipeline
│   │   ├── services/            # database, LLM API, voice verification
│   │   └── server.py            # FastAPI entrypoint
│   ├── docker-compose.yml       # Darija preparation + Atlas + SILMA + backend
│   ├── Dockerfile.darija        # three pinned CUDA/Python targets
│   ├── Dockerfile
│   └── README.md
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
[`backend/code/ARCHITECTURE.md`](backend/code/ARCHITECTURE.md).

## Quick Start

### 1. Start The Backend

The default stack runs Darija chat with pinned ASR/turn, Atlas and SILMA models.
Compose downloads the pinned Whisper base and trained Darija adapter from HF,
merges them, and prepares verified ready-to-run CT2 files automatically. See the
[guide](backend/studio/DOCKER.md#2-automatic-ready-to-run-asr-preparation-from-hugging-face).

```bash
cd backend
cp -n .env.example .env
# Edit HF_TOKEN in .env; ASR preparation is automatic.
docker compose up -d --build
```

Backend URLs:

- App: `http://localhost:8080`
- vLLM and SILMA stay internal; only the backend port is published.

Check it:

```bash
curl http://localhost:8080/
docker compose logs -f app
```

### 2. Start The Frontend

Expose backend port 8080 in Lightning's Ports panel. In your local checkout:

```bash
cd frontend
cp -n .env.example .env.local
# Set NEXT_PUBLIC_VOICE_SERVER_URL to the exposed Lightning HTTPS base URL.
npm ci
npm run dev
```

Open:

```text
http://localhost:3000
```

For the remote Studio backend, use:

```bash
NEXT_PUBLIC_VOICE_SERVER_URL=https://YOUR-LIGHTNING-BACKEND-URL
```

## Runtime Modes

### Chat Mode

Connect to `/ws` without query params.

This uses:

- `backend/code/agents/chat/agent.py`

### Exam Mode

Exam mode belongs to the English configuration. The default Darija Compose stack
supports general chat only and rejects exam query parameters.

Connect to `/ws` with one or more exam identifiers:

```text
/ws?user_id=...&exam_id=...&attempt_id=...
```

This uses:

- `backend/code/agents/exam/agent.py`
- Supabase context from `services/database.py`

Exam mode requires:

```bash
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
```

## Configuration

Backend config is layered:

1. `backend/code/config/global.yaml`
2. `backend/code/agents/<agent>/config.yaml`
3. environment variables from `backend/.env`

Frontend config:

```bash
NEXT_PUBLIC_VOICE_SERVER_URL=http://localhost:8080
```

## LLM Providers

| Provider | Use Case | Required Settings |
| --- | --- | --- |
| `vllm` | Default Darija/GPU stack | Atlas configured by Compose at `http://vllm:8001/v1` |
| `openai` | External API testing | `LLM_PROVIDER=openai`, `OPENAI_API_KEY=...`, `LLM_MODEL=...` |

## Development Notes

Backend docs:

- [`backend/README.md`](backend/README.md)
- [`backend/code/ARCHITECTURE.md`](backend/code/ARCHITECTURE.md)

Frontend docs:

- [`frontend/README.md`](frontend/README.md)

Useful checks:

```bash
# backend syntax
python3 -m compileall backend/code

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
