# server.py
import logging

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from agents.support.agent import build_support_agent
from core.config import get_env, load_agent_config
from core.logsetup import setup_logging
from core.session import lifespan, run_session

setup_logging(logging.INFO)
logger = logging.getLogger(__name__)

AGENT_NAME = get_env("VOICE_AGENT", "support") or "support"

app = FastAPI(lifespan=lifespan)
app.state.AGENT_NAME = AGENT_NAME

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def get_index() -> JSONResponse:
    """Return a small status payload for the voice backend."""
    return JSONResponse(
        {
            "service": "voice-agent-backend",
            "status": "ok",
            "websocket_path": "/ws",
        }
    )


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    brain = build_support_agent({})
    config = getattr(app.state, "AGENT_CONFIG", None) or load_agent_config(AGENT_NAME)
    config = {**config, "agent_name": AGENT_NAME}
    await run_session(websocket, brain, config, app.state)


if __name__ == "__main__":
    logger.info("🖥️▶️ Starting server without SSL.")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, log_config=None)
