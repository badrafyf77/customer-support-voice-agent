# Phase 5 — Browser conversation integration

The production Next.js frontend and `/ws` session path now handle Arabic transcript
direction, scoped Darija output, interruption before/during/between synthesized
phrases, visible model errors, reset, and runtime reuse. The chosen voice remains
**voice1 + main weights**. Live Studio acceptance is still deferred to the user.

## Behavior

Transcript paragraphs use `dir="auto"`, start alignment and plaintext bidi
handling. Arabic surrounds names, phone numbers, order IDs and decimals without
rewriting their characters. Quick and final assistant text update the same
message for a generation instead of merging unrelated partial turns.

The binary microphone packet is unchanged: big-endian uint32 timestamp and flags,
then 2048 signed PCM16 samples at the browser's 48 kHz capture rate. The existing
backend resampling and both audio worklets remain the playback/capture path.
Darija adds an optional numeric `generation_id` to existing assistant text, PCM
and interruption events. English events without that field remain supported.
The names `/ws`, `tts_chunk`, transcript events, `tts_start`, `tts_stop`,
`tts_interruption` and `stop_tts` are retained.

For Darija, finalized STT text commits the user turn. An earlier partial hypothesis
can be displayed, but does not replace the final recognized request sent to Atlas.
VAD recording start interrupts active or queued generation even before the
browser has received audio, and also interrupts when a completed response remains
in the browser's playback buffer. Darija microphone input stays active while the
assistant generates/speaks; existing echo cancellation and VAD settings remain.
During live testing, check echo rejection as well as deliberate barge-in.

Cancellation invalidates pending prepares, generated text and PCM. Queued output
is checked again before socket delivery. The browser rejects canceled/older
generations and ignores Stop messages for an older response once a newer one has
started. The worklet reports playback stopped when its buffer is cleared.
Generation-bound callbacks cannot mutate another turn or a newly leased session.
The existing STT dynamic timing formula and its latency floor are retained.

Model failures before first audio or during the remaining response send a visible
error and clear playback, then close the session for a clean reconnect. No other
model is substituted. A stopped STT worker or speech workers that failed to stop
cause retirement of the runtime rather than reuse. Session cleanup is shielded
from ASGI cancellation so a disconnect cannot strand a lease. Healthy runtimes
reset their history, queued prepares, callbacks and provider state before reuse.

Reset Transcript clears the session-owned conversation history and pending chat
turn as well as the UI and playback. A new socket starts with a fresh transcript;
late messages/close callbacks from the previous socket cannot change its state.
Stopping while microphone permission/setup is pending closes any stream that
arrives after cancellation.

## Later Studio browser run

Prepare all pinned artifacts using [README.md](README.md), start vLLM with
[ATLAS.md](ATLAS.md), and start SILMA with [SILMA.md](SILMA.md). Export the paths and
settings from `backend/.env.studio.example`, keeping HF_TOKEN in runtime secrets.
Then run the production backend on Studio:

```bash
"$DARIJA_STATE_ROOT/backend/bin/python" -m uvicorn server:app \
  --app-dir backend/code --host 127.0.0.1 --port 8080
```

On the local computer, open the tunnel using the actual Studio SSH alias:

```bash
ssh -N -o ExitOnForwardFailure=yes -L 8080:127.0.0.1:8080 STUDIO_SSH_ALIAS
npm --prefix frontend ci
npm --prefix frontend run dev
```

Open http://localhost:3000/?server=http://localhost:8080, choose Start and allow
microphone access. vLLM and SILMA ports remain internal. A localhost origin permits
browser microphone access. The independent vLLM memory budget remains provisional;
combined L4 memory/latency measurements belong to phase 6.

Record the results of this live sequence before claiming the exit check:

1. Start a conversation in Darija and continue for multiple turns. Check partial
   and final recognition, natural Darija replies and ordered phrase playback.
2. Give a name such as Sara or Jean-Luc, order AB-1203, phone 0612345678 and decimal
   12.50. Ask the assistant to repeat them; check both visible text and speech.
3. Use French/English terms in an otherwise Darija question. Review whether Atlas
   keeps the surrounding reply in Darija and asks for clarification when needed.
4. Interrupt while synthesis is pending, while audio plays, and between phrases.
   Immediately ask another question. Check that the canceled tail never returns,
   the quick phrase is not repeated, and the next response keeps its complete tail.
5. Reset the transcript mid-response. Disconnect/reconnect, then ask a new question.
   Check for prior text/audio, an old name recalled without context, or stuck capacity.
6. Stop during microphone setup. Repeat Start/Stop. Check that capture ends and no
   microphone stream remains active after Stop or a disconnected socket.
7. Stop Atlas or SILMA during a turn, then restore it. Confirm visible failure and
   clean reconnect, without fallback speech or a falsely completed final answer.
8. Test headphones and the intended speaker setup for echo-induced interruptions.
   Preserve VAD/timing constants until replay and live evidence justify a change.

Actual accent quality, intelligibility, acoustic interruption, sustained GPU
behavior and service latency have not been established by fake-PCM tests.

## Repeatable local checks

The local harness compiles the production session/runtime class bodies without
GPU/auth imports and uses the actual `SpeechPipelineManager`. Only the STT/model
boundaries and PCM are deterministic fakes. Its `/test/*` routes exist solely in
`backend/tests/support/session_harness.py`; production `server.py` has none.
Keep this harness on loopback and do not deploy it to Studio.

All **83 backend tests** pass against the locked backend web dependencies:

```bash
uv run --no-project --with fastapi==0.143.0 --with starlette==1.7.0 \
  --with pydantic==2.14.1 --with anyio==4.15.1 --with httpx==0.28.1 \
  --with PyYAML==6.0.2 --with openai==3.29.0 --with numpy==1.26.4 \
  python -m unittest discover -s backend/tests -v
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

The browser suite uses pinned Playwright, a real headless Chromium, synthetic
microphone capture, the production UI/worklets and the actual `/ws` session path.
For a repeat run, start this local harness in one terminal:

```bash
uv run --no-project --with fastapi==0.143.0 --with starlette==1.7.0 \
  --with pydantic==2.14.1 --with anyio==4.15.1 --with httpx==0.28.1 \
  --with PyYAML==6.0.2 --with openai==3.29.0 --with numpy==1.26.4 \
  --with uvicorn==0.54.0 --with websockets==15.0.1 \
  python -m uvicorn session_harness:app --app-dir backend/tests/support \
  --host 127.0.0.1 --port 8766
```

In another terminal:

```bash
npm --prefix frontend ci
frontend/node_modules/.bin/playwright install chromium --only-shell
npm --prefix frontend run dev -- --hostname 127.0.0.1 --port 3001
```

When both servers are ready:

```bash
npm --prefix frontend run test:browser
```

VOICE_TEST_FRONTEND and VOICE_TEST_SERVER can select alternative local test ports.
The suite saves an ignored screenshot under `frontend/tests/.artifacts/` and
reports that live models and audible quality were not tested. Ctrl-C stops the
two test servers. Saved verification scope is in
[phase5-verification.json](../../docs/darija/phase5-verification.json).
