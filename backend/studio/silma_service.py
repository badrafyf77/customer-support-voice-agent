"""Internal phrase synthesis service; bind to 127.0.0.1:8002."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from core.nodes.tts.silma_jobs import SynthesisBusy, SynthesisCancelled, SynthesisGate

logger = logging.getLogger(__name__)


class GenerationRequest(BaseModel):
    generation_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$")


class PhraseRequest(GenerationRequest):
    text: str = Field(min_length=1, max_length=2000)


def create_app(runtime=None) -> FastAPI:
    gate = SynthesisGate()

    @asynccontextmanager
    async def lifespan(app):
        nonlocal runtime
        if runtime is None:
            from core.nodes.tts.silma_runtime import load_runtime
            runtime = await asyncio.to_thread(load_runtime)
        await asyncio.to_thread(runtime.warmup)
        logger.info("SILMA ready: %s", runtime.metadata)
        yield

    app = FastAPI(lifespan=lifespan)

    @app.get("/health")
    async def health():
        if runtime is None:
            return JSONResponse({"ready": False}, status_code=503)
        return {"ready": True, **runtime.metadata,
                "tts_inference_time_ms": runtime.tts_inference_time_ms}

    @app.post("/cancel")
    async def cancel(request: GenerationRequest):
        try:
            gate.cancel(request.generation_id)
        except SynthesisBusy as exc:
            return JSONResponse({"code": "busy", "detail": str(exc)}, status_code=429)
        return {"cancelled": True, "generation_id": request.generation_id}

    @app.post("/synthesize")
    async def synthesize(request: PhraseRequest):
        if not request.text.strip():
            return JSONResponse({"code": "invalid_text"}, status_code=422)
        if runtime is None:
            return JSONResponse({"code": "not_ready"}, status_code=503)
        try:
            job = gate.start(request.generation_id)
        except SynthesisBusy as exc:
            return JSONResponse({"code": "busy", "detail": str(exc)}, status_code=409)
        except SynthesisCancelled as exc:
            return JSONResponse({"code": "cancelled", "detail": str(exc)}, status_code=409)
        task = asyncio.create_task(asyncio.to_thread(gate.run, job, runtime.synthesize, request.text))
        task.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
        started = time.monotonic()
        try:
            pcm = await asyncio.shield(task)
            if job.cancelled.is_set():
                raise SynthesisCancelled("Cancelled audio was discarded.")
        except SynthesisCancelled as exc:
            return JSONResponse({"code": "cancelled", "detail": str(exc)}, status_code=409)
        except ValueError as exc:
            return JSONResponse({"code": "invalid_text", "detail": str(exc)}, status_code=422)
        except asyncio.CancelledError:
            gate.cancel(request.generation_id)
            raise
        except Exception:
            logger.exception("SILMA synthesis failed for generation %s", request.generation_id)
            return JSONResponse({"code": "synthesis_failed"}, status_code=500)
        return Response(pcm, media_type="audio/pcm", headers={
            "X-Sample-Rate": "24000", "X-Audio-Format": "pcm_s16le",
            "X-Channels": "1",
            "X-Generation-Id": request.generation_id,
            "X-Synthesis-Ms": str(round((time.monotonic() - started) * 1000, 3)),
        })

    return app


app = create_app()
