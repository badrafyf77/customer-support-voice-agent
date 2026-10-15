# Darija on Lightning L4

**Start with [DOCKER.md](DOCKER.md)** for the preferred Docker Compose deployment:
configure `backend/.env`, run Compose, expose the backend port in Lightning, and
set that URL in the local frontend's `.env.local`. No host Python setup or SSH
tunnel is required. [RUNBOOK.md](RUNBOOK.md) retains the optional native setup.
The older sections below retain artifact provenance and independent-load details.
Phase 6 tools are implemented; actual L4 tuning and live acceptance are pending
the user's Studio run. The selected voice is voice1 + main at 32 steps.

Phase 1 prepares pinned model artifacts and independent load checks.
[Phase 2 SILMA service and typed preview](SILMA.md) are now implemented; the user
selected voice1 + main weights. [Phase 3 Atlas streaming chat](ATLAS.md) is also
implemented, including typed multi-turn speech. [Phase 4 STT/turn integration](STT.md)
also enables the microphone path with verified artifacts and existing dynamic
timing. [Phase 5 browser integration and acceptance checks](BROWSER.md) are now
implemented and locally verified. Live Studio validation remains deferred.
Missing/mismatched artifacts fail first, with their identity and path.

Use the existing `codex/darija-voice-model-review` worktree, based on
`7adb0565186569420458bb32500e072f62c832ae`. No uncommitted changes from the main
checkout were copied. See [baseline](../../docs/darija/BASELINE.md) and
[plan](../../DARIJA_PLAN.md).

## Persistent state and isolated environments

Use an NVIDIA L4 Studio, Linux x86_64, Python 3.10, uv 0.10.11, ffmpeg,
libsndfile, PortAudio headers/runtime, a C/C++ toolchain, and CUDA development
tools for dependencies that build native extensions. A sufficiently recent NVIDIA
driver must support CUDA 12.4 for all three environments.
Do not install the three stacks into the same Python environment.

`backend.lock`, `vllm.lock`, and `silma.lock` pin resolved dependencies for Linux
and Python 3.10. These are resolved lockfiles, not proof of successful L4 installs.
The backend uses torch 2.6.0 and CTranslate2 4.6.0, matching the ASR export tooling's
CUDA 12.4/cuDNN 9 stack rather than requiring the old Docker system cuDNN 8.
SILMA uses torch 2.6.0 and
its inspected model requirements. vLLM 0.8.5 has its own torch 2.6.0 environment.
Backend Transformers is 4.51.3 to satisfy Coqui's dependency.
Native dependency builds must be checked on Studio.

From the repository root on Studio:

```bash
export DARIJA_STATE_ROOT=/teamspace/studios/this_studio/darija-runtime
export DARIJA_MODEL_ROOT=/teamspace/studios/this_studio/darija-models
export HF_HOME=/teamspace/studios/this_studio/darija-cache/huggingface
export TORCH_HOME=/teamspace/studios/this_studio/darija-cache/torch
bash backend/studio/setup.sh
```

Inject HF_TOKEN as a Lightning runtime secret with access to the private model
repositories. The scripts use Hugging Face's runtime token lookup; no credentials
belong in configuration, receipts, repository files, or command arguments.

## Model pins and provenance

Authoritative machine-readable pins: [models.lock.json](models.lock.json).

| Role | Model ID | Pinned revision |
| --- | --- | --- |
| STT adapter | afyfbadreddine77/whisper-large-v3-turbo-darija | e9ff459f2f5823d4f9093db8854c691eb78045d3 |
| STT base | openai/whisper-large-v3-turbo | 41f01f3fe87f28c78e2fbf8b568835947dd65ed9 |
| Turn detector | afyfbadreddine77/darija-turn-detection | a6b5bc2249d83bd0d05c5c4c3d8f5e1eafe204e4 |
| LLM full model | MBZUAI-Paris/Atlas-Chat-2B | a6244a4c50bc32b65c6c8dc4dc1dab218b580088 |
| SILMA TTS | afyfbadreddine77/silma-tts-darija | 2bac42dba12aba0d988ee5d5f8aa8d8b75397183 |
| Vocos | charactr/vocos-mel-24khz | 0feb3fdd929bcd6649e0e7c5a688cf7dd012ef21 |

