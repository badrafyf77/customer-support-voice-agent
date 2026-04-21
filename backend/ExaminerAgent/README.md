# examiner-agent Backend

This service is the realtime oral-exam engine for Veridex. It handles live audio input, speech-to-text, turn detection, exam-aware LLM generation, text-to-speech playback, transcript persistence, and oral-attempt submission.

It is not a generic chatbot backend anymore. In this project, it is the oral examination runtime used by the frontend exam room.

## What This Backend Does

The backend is responsible for:

- receiving microphone audio over WebSocket
- transcribing the student in realtime
- deciding when a student turn has ended
- generating the next Veridex examiner turn
- speaking that response back with streaming TTS
- loading exam, rubric, attempt, and profile context from Supabase
- orchestrating oral exam flow with LangGraph
- finishing oral attempts and persisting transcript metadata

## Oral Exam Runtime Architecture

```text
Student audio
  -> WebSocket
  -> Audio input processor
  -> Realtime transcription
  -> Turn detection
  -> LangGraph oral exam controller
  -> LLM provider
  -> Streaming text output
  -> TTS synthesis
  -> Audio streamed back to the frontend
  -> Transcript + attempt metadata saved to Supabase
```

### Main components

- `code/server.py`: FastAPI app, WebSocket session lifecycle, exam finish flow
- `code/audio_in.py`: audio ingestion and STT feed pipeline
- `code/transcribe.py`: transcription processor
- `code/speech_pipeline_manager.py`: LLM + TTS orchestration
- `code/exam_graph.py`: LangGraph exam controller for question pacing and automatic closing
- `code/user_context.py`: personalized examiner system prompt builder
- `code/database.py`: Supabase exam/profile/attempt access
- `code/voice_runtime_pool.py`: warmed runtime pooling for concurrency management

## How It Works In Veridex

For each oral exam session:

1. The frontend connects to `/ws` with `user_id`, `exam_id`, and `attempt_id`.
2. The backend loads the student profile, exam metadata, rubric, and attempt transcript.
3. A personalized examiner prompt is built from that context.
4. The LangGraph controller decides when Veridex should ask the first question, ask the next question, or close the exam.
5. Student speech is transcribed in realtime.
6. Veridex generates one examiner turn at a time and streams it back as audio.
7. When the target number of questions is completed, the backend closes the oral exam automatically.
8. The attempt is submitted and persisted.

## Supported LLM Provider Modes

| Provider | Setup     | Best Use Case                | Notes                       |
| -------- | --------- | ---------------------------- | --------------------------- |
| `vllm`   | local GPU | best default for performance | recommended compose default |
| `openai` | API key   | quick external testing       | simple setup                |

## Quick Start

### Prerequisites

- Docker Engine
- Docker Compose plugin
- NVIDIA GPU drivers and `nvidia-smi` if you want GPU-backed local inference
- NVIDIA Container Toolkit for GPU Docker access

### Default stack: vLLM + examiner

From this directory:

```bash
cp .env.example .env
docker compose up -d --build
```

Default ports:

- app: `http://162.243.59.37:8080`
- vLLM: `http://162.243.59.37:8000`

Useful checks:

```bash
docker compose logs -f vllm
docker compose logs -f app
curl http://162.243.59.37:8080/
```

The first startup can take a long time because the image builds and model assets are downloaded.

## Compose files

| File                      | Stack           | App Port | When To Use It                                     |
| ------------------------- | --------------- | -------- | -------------------------------------------------- |
| `docker-compose.yml`      | examiner + vLLM | `8080`   | recommended default                                |
| `docker-compose.vllm.yml` | examiner + vLLM | `8080`   | older retained variant with fewer runtime settings |

## Configuration

Copy [`.env.example`](./.env.example) to `.env` and fill in what applies to your setup.

### Core runtime variables

```bash
LLM_PROVIDER=vllm
LLM_MODEL=Qwen/Qwen2.5-1.5B-Instruct
VLLM_BASE_URL=http://vllm:8000/v1

LOG_LEVEL=INFO
MAX_AUDIO_QUEUE_SIZE=50
VOICE_RUNTIME_MIN_WARM=1
VOICE_RUNTIME_MAX_CONCURRENT=1
VOICE_RUNTIME_IDLE_TTL_SECONDS=300
VOICE_RUNTIME_ACQUIRE_TIMEOUT_SECONDS=30
VLLM_STARTUP_TIMEOUT_SECONDS=180
VLLM_HEALTHCHECK_INTERVAL_SECONDS=2

STT_MODEL=medium.en
STT_REALTIME_MODEL=small.en
STT_USE_MAIN_MODEL_FOR_REALTIME=true
TURN_DETECTION_DEVICE=cpu
```

### Supabase integration

These enable exam-aware oral sessions:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

They are used for:

- loading profile context
- loading exam and rubric metadata
- loading and updating attempt transcripts
- persisting oral-attempt submission metadata

### OpenAI Provider

- `OPENAI_API_KEY` (required only when `LLM_PROVIDER=openai`)
- Set `LLM_PROVIDER=openai` in `.env` and choose an OpenAI model in `LLM_MODEL` (for example `gpt-5`)

## WebSocket API

Main endpoint:

- `/ws`
- `/voice-reference`

Typical query parameters:

- `user_id`
- `exam_id`
- `attempt_id`

The frontend oral room uses these to bind the live session to an exam attempt.

Evaluation handoff is not triggered by `examiner-agent` itself anymore. The oral attempt is submitted here, and any evaluator workflow should be triggered by the frontend or another backend service after submission.

## Notes For Frontend Integration

- If you use the default vLLM compose stack, point the frontend to `ws://162.243.59.37:8080`
- If you use `LLM_PROVIDER=openai` with the same compose stack, the frontend URL stays `ws://162.243.59.37:8080`

## Development Notes

Run locally without Docker:

```bash
cd code
python server.py
```

This is useful for iteration, but the Docker setup is the more representative runtime for the full local stack.

## Additional Docs

- [Project README](../../README.md)
- [Frontend README](../../frontend/README.md)
