#!/usr/bin/env bash
set -euo pipefail
studio_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
state_root="${DARIJA_STATE_ROOT:-/opt/darija}"
mode="${1:-backend}"
if [[ $# -gt 0 ]]; then shift; fi
case "$mode" in
    prepare)
        : "${HF_TOKEN:?Set HF_TOKEN in backend/.env with private-model read access}"
        case "${ASR_SOURCE:-huggingface}" in
            huggingface)
                "$state_root/asr-export/bin/python" "$studio_dir/export_asr.py" --root "${DARIJA_MODEL_ROOT:?}"
                asr_export="$DARIJA_MODEL_ROOT/asr"
                ;;
            local)
                asr_export=/asr-export
                if [[ ! -f "$asr_export/model.bin" ]]; then
                    echo "Set ASR_EXPORT_DIR and enable docker-compose.asr-local.yml for an existing export." >&2
                    exit 1
                fi
                ;;
            *)
                echo "ASR_SOURCE must be huggingface or local." >&2
                exit 1
                ;;
        esac
        exec "$state_root/asr-export/bin/python" "$studio_dir/prepare_models.py" \
            --root "${DARIJA_MODEL_ROOT:?}" --asr-export "$asr_export" "$@"
        ;;
    backend|vllm|silma)
        exec bash "$studio_dir/start_${mode}.sh" "$@"
        ;;
    *)
        exec "$mode" "$@"
        ;;
esac