Atlas and Vocos revisions were resolved through the Hugging Face model API on
13 October 2026. Atlas is downloaded as a complete model plus native tokenizer;
there is no LLM adapter. Its
[model card](https://huggingface.co/MBZUAI-Paris/Atlas-Chat-2B) documents direct loading.
The exact Atlas tokenizer/template and EOS configuration are retained in its snapshot.
System-role adaptation is implemented at the request boundary; see [ATLAS.md](ATLAS.md).

ASR pins and all five export hashes come from the inspected
`silma-tts/turn_detection/user_asr_other-export_result.json`.
That evidence records a nonzero merged adapter, FP16 CTranslate2 output, and no
training. It is the **correct model**, not the 125h export.
The exact model.bin SHA-256 is
`c130a5ee127bda0df5088ba815bddbe34b02f244903ab4da13a3460b28e49646`.
The saved processor specifies left padding; faster-whisper's right-padded feature
extraction was used in the comparison. Do not infer HF short-clip accuracy from
the saved processor without correcting its padding.

Turn hashes come from `hf_turn_publish_result.json`; SILMA hashes from
`research/hf_export_manifest.json` and revision from `research/hf_publish_result.json`.
Only the custom SILMA architecture loader was selectively adapted from
`hf_inference.py`; no research service, training pipeline, or session timing
changes were imported.

## Retrieve artifacts

On a Modal-authenticated machine with access to the original workspace, download
the known export. Create the destination directory first; Modal preserves the
remote leaf directory underneath it:

```bash
mkdir -p "$DARIJA_MODEL_ROOT/asr-download"
modal volume get darija-turn-detection user-asr-turbo-e9ff459f2f58/ctranslate2 "$DARIJA_MODEL_ROOT/asr-download"
"$DARIJA_STATE_ROOT/backend/bin/python" backend/studio/prepare_models.py \
  --root "$DARIJA_MODEL_ROOT" \
  --asr-export "$DARIJA_MODEL_ROOT/asr-download/ctranslate2"
```

If Studio has no Modal credentials, retrieve on an authenticated host and copy the
five exported files to that directory over SSH, then run preparation on Studio.
Do not point STT_MODEL at the HF LoRA repository. Do not substitute another export.
The script checks known ASR/turn/TTS hashes, downloads exact Atlas and Vocos
snapshots, records all file hashes in prepared.json, and only writes the readiness
receipt after every artifact passes. Re-running can reuse snapshot caches.
Receipts contain only model identities, revisions, sizes, and hashes.

```bash
"$DARIJA_STATE_ROOT/backend/bin/python" backend/studio/prepare_models.py \
  --root "$DARIJA_MODEL_ROOT" --verify-only
```

## Load each model independently

Run sequentially so one model is unloaded before the next; collect command
outputs and nvidia-smi readings in the phase 1 report:

```bash
"$DARIJA_STATE_ROOT/backend/bin/python" backend/studio/smoke_model.py stt --root "$DARIJA_MODEL_ROOT"
"$DARIJA_STATE_ROOT/backend/bin/python" backend/studio/smoke_model.py turn --root "$DARIJA_MODEL_ROOT"
"$DARIJA_STATE_ROOT/vllm/bin/python" backend/studio/smoke_model.py llm --root "$DARIJA_MODEL_ROOT"
"$DARIJA_STATE_ROOT/silma/bin/python" backend/studio/smoke_model.py tts --root "$DARIJA_MODEL_ROOT" --variant ema
```

Use `--audio /path/to/darija.wav` for an ASR transcription check.
Turn runs on CPU and checks finite two-class logits. STT, Atlas BF16, SILMA EMA,
and the pinned Vocos load on GPU. SILMA loads weights strictly using the supplied
custom architecture. This is not a TTS listening test or a calibrated turn-policy
test. The current turn probe now applies the phase 4 calibrated contract; recorder
replay and listening checks are separate.

For vLLM's independent service check, pick an explicit memory budget, for example
0.40 as a starting measurement, then:

```bash
export VLLM_GPU_MEMORY_UTILIZATION=0.40
bash backend/studio/start_vllm.sh
```

In another Studio terminal:

```bash
curl --fail http://127.0.0.1:8001/health
curl --fail http://127.0.0.1:8001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  --data '{"model":"MBZUAI-Paris/Atlas-Chat-2B","messages":[{"role":"user","content":"جاوب بالدارجة المغربية: السلام عليكم"}],"stream":true,"max_tokens":256}'
```

Ctrl-C stops it. The 0.40 budget is provisional for independent loading; combined
memory tuning is phase 6. Context is 4096, concurrency one, and the smoke request
caps output at 256. Both backend and server generation-cap enforcement are now implemented.
vLLM and the future SILMA service bind only to loopback, on 8001 and 8002.
SILMA now has its own HTTP service; see [SILMA.md](SILMA.md) for phase 2 commands.

## Local frontend tunnel and English baseline

Use the Studio's SSH connection instructions for the actual host/user/port:

```bash
ssh -N -o ExitOnForwardFailure=yes -L 8080:127.0.0.1:8080 STUDIO_SSH_ALIAS
```

The local frontend's `NEXT_PUBLIC_VOICE_SERVER_URL=http://localhost:8080`
continues to connect to /ws. Forward only the backend port.
For baseline measurements start the backend with VOICE_AGENT=chat,
VOICE_PROFILE=english, English STT and the English LLM service. Use [ATLAS.md](ATLAS.md) for the Darija client and native-template adaptation.
Bind the backend to Studio loopback:

```bash
cd backend/code
"$DARIJA_STATE_ROOT/backend/bin/python" -m uvicorn server:app --host 127.0.0.1 --port 8080
```

Copy [../.env.studio.example](../.env.studio.example) only when testing Darija
Darija startup. The microphone path now requires all verified model artifacts and
reachable Atlas/SILMA services; see [STT.md](STT.md).

## Phase 1 status

Implemented locally: selectable profile, corrected startup/route configuration,
artifact pins and provenance validation, isolated dependency locks, retrieval/load
scripts, internal vLLM command, tunnel instructions, and baseline capture protocol.

Deferred by user: Linux environment installation, independent GPU model load
outputs, vLLM streaming smoke test, and measured English audio/event baseline.
The user accepts the existing English behavior and will test on Studio after
Darija integration. This deliberate deferral does not imply the model loads or
Darija voice conversation have passed validation.
