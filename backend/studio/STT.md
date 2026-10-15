# Phase 4 — Darija recognition and dynamic turn detection

The Darija microphone path is now wired through the existing recorder, transport,
voice runtime manager, session, Atlas streaming client and SILMA provider. Live
Studio validation remains deferred at the user's request. The selected assistant
voice remains **voice1 + main weights**.

## Recognition

Startup verifies the prepared artifacts and receipt before creating warmed
runtimes. Partial and final transcription both use the corrected CTranslate2
export of `afyfbadreddine77/whisper-large-v3-turbo-darija` revision
`e9ff459f2f5823d4f9093db8854c691eb78045d3`. Its model.bin SHA-256 remains
`c130a5ee127bda0df5088ba815bddbe34b02f244903ab4da13a3460b28e49646`.
The 125h export is not accepted. STT_MODEL/STT_REALTIME_MODEL, if set, must resolve
to that verified prepared ASR directory. A mismatched deployment fails before
model warmup rather than quietly using another model.

The Darija recorder configuration sets Arabic transcription, uses the same main
model for realtime work, and removes both English initial prompts. Sharing the
main model avoids a second GPU copy. The inspected RealtimeSTT 0.3.104 source
routes realtime requests through its main transcription worker in this mode.
Its internal library startup probe uses an English warmup clip; user audio still
uses Arabic, and no English prompt is supplied by this integration.

Beam sizes, recording lengths/gaps, realtime polling, VAD sensitivity and ONNX
settings stay at their existing defaults. Audio capture, the browser PCM framing,
and the 48 kHz to 16 kHz resampling algorithm are unchanged. Faster-whisper retains
its usual right-padded feature extraction; the saved HF processor's left-padding
finding does not change this CTranslate2 path.

Comparison normalization now keeps Unicode letters and digits, including Arabic
and accented foreign names. It affects deduplication keys only. Raw partial/final
transcript callbacks preserve punctuation, names, order IDs, decimals and phone
numbers. Arabic `؟` is a sentence-ending equivalent of `?`; `…` is treated like
`...`, including the existing hesitation behavior. Arabic comma/semicolon remain
nonterminal punctuation rather than forcing finalization.

## Completion scoring

The pinned `afyfbadreddine77/darija-turn-detection` model runs on CPU. The runtime
loads local files only, disables remote model code, checks its saved configuration
and label mapping, and uses the training normalization from `darija_v1`:
NFKC, the supplied gaf spelling mapping, punctuation to spaces, removal of format
characters, and whitespace folding. Arabic/Latin letters, accents and numbers
remain available to the model. Normalized text is not substituted into transcripts.

Tokenizer truncation is **left**, retaining the last **128 tokens** including
special tokens. The saved temperature is **3.9**. The complete class is index 1;
the learned completion probability is `softmax(logits / 3.9)[1]`.
The supplied `darija_calls_v2` rules then give limited overrides for dangling
function words, unfinished modal clauses, hesitation, conventional short replies
and acknowledgments. Learned probability and rule-adjusted decision score remain
separate in diagnostics. The threshold uses full saved precision,
**0.7780777968696678** (approximately 0.7781), for `is_complete` classification.

The normalization and rules were selectively adapted from the inspected model
export. [turn-policy-provenance.json](../../docs/darija/turn-policy-provenance.json)
records the source hashes. The research inference script's fixed 1.4/2.2-second
schedule was not imported.

## Timing and reset

The rule-adjusted score feeds the existing probability-to-pause interpolation:

```text
model_pause = interpolate_detection(decision_score)  # currently 1 - score
weighted_pause = 0.65 * punctuation_pause + 0.35 * model_pause
pause = weighted_pause * detection_speed
pause += 0.2 if recent matching text contains ellipses else 0
pause = max(pause, pipeline_latency + pipeline_latency_overhead)
```

Existing fast/slow settings, punctuation-history averaging, ellipsis adjustment,
latency floor, and silence-monitor thresholds remain intact. There is no new
fixed digit delay or threshold-selected silence schedule. The classification
threshold is diagnostic; it does not replace this formula. The voice runtime
continues to supply the measured LLM+TTS latency estimate, in seconds, to STT.
A high measured synthesis latency can therefore dominate the pause floor;
measurement/tuning belongs to the later Studio validation.

The semantic model complements VAD. It changes the recorder's suggested silence
duration; it does not assert an acoustic end of speech or bypass VAD.

