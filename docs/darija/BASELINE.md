# English baseline — phase 1

Baseline commit: `7adb0565186569420458bb32500e072f62c832ae`.
Inspection date: 13 October 2026. Branch: `codex/darija-voice-model-review`.

This is a **source-inspected baseline**, not a recorded L4 conversation.
The user confirmed English behavior already works and requested deferring Studio
validation until Darija integration is ready. This workstation is macOS without
NVIDIA CUDA. The capture protocol below remains available for a later comparison.
Do not use the existing Modal ASR scores as voice-pipeline latency measurements.

## Configuration and startup finding

The committed English configuration uses medium.en/small.en, shared realtime
recognition by default, Kokoro, Qwen2.5-1.5B-Instruct through vLLM, and English.
Turn detection runs on CPU when configured explicitly. Runtime concurrency is one
in the default environment. The Docker vLLM allocation is 80%; that setting has
not been established as safe for the combined Darija models.

Before phase 1, server.py assigned app.state.AGENT_NAME='exam'. Lifespan preferred
that attribute over VOICE_AGENT. Plain /ws still constructed ChatAgentBrain but
leased speech models warmed using exam config. The two committed configs happen
to use the same models; custom chat config could silently be ignored.

Phase 1 resolves VOICE_AGENT and VOICE_PROFILE once before warmup and uses that
config for leased sessions. The default is chat/english. Exam query parameters
still select the exam brain in English deployments; Darija rejects exam sessions.
STT_MODEL and STT_REALTIME_MODEL now survive YAML application at startup.
Run this corrected startup as the English comparison and record its commit.

Dependency resolution also found an existing Docker inconsistency:
RealtimeTTS 0.5.5's Coqui extra requires Transformers >=4.47, while the Dockerfile
later installs 4.36.2. The isolated Studio backend pins 4.51.3; the original
Dockerfile is unchanged. This dependency change needs a live baseline check.
The Studio backend also aligns torch 2.6.0/CTranslate2 4.6.0 with the tested ASR
export's CUDA 12.4/cuDNN 9 tooling. The original Docker CTranslate2 4.4.0 requires
system cuDNN 8; copying its Python packages alone would not reproduce that runtime.
Record both environments when comparing the English baseline.

## Source-inspected event sequence

| Stage | Observable events or behavior |
| --- | --- |
| Connect | /ws accepts; status initializing; optional waiting_for_runtime; warmed runtime lease/reset; status ready. |
| Capture | Browser sends an 8-byte big-endian timestamp/flags header followed by audio payload; transport resamples input for 16 kHz STT. |
| Partial recognition | STT callbacks produce partial_user_request; partials can trigger interruption checks. |
| Endpoint | on_before_final finalizes the user turn, emits final_user_request, appends history. The agent schedules the response after the finalized transcript. |
| Generation | Existing LLM worker streams text; quick-answer worker synthesizes the first phrase; final-answer worker consumes the remaining stream. |
| Text | assistant_partial updates may repeat; partial_assistant_answer is conditional; final_assistant_answer is delivered or forced during interruption. Their exact interleaving with audio is asynchronous. |
| Audio | tts_chunk carries base64 PCM16; playback worklet consumes mono 24 kHz samples in FIFO order. Browser reports tts_start and tts_stop. |
| Interrupt | While client playback is active, VAD recording start queues tts_interruption then stop_tts, suppresses chunk sending, aborts generation, and forces delivered assistant text. Browser clears its buffer. |
| Disconnect/reuse | Session tasks stop; the runtime resets history/callbacks/generation state before returning to the pool. |

The potential-sentence callback returns early when an agent brain is attached.
Do not assume speculative response generation begins on every partial transcript.
Playback-stop/start events can also represent buffer starvation between phrases.

## Timing behavior to retain

Recorder initial post-speech silence is 0.6 s. Semantic probability maps linearly
to `1 - p`; the existing policy combines punctuation and model pauses at
0.65/0.35, scales by detection_speed, adds 0.2 s for ellipses, and applies the
pipeline-latency + 0.1 s floor. Recorder/STT has further timing logic; these
constants are not measured endpointing times.

TTS_FINAL_TIMEOUT is 1.0 s and participates in completion detection after audio.
No turn timing, VAD, quick/final worker, or browser playback code changes in phase 1.
In particular, no 1.4/2.2-second fixed silence schedule is imported.

## Capture on the L4

1. Start the English stack from the baseline commit (or retain an existing measured
   baseline), then repeat with phase 1's corrected startup. Save dependency freezes,
   git commit, GPU/driver information, model settings, microphone/sample rate,
   browser version, and tunnel/network conditions for both.
2. Before connecting, paste backend/studio/browser_trace.js into browser DevTools.
   It records event types and monotonic browser timestamps without transcript/audio.
   Save with `copy(JSON.stringify(voiceTrace.events, null, 2))`. Reload to restore
   normal constructors. Keep logs outside Git.
3. Record microphone and playback on a common audio timeline. Run five warm turns:
   greeting, short question, a longer explanation, an unfinished clause, and a
   number/name. Repeat three times, then interrupt a long reply and start a new turn.
   Browser `voiceTrace.mark("speech_end")` is a coarse manual marker; recorded audio
   is required for accurate last-speech and first-audible times.
4. Run `nvidia-smi --query-gpu=timestamp,name,memory.used,utilization.gpu --format=csv -lms 100`
   into a local CSV while testing; stop with Ctrl-C. Record idle and sampled peak
   across all processes. PyTorch counters omit CTranslate2 and vLLM allocations.
5. Compare events and transcript/audio outcomes before comparing timing.

| Metric | Definition | L4 result |
| --- | --- | --- |
| Endpointing | Last user speech sample → finalized user transcript | Deferred by user |
| First audible response | Last user speech sample → first assistant playback sample | Deferred by user |
| Phrase gaps | Consecutive assistant audio segment boundaries on playback timeline | Deferred by user |
| Interruption delay | First interrupting user speech sample → last assistant playback sample | Deferred by user |
| Peak GPU memory | Highest sampled total device usage, plus per-process observations | Deferred by user |

Report individual runs and warm p50/p95, separating cold startup. Playback worklet
notifications are scheduling proxies; they omit audio-device output latency.
Never subtract a server wall clock from a browser monotonic timestamp.
