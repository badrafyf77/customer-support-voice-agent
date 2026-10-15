# Phase 2 implementation status

Implemented in the existing codex/darija-voice-model-review worktree.

- SILMA provider and provider factory are integrated with the existing quick/final
  workers. Existing English engines retain their behavior.
- The internal service caches the pinned custom model, Vocos, reference waveform,
  and reference transcript. It uses 32 steps and reference-rate duration estimation.
- PCM output is mono 24 kHz signed little-endian 16-bit audio. Phrase ordering,
  trailing text, Arabic punctuation, and identifier preservation are handled.
- Work and audio queues are bounded. Cancellation suppresses late results and audio
  from earlier generations or reused sessions, while active diffusion may finish.
- A typed preview reuses the existing browser playback worklet and checks request
  IDs to reject stale audio after Stop.
- The user chose **voice1 + main weights** from existing paired comparison samples.
  That choice is persisted in the shared selection and Studio configuration example.
- A fresh paired listening comparison generator covers greetings, questions,
  negation, names, digit identifiers, and longer replies.

Local verification: 38 backend regression tests and browser playback-control checks
use deterministic fake PCM. Python/JavaScript/shell syntax and diff checks pass.
No GPU model execution or live Studio validation was performed, as requested.
Actual new-service speech quality, latency, and audible playback remain unverified.

Commands and contracts: [backend/studio/SILMA.md](../../backend/studio/SILMA.md).
Next implementation: phase 3 Atlas request formatting and streaming integration.
