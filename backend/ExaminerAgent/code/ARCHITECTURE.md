# Voice Agent Architecture

The runtime is split into three layers:

## `core/`

Shared voice pipeline infrastructure. This layer owns WebSocket session lifecycle,
runtime pooling, audio input, VAD/STT callbacks, LLM/TTS streaming orchestration,
and generic brain interfaces.

Rules:
- `core/` must not import from `agents/`.
- `core/` may import from `services/`.
- `core/config.py` is the only core module that reads environment variables.
- `core/voice_runtime_pool.py` preserves warmed runtime concurrency behavior.

## `services/`

Shared external integrations. This layer owns Supabase, STT, TTS, LLM, and voice
verification integrations.

Rules:
- `services/` must not import from `agents/`.
- Environment access belongs in `services/llm.py` or `core/config.py`.
- Service modules are reusable by any agent.

## `agents/`

Agent-specific product behavior. Each folder is self-contained and may define its
own graph, prompts, tools, and config.

The current exam agent lives in `agents/exam/`:
- `agent.py`: LangGraph exam controller and `build_exam_agent(context)`.
- `prompts.py`: exam system prompt builder.
- `tools.py`: reserved home for exam graph tools.
- `config.yaml`: model, voice, STT, and language settings.

Adding another voice agent should mean adding a new `agents/<name>/` folder and
wiring the server entry point to build that agent brain. The VAD -> STT -> LLM ->
TTS pipeline should remain unchanged.
