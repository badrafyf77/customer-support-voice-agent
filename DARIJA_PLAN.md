# Adapt the Existing Voice Agent to Moroccan Darija

## Objective and fixed decisions

Deliver **general voice chat with Darija-only replies**, preserving the project's existing streaming responses, quick-answer flow, low latency, and user interruptions. Keep changes focused on model loading, provider integration, and Arabic text handling.

| Component | Selected model |
| --- | --- |
| STT | afyfbadreddine77/whisper-large-v3-turbo-darija |
| Turn detection | afyfbadreddine77/darija-turn-detection |
| LLM | MBZUAI-Paris/Atlas-Chat-2B |
| TTS | afyfbadreddine77/silma-tts-darija |

Atlas-Chat-2B replaces the previously proposed SILMA LLM base and Darija LoRA adapter. Load Atlas directly as a complete model; no separate LLM base or LoRA registration is required. SILMA remains the TTS model.

Deployment: one Lightning AI Studio with an **NVIDIA L4**, plus the Next.js frontend running locally. Start with one active conversation. Run STT, LLM, and TTS on the GPU; run turn detection and VAD on CPU.

Work on the **codex/darija-voice-model-review** branch, based on commit **7adb0565186569420458bb32500e072f62c832ae**. Use the clean committed baseline. Selectively adapt useful inference code from the silma-tts workspace without importing the original checkout's uncommitted changes wholesale.

Exam features and business integrations are outside this release. Assistant replies should use Arabic-script Darija; preserve names and factual identifiers when necessary. No new fixed waiting periods or broad session-pipeline redesign should be introduced by default.

## Phase 1 — Establish the baseline and Studio environment

**Purpose:** protect the behavior that already works and make model loading reproducible.

- Record the English pipeline's event sequence and, where runnable on the L4, its endpointing delay, first audible response, phrase gaps, interruption delay, and peak GPU memory.
- Add a selectable Darija chat configuration. Correct the startup configuration path so the hardcoded exam setting cannot override the selected chat runtime.
- Prepare isolated environments for the voice backend, vLLM, and SILMA TTS. Use separate processes on the same Studio, with persistent model caches and pinned model revisions.
- Retrieve or reproduce the **correct STT model's** CTranslate2 export and verify its provenance. Do not reuse the whisper-large-v3-turbo-darija-125h export.
- Download Atlas-Chat-2B and its tokenizer directly. Record the full-model revision rather than preparing an LLM adapter.
- Use an SSH tunnel for the local frontend's backend connection. Keep vLLM and TTS endpoints internal.
- Record model IDs and revisions in startup diagnostics. Missing private models must produce a clear startup failure; credentials must remain in runtime secrets.

**Exit check:** the baseline is documented, all required artifacts are identified, and the Studio can load each model independently.

## Phase 2 — Add SILMA TTS and select the assistant voice

**Purpose:** resolve the largest unsupported component without redesigning session orchestration.

- Introduce a small TTS provider factory in place of direct RealtimeTTSProvider construction. Keep existing providers available through the same boundary.
- Implement SilmaTTSProvider with the existing contract: synthesis from text or a text generator, stop, reset, shutdown, first-audio callback, and measured TTS latency.
- Back it with a private SILMA inference service. Load the custom architecture and adapted weights using the supplied loader; cache the model, Vocos vocoder, reference waveform, and reference transcript.
- Accept phrase text and a generation identifier; return mono **24 kHz signed PCM16** compatible with the existing browser player. Provide readiness and cancellation operations. Do not download models or reload the vocoder per phrase.
- Estimate duration from the reference speaking rate and generated text length, following the inspected SILMA inference approach, instead of applying the example's fixed six-second duration.
- Preserve the existing quick-answer/remaining-answer split. Add Arabic punctuation recognition to the first-phrase detector; let the SILMA provider segment the remaining text stream into phrases and flush trailing text.
- Synthesize phrases sequentially while previously generated audio plays, with bounded pending work. SILMA completes synthesis for each phrase before its audio becomes available; packet slicing alone does not remove that delay.
- On cancellation, stop submitting phrases and suppress late results. An active diffusion pass may finish internally, but its canceled audio must never reach playback.
- Begin with the tested 32-step synthesis settings. Use EMA as the smoke-test default, then compare main and EMA weights with the available reference voices on identical Darija sentences.
- Produce a listening comparison covering greetings, questions, negation, names, numbers, and longer replies. The user selects the reference voice and checkpoint variant; store that choice as configuration and cache the selected reference.
- Keep transcript text separate from any pronunciation preparation for numbers or abbreviations. Avoid automatic standard-Arabic diacritization.

