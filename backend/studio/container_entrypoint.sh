#!/usr/bin/env bash
set -euo pipefail
studio_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
state_root="${DARIJA_STATE_ROOT:-/opt/darija}"
mode="${1:-backend}"
if [[ $# -gt 0 ]]; then shift; fi
case "$mode" in
    prepare)
        : "${HF_TOKEN:?Set HF_TOKEN in backend/.env with private-model read access}"
        if [[ ! -f /asr-export/model.bin ]]; then
            echo "Missing corrected ASR export. Set ASR_EXPORT_DIR in backend/.env to the folder containing model.bin and its four companion files." >&2
            exit 1
        fi
        exec "$state_root/backend/bin/python" "$studio_dir/prepare_models.py" \
            --root "${DARIJA_MODEL_ROOT:?}" --asr-export /asr-export "$@"
        ;;
    backend|vllm|silma)
        exec bash "$studio_dir/start_${mode}.sh" "$@"
        ;;
    *)
        exec "$mode" "$@"
        ;;
esac
