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

## 2. Upload the ASR export once

The correct CTranslate2 export is not stored in Git or the HF adapter repository.
Upload the five files from this existing Mac folder using the Studio file browser
or your existing transfer method:

```text
/Users/afyfbadreddine/.codex/worktrees/darija-voice-model-review/customer-support-voice-agent/backend/studio/.models/asr-download/ctranslate2/
```

Place them in a Studio folder, for example:

```text
/teamspace/studios/this_studio/darija-asr-export/
  config.json
  model.bin
  preprocessor_config.json
  tokenizer.json
  vocabulary.json
```

Set `ASR_EXPORT_DIR` to that folder. `model.bin` is approximately 1.6 GB and its
SHA-256 must be
`c130a5ee127bda0df5088ba815bddbe34b02f244903ab4da13a3460b28e49646`.
The preparation container verifies every file; the 125h export is not accepted.
If the folder is already on Studio, just point `.env` to it. No transfer is needed
for Atlas, turn detection, SILMA or Vocos; Compose downloads those automatically.

## 3. Configure .env

```bash
cp -n .env.example .env
```

Edit **backend/.env** in Studio:

```dotenv
HF_TOKEN=your_hugging_face_read_token
ASR_EXPORT_DIR=/teamspace/studios/this_studio/darija-asr-export
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

The token needs read access to your private turn/TTS model repositories. `.env` is
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

Compose builds three isolated pinned CUDA 12.4/Python 3.10 stacks. It runs the
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

# Apply .env changes (restart alone does not re-read environment values)
docker compose up -d

# Rebuild after a code update
git pull --ff-only
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

- Missing bind folder: fix `ASR_EXPORT_DIR` to the actual Studio folder. A missing
  directory is rejected instead of silently creating an empty one.
- Preparation failure: inspect `docker compose logs prepare-models`; check the
  token's private-model access or the export hash. After correcting it, rerun up.
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
