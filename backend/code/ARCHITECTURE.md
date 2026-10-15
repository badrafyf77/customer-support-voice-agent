# Voice Agent Architecture Map

This map describes the important files under `code/`. Package `__init__.py` files
are omitted because they only mark packages or re-export names.

Type key:
- **Core**: required for the runtime path.
- **Support**: required by core or agents, but not an entrypoint itself.
- **Optional**: used only for a specific mode, feature, or future extension.

## Top Level

| File | Role | Imported / Called By | Depends On | Type | Possible Overlap |
| --- | --- | --- | --- | --- | --- |
| `server.py` | FastAPI entrypoint for HTTP endpoints and `/ws` sessions. | Uvicorn, Docker command, local `python server.py`. | `agents.chat.agent`, `agents.exam.agent`, `core.config`, `core.logsetup`, `core.session`, `services.database`, FastAPI. | Core | Owns HTTP routing only; session lifecycle belongs in `core/session.py`. |
| `system_prompt.txt` | Fallback generic system prompt for the speech pipeline. | Read by `core/pipeline.py` when an agent does not provide a prompt. | None. | Optional | Overlaps conceptually with `agents/exam/system_prompt.txt`; agent prompts should win for exam sessions. |

## Agents

| File | Role | Imported / Called By | Depends On | Type | Possible Overlap |
| --- | --- | --- | --- | --- | --- |
| `agents/base.py` | Defines the minimal `BaseAgent.run_turn(...)` contract. | `agents/chat/agent.py`, `agents/exam/agent.py`, `agents/__init__.py`. | `core.models`. | Core | Slight overlap with `core/brain.py` protocols; keep `base.py` as the concrete agent contract. |
| `agents/chat/agent.py` | Implements the simple non-exam chat agent. | `server.py`. | `agents.base`, `core.models`, stdlib locking/dataclasses. | Core | No overlap; this is the fallback agent when no exam context is provided. |
| `agents/chat/config.yaml` | Per-agent runtime config for chat sessions. | Loaded by `core.config.load_agent_config("chat")` from `server.py`. | `config/global.yaml` defaults and environment placeholders. | Support | Overrides `config/global.yaml`; keep only chat-specific differences here. |
| `agents/exam/agent.py` | Orchestrates oral exam planning, graph transitions, control payloads, finish/save behavior. | `server.py`, `agents/exam/__init__.py`; called by `core/session.py` through `BaseAgent.run_turn`. | LangGraph, `agents.base`, `agents.exam.prompts`, `core.brain`, `core.models`, `services.database`. | Core | Large file with some persistence calls; overlaps a little with `services/database.py` and should eventually delegate more save details. |
| `agents/exam/prompts.py` | Builds personalized exam system prompts and context summaries. | `agents/exam/agent.py`. | stdlib JSON/logging/regex. | Support | No runtime overlap; prompt text should stay here rather than in `agent.py`. |
| `agents/exam/tools.py` | Reserved boundary for future exam tools. | Not currently called. | None. | Optional | Currently overlaps with nothing; can be removed until real tools exist. |
| `agents/exam/config.yaml` | Per-agent runtime config for exam sessions. | Loaded by `core.config.load_agent_config("exam")` from `core/session.py` and `server.py`. | `config/global.yaml` defaults and environment placeholders. | Support | Overrides `config/global.yaml`; keep only exam-specific differences here. |
| `agents/exam/system_prompt.txt` | Static exam prompt asset retained with the exam agent. | Not currently imported by Python code. | None. | Optional | May overlap with `agents/exam/prompts.py`; remove if prompt builder fully replaces it. |

## Config

| File | Role | Imported / Called By | Depends On | Type | Possible Overlap |
| --- | --- | --- | --- | --- | --- |
| `config/global.yaml` | Shared default config for all voice agents. | Loaded by `core.config.load_agent_config`. | Environment placeholders such as `${LLM_PROVIDER}`. | Support | Overridden by `agents/*/config.yaml`; avoid duplicating identical values in agent configs. |

## Core

