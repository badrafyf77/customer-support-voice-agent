# Phase 5 status — 15 October 2026

Browser/session implementation and local verification complete in the existing
`codex/darija-voice-model-review` worktree. Live Studio acceptance remains deferred
at the user's request. The original checkout was not changed.

- Added automatic transcript direction while preserving names and identifiers.
- Kept `/ws` microphone framing, transcript/PCM/stop event names and worklet flow.
  Optional Darija generation IDs reject canceled audio/text and stale Stop events.
- Darija commits the final recognized transcript, keeps microphone capture active
  for VAD barge-in, and interrupts during synthesis/playback or between phrases.
- Canceled pending prepares and bound model callbacks to their original turn;
  old callbacks cannot mutate a later turn or another session.
- Visible errors clear playback and close failed sessions. Stopped STT workers
  and unsafe speech workers retire their runtime. ASGI cancellation cannot
  interrupt lease cleanup. No fallback models were added.
- Reset clears actual conversation/pending chat state. Reconnect clears the UI,
  ignores old sockets, and safely reuses healthy warmed runtimes.
- Added production-session/lease integration tests, worklet/generation tests and
  a real Chromium browser test using synthetic microphone and fake model PCM.
- All 83 backend tests pass with locked web dependencies. Browser, TypeScript,
  worklet/generation and production build checks are recorded in the verification
  report. A screenshot was inspected for Arabic/mixed-identifier rendering.

Commands and the pending live checklist: [BROWSER.md](../../backend/studio/BROWSER.md).
The live exit check is not claimed: native Darija quality, real ASR accuracy,
audible interruption, sustained full-model conversation and L4 memory/latency
remain unverified. Phase 6 measurement/tuning still requires the actual Studio.
