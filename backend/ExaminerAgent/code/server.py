# server.py
from datetime import datetime, timezone
import logging

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from agents.exam.agent import build_exam_agent
from core.config import load_agent_config
from core.logsetup import setup_logging
from core.session import lifespan, run_session
from services import database

setup_logging(logging.INFO)
logger = logging.getLogger(__name__)

AGENT_NAME = "exam"

app = FastAPI(lifespan=lifespan)
app.state.AGENT_NAME = AGENT_NAME

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/voice-reference")
async def check_voice_reference(user_id: str):
    """Return whether a permanent voice reference exists for a user."""
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    db = database.get_database_client()
    payload = db.get_user_voice_reference(user_id)
    return JSONResponse({"exists": bool(payload)})


@app.post("/voice-reference")
async def upload_voice_reference(
    user_id: str = Form(...),
    audio: UploadFile = File(...),
):
    """
    Receive a short voice sample, extract a SpeechBrain ECAPA-TDNN embedding,
    and persist it permanently on the user's profile.
    """
    from services.speaker_verification import (
        DEFAULT_MATCH_THRESHOLD,
        embedding_to_list,
        extract_embedding_from_wav_bytes,
    )

    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    blob = await audio.read()
    if not blob:
        raise HTTPException(status_code=400, detail="Empty audio upload")

    try:
        embedding = extract_embedding_from_wav_bytes(blob)
    except Exception as exc:
        logger.exception("🗣️🔐 Failed to extract voice reference embedding: %s", exc)
        raise HTTPException(status_code=500, detail=f"Embedding failure: {exc}") from exc

    if embedding is None:
        raise HTTPException(
            status_code=422,
            detail="Could not produce an embedding. Please record at least 2 seconds of clear speech.",
        )

    payload = {
        "embedding": embedding_to_list(embedding),
        "model": "speechbrain/spkrec-ecapa-voxceleb",
        "threshold": DEFAULT_MATCH_THRESHOLD,
        "enrolled_at": datetime.now(timezone.utc).isoformat(),
        "audio_bytes": len(blob),
    }

    db = database.get_database_client()
    saved = db.update_user_voice_reference(user_id, payload)

    return JSONResponse(
        {
            "ok": True,
            "saved": saved,
            "embedding_dim": len(payload["embedding"]),
        }
    )


@app.get("/")
async def get_index() -> JSONResponse:
    """Return a small status payload for the standalone examiner backend."""
    return JSONResponse(
        {
            "service": "examiner-agent",
            "status": "ok",
            "websocket_path": "/ws",
            "voice_reference_path": "/voice-reference",
        }
    )


@app.websocket("/ws")
async def ws_endpoint(
    websocket: WebSocket,
    user_id: str = None,
    exam_id: str = None,
    attempt_id: str = None,
):
    context = await database.load_session_context(user_id, exam_id, attempt_id)
    brain, _initial_state = build_exam_agent(context)
    config = getattr(app.state, "AGENT_CONFIG", None) or load_agent_config(AGENT_NAME)
    config = {**config, "agent_name": AGENT_NAME}
    await run_session(websocket, brain, config, app.state, user_id, context.get("exam_id"), attempt_id)


if __name__ == "__main__":
    logger.info("🖥️▶️ Starting server without SSL.")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, log_config=None)
