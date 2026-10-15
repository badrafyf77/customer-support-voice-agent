# server.py
from datetime import datetime, timezone
import logging

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from agents.chat.agent import build_chat_agent
from agents.exam.agent import build_exam_agent
from core.logsetup import setup_logging
from core.session import lifespan, run_session
from services import database

setup_logging(logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(lifespan=lifespan)

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
    """Return a small status payload for the voice backend."""
    return JSONResponse(
        {
            "service": "voice-agent-backend",
            "status": "ok",
            "websocket_path": "/ws",
            "voice_reference_path": "/voice-reference",
            "voice_profile": app.state.VOICE_PROFILE,
            "runtime": {
                "total": app.state.RUNTIME_MANAGER.total_count,
                "busy": app.state.RUNTIME_MANAGER.busy_count,
                "max_concurrent": app.state.RUNTIME_MANAGER.max_concurrent,
            },
        }
    )


@app.websocket("/ws")
async def ws_endpoint(
    websocket: WebSocket,
    user_id: str = None,
    exam_id: str = None,
    attempt_id: str = None,
):
    if user_id or exam_id or attempt_id:
        if app.state.VOICE_PROFILE == "darija":
            await websocket.close(code=1008, reason="Darija supports general chat only.")
            return
        context = await database.load_session_context(user_id, exam_id, attempt_id)
        brain, _initial_state = build_exam_agent(context)
        config = {**app.state.AGENT_CONFIG, "agent_name": "exam"}
        await run_session(websocket, brain, config, app.state, user_id, context.get("exam_id"), attempt_id)
        return

    brain, _initial_state = build_chat_agent({"profile": app.state.VOICE_PROFILE})
    config = {**app.state.AGENT_CONFIG, "agent_name": "chat"}
    await run_session(websocket, brain, config, app.state)


if __name__ == "__main__":
    logger.info("🖥️▶️ Starting server without SSL.")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, log_config=None)
