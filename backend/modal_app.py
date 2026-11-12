"""Run the voice backend on Modal (serverless GPU), as an alternative to docker compose.

Modal builds the image from our Dockerfile, starts one GPU container when someone
connects, and serves the same FastAPI app (``code/server.py``), WebSocket
included, at a public HTTPS address. The container stops after 5 idle minutes,
so nothing is billed while nobody uses it.

From ``backend`` (with the Modal CLI logged in):

    modal serve modal_app.py      # testing: runs until you press Ctrl+C
    modal deploy modal_app.py     # keeps the address until `modal app stop shopeasy-voice-agent`

Settings:
- Keys come from ``backend/.env`` when you run the command: only the names in
  ``SECRET_KEYS`` are sent to Modal, never the whole file.
- ``MODAL_GPU`` picks the GPU (default ``L4``; ``T4`` is a little cheaper).
- Trace files are kept on the Modal volume ``shopeasy-voice-state``:
  ``modal volume get shopeasy-voice-state traces/<session_id>.jsonl``
- The ShopEasy database is rebuilt fresh in each new container.
"""
from __future__ import annotations

import os
from pathlib import Path

import modal

BACKEND = Path(__file__).resolve().parent
APP_NAME = "shopeasy-voice-agent"
GPU = os.getenv("MODAL_GPU", "L4")
STATE_DIR = "/state"
SECRET_KEYS = [
    "OPENAI_API_KEY",
    "LANGSMITH_TRACING",
    "LANGSMITH_API_KEY",
    "LANGSMITH_PROJECT",
    "LANGSMITH_ENDPOINT",
]


def _secret_values() -> dict[str, str]:
    """Only the settings the server needs, from the environment or backend/.env."""
    file_values: dict[str, str | None] = {}
    env_file = BACKEND / ".env"
    if env_file.exists():
        try:
            from dotenv import dotenv_values

            file_values = dotenv_values(env_file)
        except ImportError:
            pass
    values = {key: os.environ.get(key) or file_values.get(key) for key in SECRET_KEYS}
    return {key: value for key, value in values.items() if value}


image = modal.Image.from_dockerfile(
    BACKEND / "Dockerfile",
    context_dir=BACKEND,
    # Never upload local-only folders or the .env file into the image.
    ignore=[".venv", ".env", "logs", "data", ".langgraph_api", ".pytest_cache", "tests", "**/__pycache__"],
)
# The Dockerfile's entrypoint switches to the non-root `appuser`. Modal's own
# start-up code then can't reach Modal ("Permission denied"), so clear it here.
# Modal's (legacy) image builder also installs an older typing_extensions over
# ours, which breaks anyio/FastAPI, so upgrade it again afterwards.
image = image.entrypoint([]).run_commands("pip install --no-cache-dir -U typing_extensions").env(
    {
        "LLM_PROVIDER": "openai",
        "VOICE_AGENT": "support",
        "TRACE_DIR": f"{STATE_DIR}/traces",
        "SHOP_DB_PATH": "/tmp/shop.db",
        "PYTHONPATH": "/app/code",
        "TURN_DETECTION_DEVICE": "cuda",
    }
)

app = modal.App(APP_NAME)
state = modal.Volume.from_name("shopeasy-voice-state", create_if_missing=True)


@app.function(
    image=image,
    gpu=GPU,
    secrets=[modal.Secret.from_dict(_secret_values())],
    volumes={STATE_DIR: state},
    max_containers=1,  # the voice backend handles one call per GPU
    scaledown_window=300,  # stop after 5 idle minutes
    timeout=20 * 60,  # one WebSocket call can last up to 20 minutes (the agent ends it at 15)
    startup_timeout=15 * 60,  # loading the speech models takes a while
)
@modal.concurrent(max_inputs=8)  # one call plus status requests; extra calls get "busy"
@modal.asgi_app()
def web():
    import threading
    import time

    os.chdir("/app/code")
    os.makedirs(f"{STATE_DIR}/traces", exist_ok=True)

    def save_traces_regularly() -> None:
        # Volume changes are saved when the container stops; also save every
        # 30 s so trace files can be downloaded during a test.
        while True:
            time.sleep(30)
            try:
                state.commit()
            except Exception:
                pass

    threading.Thread(target=save_traces_regularly, daemon=True).start()

    from server import app as fastapi_app

    return fastapi_app
