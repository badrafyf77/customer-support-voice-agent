# Phase 2 — SILMA speech

The user selected **voice1 + main weights** on 13 October 2026.
[voices/selection.json](voices/selection.json) stores that default. Both the
backend factory and the service read it. Explicit SILMA_VOICE_ID and
SILMA_CHECKPOINT_VARIANT values can override it; startup rejects a backend/service
mismatch.

The selected reference is spk0552 / train-00026-of-00039-01293, about 8.619 seconds.
The original mono 24 kHz waveform and Darija transcript are bundled under voices/
with SHA-256 hashes and source metadata. No transcript was diacritized or rewritten.

## Integration

The existing quick-answer and remaining-answer workers now use create_tts_provider.
Kokoro, Coqui, and Orpheus keep their existing behavior and arguments. SILMA implements
the same text/generator synthesis, stop, reset, shutdown, first-audio callback, and
measured latency contract. Lazy imports keep English TTS dependencies out of the
isolated SILMA process.

The service caches the pinned custom model, selected main/EMA weights, Vocos,
reference waveform, and reference transcript at startup, then warms one phrase.
No phrase downloads weights or reloads those resources. Generation uses 32 steps,
CFG 2, and sway -1. Duration uses reference frames per UTF-8 text byte, following
the inspected F5/SILMA implementation, including F5's 0.3 speed adjustment for very
short text. The reference plus generated phrase is limited to 30 seconds.
Long input is split rather than truncated.

Arabic punctuation is recognized in the first-phrase detector. SILMA also protects
decimals and names containing periods at that boundary; the English providers retain
their prior detector behavior. The remaining text generator is consumed one phrase
at a time, with bounded buffering and a flushed tail. Transcript text stays in the
existing pipeline, separate from the phrases supplied to synthesis. No automatic
diacritization, Arabizi digit replacement, or number rewriting is applied.

Each diffusion phrase completes before its PCM response becomes available.
The provider slices it into 100 ms playback packets and permits at most 20 pending
packets (two seconds) in the pipeline queue, with backpressure rather than dropped
tails. The next phrase can synthesize while prior audio plays. Packet slicing does
not make diffusion incremental or remove its first-audio delay.

## Cancellation and API

The service permits one active GPU pass and returns busy while a canceled pass
finishes internally. Its GPU slot is released by the actual worker, including
when the HTTP task disconnects. Cancellation tombstones cover requests canceled
before dispatch. They are bounded and retained for 300 seconds; client request
timeouts are limited to 120 seconds.

Quick/final calls share a session-scoped generation ID. Stop invalidates the provider
epoch before the pipeline waits on workers. The provider suppresses late responses,
stops submitting phrases, and rejects audio from prior sessions. The typed preview
also checks browser request IDs, including after immediate Stop or replacement.

| Route | Contract |
| --- | --- |
| GET /health | Readiness, model/vocoder revisions, reference hash, selected voice/variant, steps, sample rate, channels, phrase byte limit, measured warmup latency. |
| POST /synthesize | JSON text + generation_id; raw mono 24 kHz little-endian signed PCM16 with generation/format/rate/channel headers. |
| POST /cancel | JSON generation_id; invalidates active and not-yet-dispatched work. |

Canceled requests return 409 / cancelled; active-pass contention returns 409 / busy.
The provider retries busy requests within its deadline while remaining interruptible.
Invalid text returns 422; model failures return 500. No fallback model is used.
The provider verifies the pinned model/vocoder, selected reference and voice, sampling
steps, and response audio contract before queuing audio.

## Studio setup — live validation deferred by the user

Use the phase 1 persistent paths and runtime HF_TOKEN access. From the repository root:

```bash
uv pip sync --python "$DARIJA_STATE_ROOT/silma/bin/python" backend/studio/silma.lock
"$DARIJA_STATE_ROOT/silma/bin/python" backend/studio/prepare_models.py \
  --root "$DARIJA_MODEL_ROOT" --roles tts vocoder
bash backend/studio/start_silma.sh
```

The service binds to 127.0.0.1:8002 with one worker. TTS/vocoder preparation is
independent of STT/Atlas; a subset receipt does not claim the full stack is ready.

In another Studio terminal:

```bash
"$DARIJA_STATE_ROOT/backend/bin/python" -m uvicorn tts_preview:app \
  --app-dir backend/studio --host 127.0.0.1 --port 8080
```

Use the backend SSH tunnel and open http://localhost:8080 locally. Type Darija,
listen, press Stop during synthesis/playback, then immediately enter another
sentence. The preview loads no STT or LLM and uses the exact existing frontend
24 kHz playback worklet and tts_chunk PCM payload. Its typed controls add request
and generation identifiers. Model-service failure is visible and clears playback.

Ctrl-C stops each process. Restart to apply another voice/checkpoint; individual
phrases never reload the model. [Phase 4 Darija STT/turn integration](STT.md) now enables microphone startup.
[Phase 3 typed Atlas/SILMA chat](ATLAS.md) is implemented.

## Listening comparison

The local comparison uses existing paired final-checkpoint samples for greetings,
questions, negation, spoken numbers, and longer replies, across both references
and main/EMA weights. The user selected voice1 + main from those samples.
They predate this integration and retain their original duration settings;
they establish voice preference, not validation of the new service.

When Studio validation resumes, stop the service and generate fresh paired samples
covering all six categories, including proper names and digit identifiers:

```bash
"$DARIJA_STATE_ROOT/silma/bin/python" backend/studio/generate_voice_comparison.py \
  --root "$DARIJA_MODEL_ROOT" --output "$DARIJA_STATE_ROOT/voice-comparison"
```

The command uses the new reference-rate duration and phrase path, paired seeds,
and 32 steps. It loads one reference/checkpoint combination at a time and frees
each before the next. Outputs are PCM16 WAVs, metadata, and a listening page.

## Local checks

```bash
uv run --no-project --with fastapi==0.135.4 --with starlette==0.52.1 \
  --with pydantic==2.10.6 --with httpx==0.28.1 --with PyYAML==6.0.2 \
  --with openai==3.29.0 --with numpy==1.26.4 \
  python -m unittest discover -s backend/tests -v
node backend/tests/test_preview_player.js
```

The phase 2 checks passed; the expanded phase 3 suite also covers Atlas streaming. Tests use deterministic
fake PCM, never GPU inference. They cover phrase/tail
ordering, Arabic punctuation, decimal/name preservation, UTF-8 bounds, dynamic
duration, backpressure, cancellation during synthesis and between quick/final
phases, late results, reset/reuse, persisted selection, HTTP/PCM contracts,
typed WebSocket delivery, and browser stale-response suppression.

GPU loading, fresh intelligibility/listening checks, live playback, and latency
remain deferred at the user's request. The phase 2 audible exit check is unverified.
