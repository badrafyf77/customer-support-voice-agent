#!/usr/bin/env bash
set -euo pipefail
studio_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
state_root="${DARIJA_STATE_ROOT:-$studio_dir/.runtime}"
: "${DARIJA_MODEL_ROOT:?Set DARIJA_MODEL_ROOT to the prepared persistent model directory}"
: "${VLLM_GPU_MEMORY_UTILIZATION:?Set an explicit independent-load memory budget (e.g. 0.40); measure it on the L4}"
"${DARIJA_VALIDATION_PYTHON:-$state_root/backend/bin/python}" "$studio_dir/prepare_models.py" --root "$DARIJA_MODEL_ROOT" --roles llm --verify-only
"$state_root/vllm/bin/python" "$studio_dir/verify_atlas.py" --model-dir "$DARIJA_MODEL_ROOT/atlas"
exec "$state_root/vllm/bin/python" -m vllm.entrypoints.openai.api_server \
    --model "$DARIJA_MODEL_ROOT/atlas" \
    --tokenizer "$DARIJA_MODEL_ROOT/atlas" \
    --served-model-name MBZUAI-Paris/Atlas-Chat-2B \
    --host "${VLLM_BIND_HOST:-127.0.0.1}" --port 8001 \
    --dtype bfloat16 --max-model-len 4096 --max-num-seqs 1 \
    --generation-config "$DARIJA_MODEL_ROOT/atlas" \
    --override-generation-config '{"max_new_tokens":256}' \
    --gpu-memory-utilization "$VLLM_GPU_MEMORY_UTILIZATION"
