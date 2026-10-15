#!/usr/bin/env bash
set -euo pipefail
studio_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
state_root="${DARIJA_STATE_ROOT:-$studio_dir/.runtime}"
command -v uv >/dev/null || { echo "Install uv on the Studio before setup." >&2; exit 1; }
command -v nvidia-smi >/dev/null || { echo "Run setup on the NVIDIA L4 Studio." >&2; exit 1; }
mkdir -p "$state_root"
for environment in backend vllm silma; do
    uv venv --python 3.10 "$state_root/$environment"
    uv pip sync --python "$state_root/$environment/bin/python" "$studio_dir/$environment.lock"
done
echo "Environments prepared in $state_root"
