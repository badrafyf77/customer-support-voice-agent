"""Typed speech preview using the project's existing 24 kHz playback worklet."""
from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
import sys
import threading
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from core.nodes.tts.factory import create_tts_provider

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


@dataclass
class PreviewTurn:
    generation_id: str
    request_id: str
    stop: threading.Event = field(default_factory=threading.Event)
    audio: Queue = field(default_factory=lambda: Queue(maxsize=20))
    task: asyncio.Task | None = None


def create_app(provider=None, provider_factory=None):
    capacity = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(app):
        nonlocal provider
        if provider is None:
            provider = await asyncio.to_thread(provider_factory) if provider_factory else await asyncio.to_thread(create_tts_provider, engine="silma")
        yield
        await asyncio.to_thread(provider.shutdown)

    app = FastAPI(lifespan=lifespan)

    @app.get("/")
    async def index():
        return FileResponse(HERE / "tts_preview.html")

    @app.get("/static/ttsPlaybackProcessor.js")
    async def worklet():
        return FileResponse(REPO / "frontend/public/static/ttsPlaybackProcessor.js", media_type="text/javascript")

    @app.websocket("/ws/tts")
    async def preview(ws: WebSocket):
        await ws.accept()
        if capacity.locked():
            await ws.send_json({"type": "status", "status": "busy", "message": "A speech preview is active."})
            await ws.close(code=1013)
            return
        async with capacity:
            send_lock = asyncio.Lock()
            current = None
            tasks = set()
            await asyncio.to_thread(provider.reset_session_state)

            async def cancel():
                nonlocal current
                previous, current = current, None
                if previous:
                    previous.stop.set()
                    await asyncio.to_thread(provider.stop_playback)
                async with send_lock:
                    await ws.send_json({"type": "stop_tts",
                                        "request_id": previous.request_id if previous else None})

            async def speak(turn, text):
                worker = asyncio.create_task(asyncio.to_thread(
                    provider.synthesize, text, turn.audio, turn.stop, turn.generation_id,
                ))
                last_text = ""
                try:
                    while not worker.done() or not turn.audio.empty():
                        if turn.stop.is_set() or current is not turn:
                            break
                        partial = (getattr(provider, "assistant_text", "") if
                                   getattr(provider, "assistant_generation_id", turn.generation_id) == turn.generation_id else "")
                        if partial and partial != last_text:
                            async with send_lock:
                                if current is turn and not turn.stop.is_set():
                                    await ws.send_json({"type": "assistant_partial", "content": partial,
                                                        "request_id": turn.request_id,
                                                        "generation_id": turn.generation_id})
                            last_text = partial
                        try:
                            chunk = turn.audio.get_nowait()
                        except Empty:
                            await asyncio.sleep(0.005)
                            continue
                        async with send_lock:
                            if current is turn and not turn.stop.is_set():
                                await ws.send_json({
                                    "type": "tts_chunk", "generation_id": turn.generation_id,
                                    "request_id": turn.request_id,
                                    "content": base64.b64encode(chunk).decode("ascii"),
                                })
                    completed = await worker
                    async with send_lock:
                        if current is turn and not turn.stop.is_set():
                            partial = (getattr(provider, "assistant_text", "") if
                                   getattr(provider, "assistant_generation_id", turn.generation_id) == turn.generation_id else "")
                            if partial and partial != last_text:
                                await ws.send_json({"type": "assistant_partial", "content": partial,
                                                    "request_id": turn.request_id,
                                                    "generation_id": turn.generation_id})
                            await ws.send_json({"type": "tts_end", "generation_id": turn.generation_id,
                                                "request_id": turn.request_id,
                                                "completed": completed})
                except Exception:
                    turn.stop.set()
                    # A failed old task must not cancel its replacement turn.
                    if current is turn:
                        await asyncio.to_thread(provider.stop_playback)
                    async with send_lock:
                        if current is turn:
                            await ws.send_json({"type": "stop_tts", "request_id": turn.request_id})
                            await ws.send_json({"type": "status", "status": "error",
                                                "request_id": turn.request_id,
                                                "message": "Generation failed. Check the Atlas/SILMA service logs."})

            try:
                await ws.send_json({"type": "status", "status": "ready", "voice": provider.metadata})
                while True:
                    message = await ws.receive_json()
                    if message.get("type") == "stop_tts":
                        await cancel()
                    elif message.get("type") == "synthesize":
                        text, request_id = message.get("content"), message.get("request_id")
                        if (not isinstance(text, str) or not text.strip() or len(text) > 2000 or
                                not isinstance(request_id, str) or not 1 <= len(request_id) <= 128):
                            await ws.send_json({"type": "status", "status": "error",
                                                "message": "Enter 1–2000 characters of Darija."})
                            continue
                        await cancel()
                        current = PreviewTurn(uuid.uuid4().hex, request_id)
                        await ws.send_json({"type": "tts_begin", "generation_id": current.generation_id,
                                            "request_id": request_id})
                        current.task = asyncio.create_task(speak(current, text))
                        tasks.add(current.task)
                        def finished(task):
                            tasks.discard(task)
                            if not task.cancelled():
                                task.exception()
                        current.task.add_done_callback(finished)
            except WebSocketDisconnect:
                pass
            finally:
                if current:
                    current.stop.set()
                await asyncio.to_thread(provider.stop_playback)
                # Wait for provider calls to exit before another client reuses it.
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                await asyncio.to_thread(provider.reset_session_state)

    return app


app = create_app()