| File | Role | Imported / Called By | Depends On | Type | Possible Overlap |
| --- | --- | --- | --- | --- | --- |
| `core/brain.py` | Shared brain protocols and exam control delimiter. | `core/pipeline.py`, `agents/exam/agent.py`. | `core.models`, asyncio/typing. | Support | Some protocol overlap with `agents/base.py`; `agents/base.py` is the runtime contract, this file supports legacy/streaming shapes. |
| `core/colors.py` | ANSI color helper for log formatting. | `core/logsetup.py`, `core/session.py`, `core/pipeline.py`, `core/text_context.py`, `core/nodes/stt/faster_whisper.py`. | None. | Optional | Cosmetic only; can be removed if colored logs are replaced with plain logging. |
| `core/config.py` | Central config/env/YAML loading helpers. | `server.py`, `core/session.py`, `core/nodes/stt/faster_whisper.py`, `core/turndetect.py`, services. | `config/global.yaml`, agent config YAML, `os`, optional `yaml`, optional dotenv. | Core | Should be the only non-service place reading environment variables. |
| `core/logsetup.py` | Configures timestamped colored logging. | `server.py`, `core/session.py`. | `core.colors`, stdlib logging/time. | Support | Overlaps cosmetically with `core/colors.py`; both are logging concerns. |
| `core/models.py` | Shared data models and conversation-history normalization. | `agents/base.py`, agents, `core/brain.py`, `core/session.py`. | stdlib dataclasses/datetime/regex. | Core | Replaces the previous split session models/memory files. |
| `core/nodes/stt/faster_whisper.py` | STT node using RealtimeSTT/faster-whisper plus VAD and turn callbacks. | `core/transport/websocket.py`, `core/session.py` for config mutation. | `core.config`, `core.turndetect`, `core.text_similarity`, `core.colors`, RealtimeSTT, numpy. | Core | Single source of truth for STT/VAD behavior; should not be duplicated in `services/`. |
| `core/nodes/tts/factory.py` | Selects the legacy or SILMA TTS provider through lazy imports. | `core/pipeline.py`, typed preview. | Provider modules and shared config. | Core | Keeps provider choice out of worker orchestration. |
| `core/nodes/tts/realtime.py` | TTS node using RealtimeTTS with Kokoro/Coqui/Orpheus engines. | Provider factory. | RealtimeTTS, Hugging Face Hub, numpy, stdlib threading/queues. | Core | Existing English engine implementation. |
| `core/nodes/tts/silma.py` | HTTP synthesis, phrase streaming, bounded audio buffering, and cancellation. | Provider factory. | Internal SILMA service, `silma_text`, shared artifact pins. | Optional | Implements the same pipeline contract as legacy providers. |
| `core/nodes/tts/silma_runtime.py` | Cached custom model, Vocos, and selected reference inference. | `studio/silma_service.py`. | `silma_model`, torch/F5/Vocos in the isolated service environment. | Optional | GPU inference stays outside the voice backend process. |
| `core/pipeline.py` | Orchestrates LLM text generation, control-block stripping, and TTS worker threads. | `core/voice_runtime_pool.py`, `core/session.py`. | `core.nodes.tts.factory`, `services.llm`, `core.text_context`, `core.text_similarity`, `core.brain`. | Core | Provider-specific TTS logic remains delegated to the TTS node. |
| `core/session.py` | Owns app lifespan, WebSocket session tasks, transcript history, interrupts, and finish flow. | `server.py`. | FastAPI WebSocket, `core.config`, `core.models`, `core.pipeline`, `core.upsample_overlap`, `core.voice_runtime_pool`, `services.voice_verification`, `services.database`. | Core | Large file; overlaps a little with agent finish/save responsibilities. |
| `core/text_context.py` | Finds safe text chunks for quick TTS handoff. | `core/pipeline.py`. | `core.colors`, stdlib logging/typing. | Support | Related to `core/text_similarity.py`, but handles chunk boundaries rather than similarity. |
| `core/text_similarity.py` | Normalizes text and computes similarity for abort/de-dupe logic. | `core/pipeline.py`, `core/nodes/stt/faster_whisper.py`. | stdlib regex/difflib/logging. | Support | Related to STT normalization, but reusable enough to stay separate. |
| `core/transport/websocket.py` | Converts incoming PCM chunks to 16 kHz audio and feeds the STT node. | `core/voice_runtime_pool.py`, `core/transport/__init__.py`. | `core.nodes.stt.faster_whisper`, scipy, numpy, asyncio. | Core | Transport-specific; should not contain agent or TTS business logic. |
| `core/turndetect.py` | Uses a transformer model to estimate turn completion and silence timing. | `core/nodes/stt/faster_whisper.py`. | `core.config`, transformers, torch, threading/queue. | Core | Complements RealtimeSTT VAD; does not replace STT. |
| `core/upsample_overlap.py` | Encodes outgoing PCM audio chunks to base64 for the client. | `core/session.py`. | stdlib base64. | Support | Name suggests upsampling, but current behavior is encoding; could be renamed later. |
| `core/voice_runtime_pool.py` | Manages warmed reusable speech runtimes for concurrent sessions. | `core/session.py`. | `core.pipeline`, `core.transport.websocket`, asyncio. | Core | No overlap; this owns runtime leasing/reuse. |