**Exit check:** typed Darija produces intelligible speech through the existing browser playback path using a selected voice, and cancellation suppresses subsequent audio.

## Phase 3 — Connect Atlas-Chat-2B while preserving streaming

**Purpose:** replace the language model through the existing API boundary.

- Serve **MBZUAI-Paris/Atlas-Chat-2B** directly in vLLM. Configure the existing backend client to request that served model. Remove the previous plan's SILMA base-model loading and LoRA registration steps.
- Load the tokenizer and chat template from the pinned Atlas revision. Its native template rejects a standalone system role and requires alternating user/assistant turns. At the LLM request boundary, prepend the voice-assistant instructions to the first user message before applying the native template; leave the stored conversation transcript unchanged.
- Verify history formatting, generation prompts, and both configured end-of-turn token IDs. Do not expose model role markers in spoken output.
- Keep the existing streaming LLM client, quick-answer worker, remaining-answer worker, and cancellation flow.
- Use spoken-Darija instructions: short natural replies, Arabic-script Darija, clarification when uncertain, and no unsolicited French or English responses.
- Preserve names and factual identifiers. Do not apply indiscriminate Arabizi digit replacement, which would corrupt quantities and phone numbers.
- Start with one concurrent generation, a **4,096-token context limit**, and a **256-token response cap**. Use BF16 initially; introduce quantization only if measured memory pressure requires it.
- Check Atlas on representative conversations rather than assuming model replacement preserves output quality or latency.

**Exit check:** multi-turn text conversations stream Darija replies through SILMA TTS before the full response completes, and interruption closes the active generation.

## Phase 4 — Adapt STT and turn detection with minimal timing changes

**Purpose:** recognize Darija while retaining the existing conversational pace.

- Load the corrected Whisper CTranslate2 export for both partial and final transcription. Use Arabic transcription settings and remove English-only hints from the Darija profile.
- Preserve the current audio capture, resampling, VAD, recorder callbacks, and decoding defaults initially.
- Replace ASCII-only normalization that currently removes Arabic letters. Preserve Arabic text, numbers, and recognized foreign names.
- Load the Darija completion model with its normalization, last-128-token truncation, temperature **3.9**, threshold **0.7781**, and syntax overrides.
- Feed its calibrated decision score into the existing probability-to-pause calculation. Use the threshold for completion classification and diagnostics.
- **Retain the current dynamic timing and latency-floor logic.** Do not introduce the previously proposed fixed 1.4/2.2-second silence schedule.
- Add Arabic punctuation equivalents. Invalidate pending classifier results on reset so an earlier utterance cannot change the next turn's timing.
- Replay complete utterances, dangling clauses, short acknowledgments, hesitation, and numbers with the corrected STT model before changing timing constants.
- Keep speech-boundary detection in VAD; the semantic classifier complements it rather than replacing it.

**Exit check:** Darija transcripts and completion scores reach the existing session flow correctly, without added fixed waiting periods or stale turn decisions.

## Phase 5 — Verify the complete browser conversation

**Purpose:** prove the adapted components behave as one voice agent.

- Run the local frontend against the Studio backend through the tunnel.
- Keep the existing /ws audio framing, transcript events, tts_chunk messages, and stop/interruption messages.
- Add automatic text direction for transcripts so Arabic, names, and numbers display correctly.
- Verify ordered phrase playback with no repeated quick-answer text, missing tails, or audio from canceled generations.
- Verify interruption during synthesis, during playback, and between phrases; then immediately begin another user turn.
- Handle model-service failures with a visible error and a clean session state. Do not silently substitute another model.
- Verify reconnecting and leasing a reused runtime do not carry over another conversation's history, pending audio, or canceled request state.
- Exercise Darija-only replies when the input contains French/English terms; preserve identifiers while expressing the surrounding response in Darija.

**Exit check:** a sustained Darija-only conversation works through microphone, recognition, response generation, speech playback, interruption, and reconnect.

## Phase 6 — Tune on the L4 and deliver a repeatable setup

**Purpose:** preserve responsiveness under the actual deployment constraints.

