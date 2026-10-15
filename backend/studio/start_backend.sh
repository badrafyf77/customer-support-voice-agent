#!/usr/bin/env bash
set -euo pipefail
studio_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
state_root="${DARIJA_STATE_ROOT:-$studio_dir/.runtime}"
: "${DARIJA_MODEL_ROOT:?Source your Studio environment first}"
if [[ "${VOICE_PROFILE:-}" != darija || "${VOICE_AGENT:-}" != chat ]]; then
    echo "This launcher requires VOICE_PROFILE=darija and VOICE_AGENT=chat." >&2
    exit 1
fi
# RealtimeSTT subprocesses inherit these paths, including cuDNN 9 and cuBLAS.
cuda_libs="$("$state_root/backend/bin/python" -c 'import pathlib, site; print(":".join(str(p) for root in site.getsitepackages() for p in pathlib.Path(root).glob("nvidia/*/lib")))')"
export LD_LIBRARY_PATH="$cuda_libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$state_root/backend/bin/python" -m uvicorn server:app \
    --app-dir "$studio_dir/../code" --host 127.0.0.1 --port 8080 --workers 1