Each queued text carries a reset epoch. Reset clears pending work, history,
cached probabilities and the last decision. In-flight old inference cannot
publish a pause, repopulate the cache or update diagnostics after reset.
A reused recorder restores its initial silence duration before the next lease.
Shutdown stops the turn worker. Invalid/nonfinite classifier output logs an error
and uses the existing unknown-sentence pause with the latency floor; no other
classifier or speech model is substituted.

## Studio commands for the later validation

Use [README.md](README.md) for pinned artifact preparation and environments.
Prepare both STT and turn artifacts with the corrected export, or verify a receipt
that already includes them:

```bash
"$DARIJA_STATE_ROOT/backend/bin/python" backend/studio/prepare_models.py \
  --root "$DARIJA_MODEL_ROOT" --roles stt turn \
  --asr-export "$DARIJA_MODEL_ROOT/asr-download/ctranslate2"
"$DARIJA_STATE_ROOT/backend/bin/python" backend/studio/verify_turn.py \
  --model-dir "$DARIJA_MODEL_ROOT/turn"
```

The calibrated CPU text probe loads the actual model and reports representative
complete requests, dangling clauses, acknowledgments, hesitation and numbers:

```bash
"$DARIJA_STATE_ROOT/backend/bin/python" backend/studio/smoke_model.py turn \
  --root "$DARIJA_MODEL_ROOT"
```

These examples are authored review cases, not a measured accuracy benchmark.
Inspect [turn_cases.json](turn_cases.json) and compare actual probabilities,
overrides and decisions. Do not tune timing constants on assumed text accuracy.

For real recorder replay, create a local JSON manifest referencing your own mono
16 kHz PCM16 WAV files. Paths are relative to the manifest:

```json
[
  {"name":"complete_utterance","wav":"complete.wav","expected_complete":true},
  {"name":"dangling_clause","wav":"dangling.wav","expected_complete":false},
  {"name":"acknowledgment","wav":"ack.wav","expected_complete":true},
  {"name":"hesitation","wav":"hesitation.wav","expected_complete":false},
  {"name":"numbers_and_names","wav":"numbers.wav","expected_complete":true}
]
```

Run the actual recorder and calibrated classifier, without LLM/TTS:

```bash
"$DARIJA_STATE_ROOT/backend/bin/python" backend/studio/replay_stt.py \
  --root "$DARIJA_MODEL_ROOT" --manifest /path/to/replay.json \
  --output "$DARIJA_STATE_ROOT/stt-turn-replay.json" --pipeline-latency 0.5
```

Use the measured pipeline latency instead of 0.5 when available. The replay uses
real-time PCM input and records partial/final transcripts, VAD-silence events,
changed pause suggestions, completion diagnostics, potential-final events and
final delay relative to the last input frame. This reference is not a labelled
acoustic speech-end timestamp. Review early/multiple finals, dangling clauses,
identifiers and transcripts manually. Each case uses a fresh recorder; browser
reuse/reconnect validation belongs to phase 5.

For full microphone testing later, prepare all roles, start vLLM and SILMA using
[ATLAS.md](ATLAS.md) and [SILMA.md](SILMA.md), export the environment from
`backend/.env.studio.example`, then run:

```bash
"$DARIJA_STATE_ROOT/backend/bin/python" -m uvicorn server:app \
  --app-dir backend/code --host 127.0.0.1 --port 8080
```

The Darija startup gate from phases 1–3 is removed. Startup still requires all
verified artifacts and reachable services. Darija permits one active voice
runtime and uses the Darija prompt during LLM warmup. Keep model services on
loopback and forward only the backend port to the local frontend. Full audible
conversation, UI direction, interruption and reconnect checks are phase 5.

## Local evidence

All **73 backend tests** and browser control checks pass. Tests use fake recorder
callbacks, classifier logits, local SSE and deterministic PCM. They exercise
Arabic transcript preservation, intended ASR/config wiring, calibration and
syntax rules, dynamic timing and latency floors, reset races, invalid logits,
startup rejection of mismatched models, and existing English behavior.

The pinned tokenizer/config check passed offline, without loading weights:
[turn-tokenizer-verification.json](../../docs/darija/turn-tokenizer-verification.json).

```bash
uv run --no-project --with fastapi==0.135.4 --with starlette==0.52.1 \
  --with pydantic==2.10.6 --with httpx==0.28.1 --with PyYAML==6.0.2 \
  --with openai==3.29.0 --with numpy==1.26.4 \
  python -m unittest discover -s backend/tests -v
node backend/tests/test_preview_player.js
```

Live GPU recognition, real CPU classifier output, recorder replay and end-to-end
browser validation have not been run. The user will test after Darija integration;
no Studio access or fresh English validation is required for this implementation.