- Measure all services together. Replace the existing vLLM 80% GPU allocation with a tested budget that leaves headroom for STT, TTS, and inference peaks.
- Measure endpointing, Atlas first-token time, TTS first-audio time, browser first-audible time, phrase gaps, and interruption handling separately.
- Optimize model warmup, reference caching, phrase length, and redundant buffering first. Change established session logic only when a reproducible failure demonstrates the need.
- Benchmark reduced TTS sampling steps only after establishing the quality baseline; adopt them only if listening tests preserve intelligibility and the selected voice.
- Add focused regression tests for Arabic normalization, Atlas chat formatting and stop tokens, model calibration, phrase ordering, end-of-stream flushing, cancellation, and stale-result rejection.
- Keep concurrency at one for this release. A second session receives a clear capacity response rather than loading duplicate GPU models.
- Deliver pinned dependencies, model preparation instructions, Studio start/stop commands, tunnel setup, configuration examples, and a measured latency/memory report.

**Final acceptance:** all four intended models are confirmed in use; replies are Darija-only; speech streams in phrases; interruptions stop audible output without stale audio returning; and a sustained single-session test completes without memory growth or GPU exhaustion. Report any remaining latency difference from the English baseline explicitly rather than assuming model substitution preserves identical speed.

## Sources and implementation references

