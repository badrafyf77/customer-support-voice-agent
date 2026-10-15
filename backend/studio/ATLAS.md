# Phase 3 — Atlas streaming chat

Atlas is connected through `services/llm.py`, the existing OpenAI-compatible client,
and the existing quick-answer/remaining-answer workers. SILMA uses the user's
selected **voice1 + main weights**. [Phase 4 Darija STT and turn detection](STT.md)
now enable microphone startup; live Studio validation remains deferred.

## Request and generation contract

The full model and tokenizer come from MBZUAI-Paris/Atlas-Chat-2B revision
`a6244a4c50bc32b65c6c8dc4dc1dab218b580088`. The launcher verifies the preparation
receipt, metadata hashes, native template, generation prompt, and token IDs before
starting vLLM. It does not override the native template or register an LLM adapter.

The native Gemma template rejects system roles and requires alternating turns.
`services/atlas.py` copies message content, folds assistant instructions into the
first user message, and coalesces adjacent unanswered/interrupted user turns at
the request boundary. It does not change stored transcripts or invent assistant
turns. A leading assistant, non-text message, or unsupported tool role fails
explicitly. No Arabizi digit conversion or identifier rewriting is applied.

The chat agent supplies spoken-Darija instructions: Arabic script, concise natural
replies, clarification when uncertain, preserved foreign names and factual IDs,
and no unsolicited French/English. The English chat prompt remains available.

Both pinned EOS IDs are preserved: `<eos>` = 1 and `<end_of_turn>` = 107.
Requests set `stop_token_ids=[1,107]`, `ignore_eos=false`, and
`skip_special_tokens=true`. A small streaming filter also withholds split model
role markers and stops before their following role text. It does not buffer the
whole answer. The client caps every Atlas response at 256 tokens (or a smaller
requested cap) and permits one response per turn. Extra request bodies cannot
replace messages, the native template, EOS behavior, or token caps.

vLLM runs BF16, one scheduled sequence, a 4096-token total context, and a server
response cap of 256 via `--override-generation-config`. Context overflow is a
visible API failure; history is not silently truncated. The response cap can
truncate a long answer. The client uses the model's ordinary streaming route;
no per-token HTTP/tokenizer request is introduced.

Cancellation registers requests before waiting for headers and invalidates
unstarted generators. A stream that opens after Stop is closed without emitting
text. Atlas requests do not automatically retry, so canceled requests cannot be
redispatched by a retry. The existing 30-second HTTP timeout still bounds a
pending header wait; a transport without response headers cannot yet be closed
as a stream. Active streams close outside the registry lock, before pipeline
worker waits, including when the remaining-answer worker owns the iterator.
SILMA invalidates audio before those waits. Service errors remain visible.

## Commands for the later Studio run

Use the persistent paths and isolated environments from [README.md](README.md).
From the repository root, prepare only the Atlas artifacts if the other roles
are already prepared:

```bash
"$DARIJA_STATE_ROOT/backend/bin/python" backend/studio/prepare_models.py \
  --root "$DARIJA_MODEL_ROOT" --roles llm
export VLLM_GPU_MEMORY_UTILIZATION=0.40
bash backend/studio/start_vllm.sh
```

The memory budget is a provisional starting point; combined GPU tuning remains
phase 6. vLLM binds to loopback port 8001. In a separate terminal, start SILMA
using [SILMA.md](SILMA.md), then launch typed chat:

```bash
export VLLM_BASE_URL=http://127.0.0.1:8001/v1
export SILMA_TTS_BASE_URL=http://127.0.0.1:8002
"$DARIJA_STATE_ROOT/backend/bin/python" -m uvicorn chat_preview:app \
  --app-dir backend/studio --host 127.0.0.1 --port 8080
```

The preview constructs the actual `SpeechPipelineManager`; it adds only typed
input, session history, audio queue forwarding, and scoped text events. One
browser can lease it at a time. Stop/replacement invalidates old text and PCM;
new turns wait for worker cleanup. Reconnecting resets history and the Darija
prompt. Failed generation clears playback and displays an error. Interrupted
turns retain the user's message but omit incomplete assistant text from history.
The shared preview still supports phase 2's speech-only mode.

Forward only the browser preview port using the Studio's actual SSH alias:

```bash
ssh -N -o ExitOnForwardFailure=yes -L 8080:127.0.0.1:8080 STUDIO_SSH_ALIAS
```

Open http://localhost:8080. Type multiple turns, listen for quick speech before
response completion, stop during synthesis/playback, then send another turn.
The preview uses the exact existing 24 kHz playback worklet. Each diffusion
phrase still completes before it produces audio; this integration does not
claim incremental diffusion or measured first-audio latency.

For the text/cancellation report, with vLLM running:

```bash
"$DARIJA_STATE_ROOT/backend/bin/python" backend/studio/smoke_atlas.py \
  --output "$DARIJA_STATE_ROOT/atlas-conversations.json"
```

[atlas_cases.json](atlas_cases.json) covers history, uncertainty, negation, names,
phone/order IDs, decimals, foreign input terms, acknowledgments, and longer
replies. Review the actual answers for Darija quality and factual preservation;
passing transport checks does not establish language quality. The text report
records client stream closure; audible cancellation and GPU release need the
later live run.

## Local verification

`verify_atlas.py` was run offline with Transformers 4.51.3 and Jinja2 3.1.6 against
the downloaded pinned tokenizer. No weights loaded. The saved evidence is
[atlas-tokenizer-verification.json](../../docs/darija/atlas-tokenizer-verification.json).

```bash
uv run --no-project --with fastapi==0.135.4 --with starlette==0.52.1 \
  --with pydantic==2.10.6 --with httpx==0.28.1 --with PyYAML==6.0.2 \
  --with openai==3.29.0 --with numpy==1.26.4 python -m unittest discover -s backend/tests -v
node backend/tests/test_preview_player.js
```

The phase 3 checks passed; the expanded phase 4 suite is documented in [STT.md](STT.md). Tests exercise the locked OpenAI SDK over local SSE, request formatting and EOS
caps, split marker suppression, cancellation before dispatch/during header wait/
during an active read, direct pipeline interruption, ordered quick/final output,
real SILMA HTTP/provider/preview contracts with deterministic fake PCM, failure
cleanup, reconnect, and browser rejection of stale audio/text. All live Studio
inference, listening, latency, and memory validation remain deferred by the user.
