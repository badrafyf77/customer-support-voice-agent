#!/usr/bin/env bash
set -euo pipefail
studio_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
state_root="${DARIJA_STATE_ROOT:-$studio_dir/.runtime}"
: "${DARIJA_MODEL_ROOT:?Set DARIJA_MODEL_ROOT to the prepared model directory}"
exec "$state_root/silma/bin/python" -m uvicorn silma_service:app \
    --app-dir "$studio_dir" --host 127.0.0.1 --port 8002 --workers 1
