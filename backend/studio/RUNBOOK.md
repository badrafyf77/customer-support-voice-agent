# Optional native deployment on Lightning L4

**The requested deployment is now [Docker Compose with .env and an exposed
Lightning port](DOCKER.md).** Use that guide for the simple setup. The instructions
below retain the alternative native/SSH workflow and are not needed for Compose.

Branch: `codex/darija-voice-model-review`. Selected speech: **voice1 + main, 32 steps**.
One Studio, one GPU, one conversation; turn detection/VAD run on CPU.
The native isolated environments below are an alternative to the Darija Compose
images. The old English Docker recipe is kept separately.

Phase 6 supplies repeatable launch and measurement tools. **The Linux installs,
combined L4 budget, actual recognition, speech quality and live latency remain
unvalidated until your Studio run.** `0.40` is the first candidate budget, not a
measured production recommendation. No English latency comparison was collected.

## 1. Prepare the Studio

Choose an NVIDIA **L4** Studio. Add `HF_TOKEN` as a Lightning Secret with read
access to the private ASR, turn and TTS repositories. Open a new Studio terminal
after adding the secret. Do not paste tokens into repository files or commands.
General chat needs no OpenAI, Supabase or exam credentials.

Lightning documentation: [secrets](https://lightning.ai/docs/platform/security/security-features/secrets)
and [SSH setup](https://api.lightning.ai/docs/platform/build/ai-studio/ssh-access).
Use the Studio's **Connect via SSH** instructions on your local computer; save
the resulting SSH alias. Commands below use `STUDIO_SSH_ALIAS` as a placeholder
for that alias, including any port/identity configuration supplied by Lightning.

In the **Studio terminal**:

```bash
cd /teamspace/studios/this_studio
git clone --branch codex/darija-voice-model-review --single-branch \
  https://github.com/badrafyf77/customer-support-voice-agent.git \
  customer-support-voice-agent-darija
cd customer-support-voice-agent-darija
git rev-parse HEAD
nvidia-smi
```

If you already have this deployment clone, enter it and use `git pull --ff-only`.
Keep the deployment clone separate from another checkout with local edits.
Use your usual GitHub authentication if Git prompts for access.

Install system libraries and the pinned environment manager once:

```bash
sudo apt-get update
sudo apt-get install -y build-essential python3-dev ffmpeg libsndfile1 \
  libportaudio2 portaudio19-dev tmux
python3 -m pip install --user uv==0.10.11
export PATH="$HOME/.local/bin:$PATH"
uv --version
nvcc --version
```

The Studio must have CUDA development tools and a driver compatible with CUDA
12.4; `nvidia-smi`'s CUDA field alone does not confirm that `nvcc` is installed.
Use the Studio CUDA toolkit if already provided. The Python locks target Linux
x86_64/Python 3.10 and torch 2.6.0. Some dependencies build native extensions.

## 2. Create environments and configuration

Still in the **Studio repository root**:

```bash
cp backend/.env.studio.example backend/.env.studio
set -a
source backend/.env.studio
set +a
bash backend/studio/setup.sh
```

Setup creates three persistent environments under
`/teamspace/studios/this_studio/darija-runtime/{backend,vllm,silma}` and installs
their separate resolved locks. Do not activate or merge them together. Exported
settings go to all child processes; `.env.studio` contains paths/configuration,
not your Hugging Face token. Run the `set -a/source/set +a` block again in each
new Studio terminal. Keep these configured values:

| Setting | Value |
| --- | --- |
| `VOICE_AGENT` / `VOICE_PROFILE` | `chat` / `darija` |
| `SILMA_VOICE_ID` / `SILMA_CHECKPOINT_VARIANT` | `voice1` / `main` |
| `VOICE_RUNTIME_MIN_WARM` / `VOICE_RUNTIME_MAX_CONCURRENT` | `1` / `1` |
| `VLLM_GPU_MEMORY_UTILIZATION` | `0.40` candidate; validate below |
| Backend / Atlas / SILMA ports | `8080` / `8001` / `8002`, all loopback |

The ASR and turn paths in the example point to persistent prepared artifacts.
If you change `DARIJA_MODEL_ROOT`, update `STT_MODEL`, `STT_REALTIME_MODEL` and
`TURN_DETECTION_MODEL` consistently. Keep `TURN_DETECTION_DEVICE=cpu`.

## 3. Transfer the correct ASR export from this Mac

The 1.6 GB CTranslate2 export is intentionally excluded from Git. It already
exists on this Mac, so no Modal setup is needed for this transfer. Run the
following in a **local Mac terminal**, replacing `STUDIO_SSH_ALIAS`:

```bash
ssh STUDIO_SSH_ALIAS 'mkdir -p /teamspace/studios/this_studio/darija-models/asr-download/ctranslate2'
rsync -avP \
  /Users/afyfbadreddine/.codex/worktrees/darija-voice-model-review/customer-support-voice-agent/backend/studio/.models/asr-download/ctranslate2/ \
  STUDIO_SSH_ALIAS:/teamspace/studios/this_studio/darija-models/asr-download/ctranslate2/
```

The source directory must contain `model.bin`, `config.json`,
`preprocessor_config.json`, `tokenizer.json` and `vocabulary.json`. The expected
`model.bin` SHA-256 is
`c130a5ee127bda0df5088ba815bddbe34b02f244903ab4da13a3460b28e49646`.
Do not use the 125h export or point faster-whisper at the HF adapter repository.
If moving from another PC, copy these five files from the Mac first or retrieve
the exact Modal export using [README.md](README.md#retrieve-artifacts).

Back in the **Studio repository root**, with its environment sourced:

```bash
"$DARIJA_STATE_ROOT/backend/bin/python" backend/studio/prepare_models.py \
  --root "$DARIJA_MODEL_ROOT" \
  --asr-export "$DARIJA_MODEL_ROOT/asr-download/ctranslate2"
"$DARIJA_STATE_ROOT/backend/bin/python" backend/studio/prepare_models.py \
  --root "$DARIJA_MODEL_ROOT" --verify-only
```

This checks the export, copies it to `darija-models/asr`, downloads the pinned
turn/Atlas/SILMA/Vocos snapshots and writes `prepared.json` only after validation.
Allow time and disk space for weights, caches, and the three Python stacks.
It does not download substitute models on a failed private download.

## 4. Start the complete backend stack

In a **Studio terminal**, enter the repository and start a persistent terminal:

```bash
tmux new -s darija
```

Inside tmux, from the Studio repository root:

```bash
set -a
source backend/.env.studio
set +a
export DARIJA_RUN_DIR="$DARIJA_STATE_ROOT/runs/l4-first-run"
"$DARIJA_STATE_ROOT/backend/bin/python" backend/studio/run_stack.py \
  --output "$DARIJA_RUN_DIR"
```

The output directory must be **new**; choose `l4-run-02`, etc. for another run.
Wait for **All services ready**. First startup includes model loading, CUDA
initialization, TTS reference/model warmup and backend warmup. The supervisor
starts GPU monitoring, Atlas, SILMA, then the single voice runtime. It fails if
a port is occupied or any child exits. Use one supervisor and one backend worker.

Detach without stopping: **Ctrl-B**, then **D**. Reattach:

```bash
tmux attach -t darija
```

In another **Studio terminal**, inspect readiness and logs:

```bash
curl --fail http://127.0.0.1:8001/health
curl --fail http://127.0.0.1:8002/health
curl --fail http://127.0.0.1:8080/
tail -n 80 /teamspace/studios/this_studio/darija-runtime/runs/l4-first-run/backend.log
```

The backend should report `voice_profile=darija`, one runtime and
`max_concurrent=1`. SILMA health should show `voice1`, `main`, `steps=32` and the
pinned model identities. Backend startup logs list verified ASR/turn identities.
Atlas is served as `MBZUAI-Paris/Atlas-Chat-2B`, BF16/context 4096/response cap 256.

## 5. Connect the frontend on your local computer

In a **local terminal**, keep this tunnel running:

```bash
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L 8080:127.0.0.1:8080 STUDIO_SSH_ALIAS
```

Only forward 8080. vLLM and SILMA stay internal. In another **local terminal**,
use the existing Darija worktree on this Mac:

```bash
cd /Users/afyfbadreddine/.codex/worktrees/darija-voice-model-review/customer-support-voice-agent
node --version
npm --prefix frontend ci
cp frontend/.env.example frontend/.env.local
npm --prefix frontend run dev
```

The local verified Node version is **26.5.0**; use a compatible installed Node
version if you already have one. `frontend/.env.local` must contain:

```dotenv
NEXT_PUBLIC_VOICE_SERVER_URL=http://localhost:8080
```

If working on a different PC, clone the same branch into a new local directory
and run the frontend commands there. No Python, CUDA or model weights are needed
on the frontend computer. Restart Next after editing its environment file.

Open **http://localhost:3000/?server=http://localhost:8080**, choose **Start** and
allow microphone access. Localhost supports browser microphone permissions.
Use headphones for the first run, then check the intended speaker setup for
echo. The frontend uses `/ws`; no exam/user query parameters are needed.
Optional production frontend: `npm --prefix frontend run build`, then
`npm --prefix frontend start` instead of `run dev`.

## 6. Measure and validate before tuning

Keep the complete backend running. Disconnect the browser session before direct
service probes. In a **second Studio terminal**, from the repo root:

```bash
set -a
source backend/.env.studio
set +a
export DARIJA_RUN_DIR="$DARIJA_STATE_ROOT/runs/l4-first-run"
"$DARIJA_STATE_ROOT/backend/bin/python" backend/studio/measure.py benchmark \
  --output "$DARIJA_RUN_DIR/probes" --repeats 3
```

These probes require an idle, warmed Darija backend with exactly one resident
runtime. They measure first spoken Atlas text and first SILMA PCM, sequentially
and with Atlas/TTS overlapping. STT remains resident; native microphone STT load
is exercised separately by the browser conversation. Saved WAVs need listening
review; real-time factor below 1 alone does not establish acceptable phrase gaps.

For browser timing, open DevTools **before Start**, paste the contents of
`backend/studio/browser_trace.js` from this repository, then run:

```javascript
voiceTrace.controls()
```

Use **Mark utterance end** when you finish speaking. Use **Mark interruption
start** as you begin a deliberate interruption. These are timing marks only;
speak normally to exercise actual VAD interruption. Complete the eight live
checks in [BROWSER.md](BROWSER.md#later-studio-browser-run), including interruptions
before audio, during playback and between phrases, immediate next turns, IDs,
reset/reconnect, service failure recovery and speaker echo checks. Continue for
at least 30 minutes to inspect sustained memory behavior. A second browser
session must receive a clear capacity error while the first remains usable.

Click **Save timing trace**. From your local terminal, upload the downloaded file:

```bash
scp ~/Downloads/browser-trace.json \
  STUDIO_SSH_ALIAS:/teamspace/studios/this_studio/darija-runtime/runs/l4-first-run/browser-trace.json
```

In the **Studio terminal**, create the measured summary:

```bash
"$DARIJA_STATE_ROOT/backend/bin/python" backend/studio/measure.py report \
  --gpu "$DARIJA_RUN_DIR/gpu.jsonl" \
  --services "$DARIJA_RUN_DIR/probes/services.json" \
  --browser "$DARIJA_RUN_DIR/browser-trace.json" \
  --output "$DARIJA_RUN_DIR/summary.json"
```

Stop the supervisor first for a final GPU-file snapshot; the report can also be
run on the growing file during testing, but avoid reading a partially written
last line. GPU sampling is every 0.5s and can miss short peaks. Compare memory at
equivalent **warmed idle** points; cold-to-warm growth is not a leak. The trace
measures worklet rendering callbacks, not physical speaker output. Manual marks
include human timing error; hardware loopback recording is required for precise
acoustic interruption/first-audible latency. Raw Atlas tokenizer TTFT may differ
from first **spoken** text because role-marker filtering can withhold characters.

Use [MEASUREMENT_REPORT.md](MEASUREMENT_REPORT.md) to record the human review and
settings alongside `run.json`, `summary.json`, logs and WAVs. The tools deliberately
leave final acceptance pending. Do not commit private transcripts/audio or runtime
reports automatically; outputs under `DARIJA_STATE_ROOT` stay outside the repo.

For precise STT endpoint replay, stop the stack first, then follow
[STT.md](STT.md)'s manifest/replay commands. That replay creates its own recorder;
do not load a duplicate STT model alongside the live backend.

Tuning order:

1. Verify the first combined run loads and sustains conversation without OOM.
   Inspect the minimum free GPU memory during overlapping probes and live turns.
   `0.40` is a candidate; if memory is insufficient, stop the stack, lower the
   budget explicitly (e.g. `0.35`) and repeat in a new run directory. If vLLM
   cannot fit its model/KV cache, inspect its startup error before changing it.
2. Establish selected-voice intelligibility at 32 steps and inspect phrase gaps,
   reference caching, warmup and buffering. Reference/model caches and bounded
   phrase queues are already implemented. Make changes only with a reproducible
   case and a before/after run under equivalent conditions.
3. Keep 32 steps for this release until paired listening evidence supports fewer
   steps. Reduced-step benchmarking/adoption is intentionally deferred until
   that baseline; current startup checks enforce 32.
4. Keep concurrency one, existing VAD and dynamic endpoint timing. Do not restore
   the old 80% vLLM allocation or claim a tested budget from a successful boot.

## 7. Stop, restart and troubleshoot

- Stop frontend: **Ctrl-C** in its local terminal.
- Stop tunnel: **Ctrl-C** in the tunnel terminal.
- Stop backend: reattach tmux and **Ctrl-C** the supervisor. It gracefully stops
  its own backend/SILMA/vLLM process groups, then force-stops them after 30s if
  needed. GPU samples and logs remain. Stopping tmux alone is not the stop command.
- Restart: source `.env.studio`, choose a new run directory, repeat step 4.
- Stop the Lightning GPU instance when finished to end its runtime charges.

| Symptom | Action |
| --- | --- |
| Model 401/403 or pinned snapshot unavailable | Check `HF_TOKEN` secret/access, reopen terminal, rerun preparation. |
| ASR hash mismatch | Transfer the exact five files again; do not bypass validation. |
| `libcudnn`/`libcublas` missing | Use `start_backend.sh`; it exports the backend environment's NVIDIA library paths to recorder subprocesses. Check successful locked torch installation. |
| Native dependency build fails | Check Python 3.10, PortAudio/toolchain/ffmpeg and CUDA headers; retain install error instead of silently changing pins. |
| Stack startup fails | Inspect the named service log in the run directory and `nvidia-smi`; all owned children are stopped. |
| Local 8080 already occupied | Stop the old tunnel, or forward `18080:127.0.0.1:8080` and set frontend server to `http://localhost:18080`. |
| Frontend never becomes ready | Check local `curl http://localhost:8080/`, tunnel, Studio backend log and profile. |
| Capacity after closing a tab | Wait for cleanup; inspect backend lease/reset log. A failed runtime is retired. Do not add workers. |
| Microphone denied | Allow localhost microphone access in browser settings; press Stop, then Start. |

For updates, stop the stack, `git pull --ff-only`, and rerun setup/model preparation
only when locks/pins changed. Keep the deployed Git commit in the measurement
report so results can be reproduced.
