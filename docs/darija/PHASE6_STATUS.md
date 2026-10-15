# Phase 6 implementation — 15 October 2026

Implemented locally:

- Complete [Lightning/local runbook](../../backend/studio/RUNBOOK.md), with native
  dependency setup, pinned model preparation, direct verified ASR transfer from
  this Mac, isolated processes, secrets, SSH tunnel and local frontend commands.
- Foreground Studio supervisor starts Atlas, SILMA and the single backend worker
  in order, waits for readiness, saves separate logs/configuration provenance and
  samples device-wide GPU usage. Ctrl-C/error cleans up only its own process groups.
- Backend launcher propagates installed NVIDIA CUDA library paths to CTranslate2
  recorder subprocesses; no reliance on the old Docker cuDNN 8 configuration.
- Explicit provisional vLLM allocation 0.40 in the deployment example; the old
  80% allocation is not reused. No combined-load budget is claimed as tested.
- Resident-stack probes measure Atlas first spoken text and SILMA first PCM,
  synthesis time/real-time factor, sequentially and concurrently, and save WAVs
  for selected-voice quality review. All stacks remain loaded; active microphone
  inference is exercised in the separate browser run.
- Bounded browser timing capture with optional manual endpoint/interruption marks,
  generation IDs, rendering events, audio-context latency metadata and JSON export.
  It does not record transcript/audio. Summary calculations keep browser clocks
  separate from Studio clocks and do not claim physical acoustic measurements.
- Immediate Darija capacity rejection through the existing single-runtime manager,
  with regression coverage that the first session remains usable and no duplicate
  runtime is loaded. Backend status exposes profile/runtime counts.
- Measurement/acceptance template explicitly leaves unmeasured values pending.

Existing regression checks cover Arabic normalization, calibrated turn policy,
Atlas formatting/stops, phrase ordering/tails, cancellation, stale results and
browser reset/reconnect. Additional phase 6 checks cover measurement summaries,
turn-boundary gap handling and owned-process shutdown.
All 89 backend tests, frontend unit/type checks, nine production-frontend
Chromium check groups, trace privacy/restore checks and syntax checks pass locally.
Saved scope: [phase6-verification.json](phase6-verification.json).

Pending user Studio run:

- Actual Linux native installs and all model loads on L4.
- Combined GPU headroom/budget adoption, recognition/language/listening review,
  acoustic interruption and sustained live-browser acceptance.
- Measured L4 latency/memory report. No fabricated results or assumed English
  latency equivalence; the English measurement baseline was deferred by the user.
- Fewer TTS steps and any timing/queue changes require a quality baseline and
  reproducible measurement evidence first. No speculative tuning was applied.

Phase 6 deployment/measurement tooling is implemented. The plan's **live final
acceptance remains open** until these Studio checks are completed.
