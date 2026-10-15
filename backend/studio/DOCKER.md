# Docker Compose on Lightning; frontend on your computer

This is the preferred deployment for this branch. Your Studio already has Docker,
Compose and NVIDIA support. No host Python/uv environments, tmux or SSH tunnel
are needed. Runtime configuration, including `HF_TOKEN`, goes in **backend/.env**.

## 1. Get the code on Studio

For a new clone, in the Studio terminal:

```bash
cd /teamspace/studios/this_studio
git clone --branch codex/darija-voice-model-review --single-branch \
  https://github.com/badrafyf77/customer-support-voice-agent.git
cd customer-support-voice-agent/backend
```

For an existing Darija deployment clone, enter it, run `git pull --ff-only`, then
`cd backend`. All following Compose commands run from **backend/**.

## 2. Automatic ready-to-run ASR preparation from Hugging Face

No manual export upload or Modal credentials are required. The selected model is
`afyfbadreddine77/whisper-large-v3-turbo-darija`, adapter revision
`e9ff459f2f5823d4f9093db8854c691eb78045d3`. Its pinned HF repository contains
the trained LoRA adapter. The setup container automatically:

1. Downloads `openai/whisper-large-v3-turbo` at the pinned base revision and
   the selected Darija adapter directly from Hugging Face.
2. Checks that the intended trained, nonzero LoRA weights loaded, then safely
   merges them on CPU. No training or GPU job is performed.
3. Saves the processor/tokenizer and converts the merged model to FP16
   CTranslate2, using the original export recipe's isolated pinned toolchain.
4. Checks all five files against the known correct export's size/SHA-256 before
   publishing them to the persistent model volume. A mismatch fails setup.

The expected `model.bin` SHA-256 remains
`c130a5ee127bda0df5088ba815bddbe34b02f244903ab4da13a3460b28e49646`.
The separate 125h model is not used. Later starts reuse verified ready-to-run
files without repeating the merge/conversion. The other models are downloaded
at their pinned HF revisions as before.

This preparation runs automatically as part of `docker compose up -d --build`,
after image builds and before inference services start. Private downloads use
runtime `.env` credentials; image layers contain code/dependencies. The first
setup requires CPU memory/disk for the base, adapter, merge and conversion.

## 3. Configure .env

```bash
cp -n .env.example .env
```

Edit **backend/.env** in Studio:

```dotenv
HF_TOKEN=your_hugging_face_read_token
ASR_SOURCE=huggingface
ASR_EXPORT_CPU_THREADS=4
BACKEND_PORT=8080
VLLM_GPU_MEMORY_UTILIZATION=0.40
SILMA_VOICE_ID=voice1
SILMA_CHECKPOINT_VARIANT=main
SILMA_REQUEST_TIMEOUT_SECONDS=120
LOG_LEVEL=INFO
MAX_AUDIO_QUEUE_SIZE=50
VLLM_STARTUP_TIMEOUT_SECONDS=1200
VLLM_HEALTHCHECK_INTERVAL_SECONDS=2
```

The token needs read access to your private ASR adapter, turn and TTS repositories. `.env` is
ignored by Git and Docker's build context; it is injected only at container runtime.
Models and caches persist in named Docker volumes. You do not need Lightning
Secrets, OpenAI credentials or Supabase credentials for general Darija chat.

`0.40` is the first L4 memory-budget candidate, not a measured safe allocation.
The selected voice remains voice1/main at 32 steps; one conversation is allowed.
Internal model paths, profile and service URLs are supplied by Compose, so do not
copy the host/native `.env.studio` over this file.

## 4. Build and start

```bash
docker compose up -d --build
docker compose ps -a
docker compose logs -f
```

Compose builds four isolated pinned Python 3.10 environments: CPU model
preparation, backend, vLLM and SILMA. The GPU images use CUDA 12.4. It runs the
preparation container first, starts vLLM after preparation succeeds, then starts
SILMA and finally the voice backend when their predecessors are healthy. The first
build/download can take time. The completed preparation container should show
**Exited (0)**; that is expected. The three live services should become healthy.

Only the backend is published on Studio, by default **8080**. Atlas and SILMA have
no host port mappings. Check the backend:

```bash
curl --fail http://localhost:8080/
```

Expected fields include `status: ok`, `voice_profile: darija`, `runtime.total: 1`
and `runtime.max_concurrent: 1`.

## 5. Expose the backend port in Lightning

Open the Studio's **Ports** panel/plugin and expose **8080**, or the value you
chose for `BACKEND_PORT`. Copy its browser-accessible HTTPS URL. Make the port
accessible to the browser running your frontend; a Studio login redirect is not
the voice endpoint. The URL's root should show the JSON status above.

Use this base HTTPS URL in the local frontend. The frontend already changes
`https://…` to `wss://…/ws` for its WebSocket connection. Do not expose ports 8001
or 8002 and do not add `/ws` to the frontend environment value.

Lightning's [port-sharing documentation](https://lightning.ai/docs/platform/build/host-web-apps)
describes exposing an application through the port plugin. Docker's
[GPU Compose documentation](https://docs.docker.com/compose/how-tos/gpu-support/)
and [environment file documentation](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/)
describe the configuration used here.

## 6. Run the frontend locally

In your **local Mac terminal**:

```bash
cd /Users/afyfbadreddine/.codex/worktrees/darija-voice-model-review/customer-support-voice-agent
npm --prefix frontend ci
cp -n frontend/.env.example frontend/.env.local
```

Edit **frontend/.env.local**:

```dotenv
NEXT_PUBLIC_VOICE_SERVER_URL=https://YOUR-LIGHTNING-BACKEND-URL
```

Then:

```bash
npm --prefix frontend run dev
```

Open http://localhost:3000, press Start, and allow microphone access. Restart Next
after changing `.env.local`. Clear an old `?server=` URL override if present; use
the plain localhost URL so the environment setting is selected.

On another local PC, clone the same branch first, then use its `frontend/`
directory. Local GPU/Python/model installations are not required.

## Daily commands

From Studio's `backend/`:

```bash
# Status and logs
docker compose ps -a
docker compose logs -f app
docker compose logs --tail=100 prepare-models vllm silma

# Apply .env changes; stop first to preserve GPU loading/profiling order.
docker compose down
docker compose up -d

# Rebuild after a code update
git pull --ff-only
docker compose down
docker compose up -d --build

# Stop/remove containers; named model/cache volumes remain
docker compose down
```

Avoid `docker compose down -v` unless you intend to delete downloaded models and
caches. To check artifacts again without starting duplicate GPU runtimes:

```bash
docker compose run --rm --no-deps app \
  /opt/darija/backend/bin/python /app/studio/prepare_models.py \
  --root /models --verify-only
```

## Troubleshooting and phase 6 measurements

- Preparation failure: inspect `docker compose logs prepare-models`; check the
  token's private-model access, CPU memory/disk or export hash. A provenance
  mismatch must not be bypassed. After correcting the cause, rerun up.
- GPU OOM: inspect the failing service and `nvidia-smi`. The allocation is still
  provisional. Stop the stack before changing the budget and repeat the combined
  run; do not increase worker/conversation counts or restore the old 80% setting.
- Frontend cannot connect: check the exposed URL's JSON in your local browser,
  port visibility, `.env.local`, and any old `?server=` override.
- Local microphone: allow permission for localhost, then Stop/Start again.

Existing browser timing/checklist tools still apply. For service benchmarks with
all models resident, disconnect the frontend and run:

```bash
docker compose exec -T app /opt/darija/backend/bin/python \
  /app/studio/measure.py benchmark --output /cache/measurements/l4-first-probes
```

For GPU sampling in another Studio terminal (uses the already installed driver):

```bash
nvidia-smi --query-gpu=timestamp,name,memory.used,memory.free,utilization.gpu \
  --format=csv -l 1 > darija-gpu.csv
```

Ctrl-C ends sampling. Retrieve benchmark WAVs/results with `docker compose cp
app:/cache/measurements/l4-first-probes ./l4-first-probes`. Put private captures
outside Git. Live model/voice quality, combined L4 memory and acoustic latency
remain pending your Studio test. Local Compose configuration checks do not prove
a successful Linux GPU image build or live conversation.

The previous English Compose recipe remains in `docker-compose.english.yml`
with its old template `.env.english.example`. The native/non-Docker alternative
remains in [RUNBOOK.md](RUNBOOK.md); it is not required for this setup.

## Build and startup organization

`Dockerfile.darija` separates shared system dependencies, four isolated dependency
stages, one shared source stage, and four final targets. Each dependency stage
copies only its lockfile before installation, so source edits preserve the
expensive dependency cache. BuildKit may build independent stages concurrently;
their `FROM`/`COPY --from` dependencies define the build graph.

| Target | Dependency lock | Responsibility |
| --- | --- | --- |
| `prepare` | `studio/asr-export.lock` | HF base/adapter merge, CT2 conversion and model preparation |
| `vllm` | `studio/vllm.lock` | Atlas inference |
| `silma` | `studio/silma.lock` | Selected voice inference |
| `backend` | `studio/backend.lock` | STT/turn/session HTTP and WebSocket server |

`docker-compose.yml` owns startup ordering and readiness:

```text
prepare-models exits successfully -> vllm healthy -> silma healthy -> app starts
```

Shared build, healthcheck, environment and GPU settings are declared once at the
top. Each service declares its own target, command and predecessor. Only
`prepare-models` can write the model volume; inference services mount it read-only.
`container_entrypoint.sh` dispatches commands, while `export_asr.py` owns the
Python conversion and cache/validation logic. No inference stack imports PEFT.

## Optional existing-export mode

If a verified export is already on Studio, set `ASR_EXPORT_DIR` in `.env` and use
the explicit override instead of automatic HF conversion:

```bash
docker compose -f docker-compose.yml -f docker-compose.asr-local.yml up -d --build
```

The override sets `ASR_SOURCE=local` and mounts the source read-only. The default
setup above has no local model bind mount and only needs `HF_TOKEN`.
