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
| `server.py` | FastAPI entrypoint for HTTP endpoints and `/ws` sessions. | Uvicorn, Docker command, local `python server.py`. | `agents.support.agent`, `core.config`, `core.logsetup`, `core.session`, FastAPI. | Core | Owns HTTP routing only; session lifecycle belongs in `core/session.py`. |
| `studio.py` | Exposes the two agent graphs to LangGraph Studio (`langgraph dev`, configured in `../langgraph.json`). | `langgraph dev`. | `agents.support.supervisor`. | Optional | Debugging only. |
| `system_prompt.txt` | Fallback generic system prompt for the speech pipeline. | Read by `core/pipeline.py` when an agent does not provide a prompt. | None. | Optional | Agent prompts win when an agent provides one. |

## Agents

| File | Role | Imported / Called By | Depends On | Type | Possible Overlap |
| --- | --- | --- | --- | --- | --- |
| `agents/base.py` | Defines the `BaseAgent` contract: `run_turn(...)` plus default `idle_turn(...)`, `close_session(...)`, `finish_session(...)` / `save_progress(...)` hooks. | `agents/support/agent.py`, `agents/__init__.py`, `core/session.py`. | `core.models`. | Core | No overlap; this is the only agent contract. |
| `agents/graph.py` | Shared LangGraph nodes: `model` <-> `tools` with the tool-call limit, plus `TraceHandler` (model calls into our trace file). | `agents/support/supervisor.py`, `agents/orders/agent.py`. | LangGraph, LangChain, `core.trace`. | Core | The only place that runs tool calls for an agent. |
| `agents/models.py` | Builds the LangChain `ChatOpenAI` of an agent from its config (Responses API, reasoning effort). | Both agents. | `langchain_openai`. | Support | `services/llm.py` is only used by the speech pipeline now. |
| `agents/support/agent.py` | `SupportAgent`: returns each turn as a text stream for the pipeline; gives background results and ends the call from `idle_turn`. | `server.py`. | `agents.support.supervisor`, `core.models`. | Core | Thin adapter; behaviour lives in `supervisor.py`. |
| `agents/support/supervisor.py` | The supervisor LangGraph graph (`identity -> model <-> tools`), background orders jobs, call limits. No audio. | `agents/support/agent.py`, `tests/text_runner.py`. | `agents.support.identity`, `agents.orders.agent`, `agents.tool_loop`, `shop.tools`, `core.trace`. | Core | The single "agent brain" used by voice and text tests. |
| `agents/support/identity.py` | Steps 1 and 2 in plain code: phone number lookup and name confirmation. | `agents/support/supervisor.py`. | `core.trace`. | Core | No AI here, on purpose. |
| `agents/support/prompt.md`, `config.yaml` | Supervisor instructions; model, limits and speech settings. | `supervisor.py`; `load_agent_config("support")`. | `config/global.yaml`. | Support | Overrides `config/global.yaml`. |
| `agents/orders/agent.py` | Orders specialist LangGraph graph: runs a job and returns `done` / `needs_info` / `cannot` (structured output). | `agents/support/supervisor.py`. | `agents.graph`, `agents.models`, `shop.tools`. | Core | Never talks to the customer. |
| `agents/orders/prompt.md`, `config.yaml` | Orders agent instructions; model and tool-call limit. | `agents/orders/agent.py`; `load_agent_config("orders")`. | `config/global.yaml`. | Support | Overrides `config/global.yaml`. |

## Shop

| File | Role | Imported / Called By | Depends On | Type | Possible Overlap |
| --- | --- | --- | --- | --- | --- |
| `shop/schema.sql`, `shop/seed.py` | Fake ShopEasy database: tables and seed data with dates counted from today. | `shop/db.py` (builds a missing database), `python -m shop.seed`. | SQLite. | Support | Test data only; not a real shop. |
| `shop/db.py` | Small SQLite helpers; one connection per call so threads are safe. | `shop/tools.py`, agents. | `core.config`. | Support | No overlap. |
| `shop/tools.py` | The tools: plain functions, their descriptions for the AI, and `run_tool` (tracing, errors as data, verified customer from code). | Agents. | `shop.db`, `core.trace`. | Core | Will move behind an MCP server in Phase 3. |

## Config

| File | Role | Imported / Called By | Depends On | Type | Possible Overlap |
| --- | --- | --- | --- | --- | --- |
| `config/global.yaml` | Shared default config for all voice agents. | Loaded by `core.config.load_agent_config`. | Environment placeholders such as `${LLM_PROVIDER}`. | Support | Overridden by `agents/*/config.yaml`; avoid duplicating identical values in agent configs. |

## Core

