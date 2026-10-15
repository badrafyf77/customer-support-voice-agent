# Phase 3 status — 13 October 2026

Implementation complete locally; live exit check deferred at the user's request.
Work remains in the clean `codex/darija-voice-model-review` worktree; no original
checkout changes were imported.

- Atlas uses the existing streaming API client and quick/final TTS workers.
- Native alternating history is produced at the request boundary; system
  instructions are folded into the first user message without transcript mutation.
- Arabic-script spoken-Darija prompt, uncertainty/clarification instructions,
  preserved names/IDs, EOS IDs 1 and 107, role-marker suppression, BF16,
  one scheduled sequence, context 4096, and response cap 256 are implemented.
- Pending requests cannot resurrect canceled output. Active LLM transport closure
  precedes worker waits; SILMA suppresses canceled PCM. Header waits remain
  subject to the existing HTTP timeout, with Atlas automatic retries disabled.
- Typed multi-turn browser chat uses the actual speech pipeline, SILMA provider,
  and unchanged playback worklet. The selected default remains voice1 + main.
- Fixed a lost whitespace separator at the quick/final boundary for SILMA chat
  and protected hyphenated identifiers at the quick-phrase boundary.
- Offline pinned-tokenizer verification passed for the native template, multi-turn
  generation prompt, special-token IDs, and both configured EOS IDs.
- All 55 local backend tests and browser regression checks pass using local SSE/fake PCM.
  Tests confirm quick audio before LLM EOF, complete ordered tails without repeat,
  active interruption, service failures, clean reconnect, and stale-output rejection.

Prepared commands and representative conversation cases are in
[ATLAS.md](../../backend/studio/ATLAS.md). No Atlas weights or live SILMA inference
were run locally, and no Studio session was used. Output quality, intelligibility,
audible interruption, latency, and combined GPU memory remain unverified.
Microphone Darija startup explicitly awaits phase 4 STT/turn integration.