## Services

| File | Role | Imported / Called By | Depends On | Type | Possible Overlap |
| --- | --- | --- | --- | --- | --- |
| `services/database.py` | Supabase access for profiles, exams, attempts, transcripts, and voice references. | `server.py`, `agents/exam/agent.py`, `core/session.py`. | `core.config`, Supabase client. | Core | Persistence details overlap slightly with exam finish logic in `agents/exam/agent.py`. |
| `services/atlas.py` | Atlas native message adaptation, bounded generation options, and streaming role-token suppression. | `services/llm.py`, Studio verification scripts. | stdlib only; pinned Atlas contract. | Support | Does not own session history or TTS scheduling. |
| `services/llm.py` | Provider wrapper for vLLM/OpenAI-compatible streaming generation. | `core/pipeline.py`. | OpenAI client, env vars, stdlib threading/time/uuid. | Core | No overlap; LLM API access stays here while orchestration stays in `core/pipeline.py`. |
| `services/speaker_verification.py` | Extracts and compares speaker embeddings. | `server.py`, `services/voice_verification.py`. | SpeechBrain/torch stack, numpy, `core.config`. | Optional | Supports voice verification only; separate from STT. |
| `services/voice_verification.py` | Samples student answer audio and records speaker-verification checks. | `core/session.py`. | `services.speaker_verification`, `core.config`, numpy/threading. | Optional | Works with `services/database.py` for persistence, but owns verification decisions. |

## Main Runtime Flow

1. The client connects to `server.py` at `/ws`.
2. `server.py` loads exam context through `services/database.py` when `user_id`, `exam_id`, or `attempt_id` are present.
3. `server.py` builds either `ExamAgentBrain` or `ChatAgentBrain`, loads agent config with `core/config.py`, then calls `core/session.py::run_session`.
4. `core/session.py` acquires a warmed `VoiceRuntime` from `core/voice_runtime_pool.py`.
5. `VoiceRuntime` contains:
   - `core/transport/websocket.py::AudioInputProcessor`
   - `core/pipeline.py::SpeechPipelineManager`
6. Incoming audio bytes go to `AudioInputProcessor`, which resamples them and feeds `core/nodes/stt/faster_whisper.py`.
7. The STT node emits partial, potential-final, and final transcript callbacks into `core/session.py`.
8. On a final user turn, `core/session.py` appends the user message, asks the active agent via `BaseAgent.run_turn(...)`, and receives an `AgentResult`.
9. `core/pipeline.py` sends the agent prompt/history to `services/llm.py`, strips any exam control block, and streams spoken text to the TTS provider selected by `core/nodes/tts/factory.py`.
10. The TTS node produces audio chunks; `core/session.py` base64-encodes them with `core/upsample_overlap.py` and sends `tts_chunk` messages back over the WebSocket.
11. When the assistant turn finishes, `core/session.py` sends final text events, updates conversation history, and lets the agent apply any control transition.

## Darija typed chat (phase 3)

`studio/chat_preview.py` adapts typed input to the same `SpeechPipelineManager`.
The Darija chat agent owns the spoken prompt; `services/atlas.py` folds it into
native user/assistant messages only at the LLM request boundary. vLLM and SILMA
remain independent loopback services. The existing quick/final workers stream
SILMA PCM through the shared preview and unchanged frontend playback worklet.
Phase 4 passes per-instance ASR/turn configuration through the runtime manager
and audio transport. Darija recognition shares the verified main model for
partial/final text. `core/darija_turn.py` applies the saved calibration and syntax
contract; `core/turndetect.py` feeds its score into the existing dynamic timing
formula. Reset epochs invalidate pending old turn decisions. The microphone path
is enabled. Phase 5 adds scoped delivery of generated text/PCM, final-STT turn
commitment, VAD barge-in during synthesis, explicit model failure handling and
shielded session cleanup. Stopped/unsafe runtimes retire instead of being reused.
The frontend keeps the existing wire/worklet formats and adds automatic text
direction plus stale-socket/generation guards. Live Studio acceptance is pending.
