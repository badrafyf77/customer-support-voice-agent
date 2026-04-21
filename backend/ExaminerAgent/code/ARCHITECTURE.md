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
- `core/session.py` owns the WebSocket session lifecycle.
- `core/models.py` owns small shared data objects and conversation history normalization.
- `core/nodes/` owns the active STT/TTS runtime implementations. VAD is currently
  configured inside the STT node via RealtimeSTT and turn detection lives in
  `core/turndetect.py`.

## `services/`

Shared external integrations. This layer owns Supabase, LLM API access, speaker
verification, and voice verification integrations. STT/TTS runtime logic belongs
under `core/nodes/`.

Rules:
- `services/` must not import from `agents/`.
- Environment access belongs in `services/llm.py` or `core/config.py`.
- Service modules are reusable by any agent.

## `agents/`

Agent-specific product behavior. Each folder is self-contained and may define its
own graph, prompts, tools, and config.

Every runtime agent implements `BaseAgent.run_turn(text, session) -> AgentResult`
from `agents/base.py`. This keeps the voice runtime independent from whether the
agent uses LangGraph, a direct LLM call, or a custom orchestrator.

The current exam agent lives in `agents/exam/`:
- `agent.py`: LangGraph exam controller and `build_exam_agent(context)`.
- `prompts.py`: exam system prompt builder.
- `tools.py`: reserved home for exam graph tools.
- `config.yaml`: model, voice, STT, and language settings.

Adding another voice agent should mean adding a new `agents/<name>/` folder and
wiring the server entry point to build that agent. The VAD -> STT -> LLM -> TTS
pipeline should remain unchanged.

## `config/`

`config/global.yaml` provides shared defaults. `agents/<name>/config.yaml`
overrides those defaults, and top-level settings can be overridden with
environment variables such as `VOICE_AGENT_LLM_PROVIDER` or `EXAM_LLM_PROVIDER`.
