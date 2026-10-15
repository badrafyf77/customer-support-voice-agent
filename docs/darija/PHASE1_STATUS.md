# Phase 1 preparation status

Phase 2 is now implemented; see [current status](PHASE2_STATUS.md).

Implemented on `codex/darija-voice-model-review`, based on
`7adb0565186569420458bb32500e072f62c832ae`.

## Completed locally

- Read the session, runtime pool, transport, STT/turn detection, LLM/TTS workers,
  agents, frontend capture/playback, Docker config, and Darija plan.
- Corrected startup selection and made chat/darija a selectable preparation profile.
  Warmup and WebSocket sessions now use the selected configuration.
- Added model identities, full revisions, known hashes, reproducible snapshot
  retrieval, readiness receipts, explicit startup diagnostics, and load probes.
- Retrieved the **correct** Darija CTranslate2 export from the original Modal
  volume. All five file sizes and SHA-256 hashes match the prior provenance;
  [verification report](asr-artifact-verification.json).
  The ignored local cache is
  `backend/studio/.models/asr-download/ctranslate2`.
- Retrieved Atlas's pinned tokenizer, chat template, model configuration, generation
  configuration, and weight index. Both configurations specify EOS IDs `[1, 107]`.
  Full Atlas weights are retrieved by the Studio preparation script.
- Added separate dependency environments, an internal Atlas vLLM launcher,
  persistent cache settings, runtime-secret instructions, and the backend SSH tunnel.
- Documented English events/timing and provided an optional browser trace recorder.
- Local regression checks cover configuration selection, startup and WebSocket
  configuration consistency, artifact mismatch/missing files, and Darija exam rejection.

## Deferred by the user

The user confirmed English behavior works and will test once Darija integration
is ready. No Studio connection, Linux environment installation, GPU model load,
vLLM streaming request, English audio benchmark, or Darija voice session was run.
The remaining turn/TTS/vocoder/full-Atlas downloads are handled by prepare_models.py
on Studio. No all-model readiness receipt was generated on this workstation.

## Next implementation phase

Phase 2: add the SILMA inference service and TTS provider through the existing
pipeline boundary, preserve quick/final phrase flow, and suppress canceled audio.
The Darija profile deliberately reports that this provider is pending instead of
attempting to speak with Kokoro.

Setup commands: [backend/studio/README.md](../../backend/studio/README.md).