- Project architecture: backend/code/ARCHITECTURE.md.
- Local model workspace: /Users/afyfbadreddine/Downloads/silma-tts/.
- Correct STT comparison and export provenance: turn_detection/ASR_MODEL_COMPARISON.md and turn_detection/user_asr_other-export_result.json in that workspace.
- SILMA custom loader: hf_inference.py in that workspace; reference selection samples are under research/pilot_evaluation/ and research/full_evaluation/.
- [Atlas-Chat-2B model card](https://huggingface.co/MBZUAI-Paris/Atlas-Chat-2B).
- [Atlas tokenizer configuration and native chat template](https://huggingface.co/MBZUAI-Paris/Atlas-Chat-2B/blob/main/tokenizer_config.json).
- [Atlas model configuration](https://huggingface.co/MBZUAI-Paris/Atlas-Chat-2B/blob/main/config.json).

## Phase 1 implementation status — 13 October 2026

- Working in the specified clean worktree and branch; the main checkout's
  uncommitted changes were preserved.
- Added chat/english and chat/darija startup selection before runtime warmup;
  WebSocket sessions use the selected runtime configuration.
- Added pinned artifact identities, export hashes, model preparation receipts,
  offline validation, isolated Studio dependency locks, independent load probes,
  an internal vLLM launcher, and SSH tunnel instructions.
- Documented the source-inspected English event sequence and existing timing
  behavior in docs/darija/BASELINE.md.
- The user confirmed the English code works and requested **deferring Studio
  validation until Darija integration is ready**, when they will test it. Treat
  English behavior as accepted; do not block subsequent implementation on fresh
  English measurements or request Studio access again for those checks.
- No full Darija conversation has been launched. SILMA provider, Atlas request
  formatting, and Darija STT/turn policy integration remain phases 2–4.

Setup and current validation status: backend/studio/README.md.

## Phase 2 implementation status — 13 October 2026

- Added the provider factory and SILMA provider through the existing quick/final
  TTS boundary, preserving existing English engines.
- Added the isolated internal SILMA service with pinned custom weights/vocoder,
  cached references, reference-rate duration, 32-step generation, PCM16 output,
  readiness, bounded work, and cancellation/stale-result suppression.
- Added Arabic phrase boundaries, tail flushing, identifier protection, and a typed
  preview using the existing frontend audio worklet.
- Built a listening comparison from existing paired final-checkpoint audio.
  The user's final selection is **voice1 + main weights**, persisted in
  backend/studio/voices/selection.json and the Studio environment example.
- Added a fresh comparison generator covering greetings, questions, negation,
  names, numbers, and longer replies, ready for the later Studio run.
- Local regression tests exercise the transport/control contracts with fake PCM.
  No GPU inference or live Studio tests were run, as requested. New intelligibility
  and audible playback checks remain unverified.

Implementation and commands: backend/studio/SILMA.md. Next: phase 3 Atlas request
formatting and streaming integration.


## Phase 3 implementation status — 13 October 2026

- Connected pinned Atlas through the existing streaming client and quick/final
  speech workers. Native-template adaptation folds instructions into the first
  user message and leaves stored transcripts unchanged.
- Added spoken-Darija instructions, strict response limits, both EOS IDs, and
  streaming suppression of split role markers. vLLM serves BF16, context 4096,
  one scheduled sequence, and a server response cap of 256.
- Fixed cancellation around pending stream opens and closed active Atlas streams
  before worker waits. No automatic Atlas retries after transport failures.
- Added typed multi-turn Atlas/SILMA browser chat using the existing pipeline and
  playback worklet, with scoped text/audio, error cleanup and clean reconnect.
  The selected voice remains **voice1 + main weights**.
- Verified the exact pinned tokenizer/template and multi-turn generation prompt
  locally without loading model weights. Local SSE/fake-PCM regression checks
  confirm early quick speech, ordered tails, cancellation and session isolation.
- Prepared representative conversation cases and a Studio streaming/cancellation
  report command. Language quality, listening, GPU memory and measured latency
  remain deferred at the user's request; the live phase 3 exit check is not yet
  claimed. Microphone startup awaits phase 4 STT/turn integration.

Implementation and commands: backend/studio/ATLAS.md. Next: phase 4.


## Phase 4 implementation status — 15 October 2026

- Wired the corrected CTranslate2 ASR into both partial/final paths with Arabic
  settings and removed English-only hints, preserving capture, resampling, VAD,
  callback flow and decoding defaults.
- Added Unicode transcript comparison, Arabic punctuation equivalents, and CPU
  Darija completion with the saved normalization, last 128 tokens, temperature
  3.9, precise saved threshold (approximately 0.7781), and syntax overrides.
- Fed the calibrated decision score into the existing dynamic pause calculation
  and latency floor. No fixed 1.4/2.2-second schedule or digit delay was imported.
- Added reset epochs to discard pending/in-flight old classifier results and
  restored initial recorder silence on session reuse.
- Enabled the Darija microphone startup path after full artifact validation,
  preserving the selected voice1 + main and limiting Darija to one active runtime.
- All 73 local backend tests and browser checks pass; pinned tokenizer/calibration
  metadata were checked offline without loading model weights.
- Prepared representative completion cases and actual-recorder replay tooling.
  Live recognition/classifier/replay checks remain deferred at the user's request;
  the phase 4 live exit check has not been claimed.

Implementation and commands: backend/studio/STT.md. Next: phase 5.


## Phase 5 implementation status — 15 October 2026

- Added automatic transcript direction and optional Darija generation IDs while
  retaining /ws audio framing, transcript/PCM events and existing worklets.
- Fixed final-STT turn commitment and Darija VAD interruption before first audio,
  during playback and between phrases; microphone input remains active for barge-in.
- Added generation-bound text callbacks, canceled queued prepares, stale output
  filtering, visible model-service errors and clean reconnect behavior.
- Shielded runtime cleanup from ASGI cancellation and retire runtimes with stopped
  STT workers or speech workers that did not stop, preserving safe reuse.
- Reset clears session history/pending chat state. Old socket callbacks and late
  microphone permission results cannot reactivate a stopped session.
- All 83 backend tests pass with locked web dependencies. The real local frontend
  and Chromium pass synthetic-microphone /ws tests against production session,
  runtime and speech workers with deterministic model boundaries.
- The user-requested Studio deferral remains in force. The live sustained Darija
  conversation exit check is not claimed; language/listening quality, actual ASR,
  audible cancellation and combined GPU behavior still need the user's run.

Implementation, local evidence and live checklist: backend/studio/BROWSER.md.
Next: phase 6 measurement and repeatable setup.

## Phase 6 implementation status — 15 October 2026

- Added the complete Studio/local deployment runbook, direct ASR transfer,
  ordered service supervisor, start/stop commands, isolated CUDA-library setup,
  and startup/runtime diagnostics. The selected voice remains voice1 + main.
- Added GPU sampling, resident-stack sequential/overlapping Atlas/TTS probes,
  saved listening WAVs, browser timing marks/export and measured-summary tooling.
- Added immediate single-session capacity feedback and targeted regression checks.
- The deployment example explicitly uses 0.40 as the first vLLM **candidate**;
  combined L4 loading/headroom must establish the adopted allocation.
- Kept cached models/references, existing dynamic endpoint timing, bounded phrases
  and 32 TTS steps. No unmeasured tuning or unsupported lower-step adoption.
- The user's deferred Studio run is now documented step by step. Actual Linux
  installation, L4 memory/latency, language/listening quality and final sustained
  microphone acceptance remain pending, with an honest blank report template.

Commands: backend/studio/RUNBOOK.md. Scope: docs/darija/PHASE6_STATUS.md.
Phase 6 is the last planned phase; live final acceptance is still open.

### Deployment preference update — 15 October 2026

The user already has NVIDIA, Docker and Docker Compose installed on Studio and
requested a simpler deployment: `backend/.env` including HF_TOKEN, Docker Compose
build/start, an exposed Lightning backend port, and its URL in the local frontend
environment. This supersedes native host environments, Lightning Secrets and
SSH tunneling as the primary setup. See backend/studio/DOCKER.md. The corrected
ASR export still needs a one-time upload/path; other pinned models are prepared
automatically by Compose. Live L4 acceptance remains pending.
