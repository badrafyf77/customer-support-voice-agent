# Phase 4 status — 15 October 2026

Implementation complete locally in `codex/darija-voice-model-review`, based on
`7adb0565186569420458bb32500e072f62c832ae`. The original checkout remains untouched.

- Partial and final Darija recognition use the verified corrected CTranslate2
  export, Arabic settings and no English initial prompts, sharing the main model.
- Runtime/transport wiring passes STT configuration per instance. Capture,
  resampling, VAD, decoding defaults and recorder callbacks are retained.
- Unicode comparison keys preserve Arabic, digits and foreign names; transcript
  callbacks retain the original recognized text. Arabic question/ellipsis
  punctuation is handled through the existing detection path.
- CPU turn detection applies pinned normalization, left truncation to 128 tokens,
  temperature 3.9, saved threshold 0.7780777968696678, and supplied syntax rules.
  Learned probability, decision score and classification remain distinguishable.
- The decision score feeds the existing dynamic pause formula, with unchanged
  punctuation weighting, speed settings, ellipsis adjustment and latency floor.
  No fixed 1.4/2.2-second schedule or extra digit delay was added.
- Reset epochs suppress queued and in-flight old scores and cache writes; runtime
  reuse restores the recorder's initial silence setting. Worker shutdown and
  invalid-logit handling are implemented.
- Darija microphone startup is enabled after artifact/service validation, with
  one active runtime, Atlas warmup in Darija and SILMA voice1 + main.
- All 73 local backend tests and browser control checks pass. The pinned tokenizer
  and saved calibration were verified offline without loading weights.
- Representative text cases and real-recorder replay/report commands are ready.
  No live inference or Studio validation was performed, as the user requested.

Commands and evidence: [STT.md](../../backend/studio/STT.md).
The phase 4 live exit check is deferred: recognition accuracy, calibrated
classifier quality on audio transcripts, replay timing and audible full-stack
behavior remain unverified. Phase 5 covers complete browser conversation checks.