| File | Role | Imported / Called By | Depends On | Type | Possible Overlap |
| --- | --- | --- | --- | --- | --- |
| `core/colors.py` | ANSI color helper for log formatting. | `core/logsetup.py`, `core/session.py`, `core/pipeline.py`, `core/text_context.py`, `core/nodes/stt/faster_whisper.py`. | None. | Optional | Cosmetic only; can be removed if colored logs are replaced with plain logging. |
| `core/config.py` | Central config/env/YAML loading helpers. | `server.py`, `core/session.py`, `core/nodes/stt/faster_whisper.py`, `core/turndetect.py`. | `config/global.yaml`, agent config YAML, `os`, optional `yaml`, optional dotenv. | Core | Should be the only non-service place reading environment variables. |
| `core/logsetup.py` | Configures timestamped colored logging. | `server.py`, `core/session.py`. | `core.colors`, stdlib logging/time. | Support | Overlaps cosmetically with `core/colors.py`; both are logging concerns. |
| `core/models.py` | Shared data models (`SessionContext`, `AgentResult`) and conversation-history normalization. | `agents/base.py`, agents, `core/session.py`. | stdlib dataclasses/datetime/regex. | Core | Replaces the previous split session models/memory files. |
| `core/nodes/stt/faster_whisper.py` | STT node using RealtimeSTT/faster-whisper plus VAD and turn callbacks. | `core/transport/websocket.py`, `core/session.py` for config mutation. | `core.config`, `core.turndetect`, `core.text_similarity`, `core.colors`, RealtimeSTT, numpy. | Core | Single source of truth for STT/VAD behavior; should not be duplicated in `services/`. |
| `core/nodes/tts/realtime.py` | TTS node using RealtimeTTS with Kokoro/Coqui/Orpheus engines. | `core/pipeline.py`. | RealtimeTTS, Hugging Face Hub, numpy, stdlib threading/queues. | Core | Single source of truth for TTS behavior; should not be duplicated in `services/`. |
| `core/pipeline.py` | Orchestrates LLM text generation and TTS worker threads. | `core/voice_runtime_pool.py`, `core/session.py`. | `core.nodes.tts.realtime`, `services.llm`, `core.text_context`, `core.text_similarity`. | Core | Still contains a lot of worker detail; provider-specific TTS logic is delegated to the TTS node. |
| `core/session.py` | Owns app lifespan, WebSocket session tasks, transcript history, interrupts, and finish flow. | `server.py`. | FastAPI WebSocket, `core.config`, `core.models`, `core.upsample_overlap`, `core.voice_runtime_pool`. | Core | Large file; delegates finish/save details to the agent hooks. |
| `core/trace.py` | Writes one JSON-lines trace file per call, with `parent_id` links across agents and threads. | Agents, tools, tests. | `core.config`. | Core | Separate from `core/logsetup.py`: logs are for developers, traces are the call record. |
| `core/text_context.py` | Finds safe text chunks for quick TTS handoff. | `core/pipeline.py`. | `core.colors`, stdlib logging/typing. | Support | Related to `core/text_similarity.py`, but handles chunk boundaries rather than similarity. |
| `core/text_similarity.py` | Normalizes text and computes similarity for abort/de-dupe logic. | `core/pipeline.py`, `core/nodes/stt/faster_whisper.py`. | stdlib regex/difflib/logging. | Support | Related to STT normalization, but reusable enough to stay separate. |
| `core/transport/websocket.py` | Converts incoming PCM chunks to 16 kHz audio and feeds the STT node. | `core/voice_runtime_pool.py`, `core/transport/__init__.py`. | `core.nodes.stt.faster_whisper`, scipy, numpy, asyncio. | Core | Transport-specific; should not contain agent or TTS business logic. |
| `core/turndetect.py` | Uses a transformer model to estimate turn completion and silence timing. | `core/nodes/stt/faster_whisper.py`. | `core.config`, transformers, torch, threading/queue. | Core | Complements RealtimeSTT VAD; does not replace STT. |
| `core/upsample_overlap.py` | Encodes outgoing PCM audio chunks to base64 for the client. | `core/session.py`. | stdlib base64. | Support | Name suggests upsampling, but current behavior is encoding; could be renamed later. |
| `core/voice_runtime_pool.py` | Manages warmed reusable speech runtimes for concurrent sessions. | `core/session.py`. | `core.pipeline`, `core.transport.websocket`, asyncio. | Core | No overlap; this owns runtime leasing/reuse. |

## Services

| File | Role | Imported / Called By | Depends On | Type | Possible Overlap |
| --- | --- | --- | --- | --- | --- |
| `services/llm.py` | Provider wrapper for vLLM/OpenAI-compatible streaming generation, used by the speech pipeline (prewarm, latency check, plain `generate` turns). | `core/pipeline.py`. | OpenAI client, env vars, stdlib threading/time/uuid. | Core | No overlap; LLM API access stays here while orchestration stays in the agents and `core/pipeline.py`. |

## Main Runtime Flow

1. The client connects to `server.py` at `/ws`.
2. `server.py` builds the `SupportAgent`, loads its config with `core/config.py`, then calls `core/session.py::run_session`.
3. `core/session.py` acquires a warmed `VoiceRuntime` from `core/voice_runtime_pool.py`.
4. `VoiceRuntime` contains:
   - `core/transport/websocket.py::AudioInputProcessor`
   - `core/pipeline.py::SpeechPipelineManager`
5. Incoming audio bytes go to `AudioInputProcessor`, which resamples them and feeds `core/nodes/stt/faster_whisper.py`.
6. The STT node emits partial, potential-final, and final transcript callbacks into `core/session.py`.
7. On a final user turn, `core/session.py` appends the user message and calls `BaseAgent.run_turn(text, session)`, which returns an `AgentResult`.
8. For a `stream` result (what `SupportAgent` returns), `core/pipeline.py` speaks the text the supervisor's generator yields; the supervisor runs the identity steps, model calls and tools inside it. For a `generate` result, the pipeline calls `services/llm.py` itself. A `finish` result ends the session through the agent's `finish_session(...)` hook.
   While nobody is speaking, `core/session.py::watch_idle_agent_turns` calls `idle_turn(...)` so the agent can speak background results, the call-limit warning, or end the call after a transfer.
9. The TTS node produces audio chunks; `core/session.py` base64-encodes them with `core/upsample_overlap.py` and sends `tts_chunk` messages back over the WebSocket.
10. When the assistant turn finishes, `core/session.py` sends the final text event and updates conversation history.
