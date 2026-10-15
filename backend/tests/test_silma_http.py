"""HTTP/WebSocket contract checks with deterministic PCM, without loading models."""
import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from queue import Queue
import sys
import threading
import unittest

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "studio"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from silma_service import create_app as service_app
from tts_preview import create_app as preview_app
from core.nodes.tts.silma import SilmaTTSProvider
from core.nodes.tts.silma_config import selected_voice
from test_silma import metadata


class FakeRuntime:
    def __init__(self):
        self.metadata = metadata()
        self.tts_inference_time_ms = 25
        self.warmups = 0
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.pcm = b"\x10\x00\xf0\xff" * 32

    def warmup(self):
        self.warmups += 1

    def synthesize(self, text):
        self.started.set()
        if not self.release.wait(2):
            raise RuntimeError("Test pass was not released")
        return self.pcm


class ApiProvider(SilmaTTSProvider):
    def __init__(self, client):
        self.client = client
        super().__init__()

    def _request(self, method, path, payload=None, timeout=None):
        response = self.client.request(method, path, json=payload)
        return response.status_code, dict(response.headers), response.content


class HttpTests(unittest.TestCase):
    def test_health_and_pcm_contract_and_one_cached_warmup(self):
        runtime = FakeRuntime()
        with TestClient(service_app(runtime)) as client:
            health = client.get("/health")
            self.assertEqual(health.json()["channels"], 1)
            for generation in ("one", "two"):
                response = client.post("/synthesize", json={"generation_id": generation, "text": "سلام"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, runtime.pcm)
                self.assertEqual(response.headers["x-sample-rate"], "24000")
                self.assertEqual(response.headers["x-generation-id"], generation)
                self.assertEqual(response.headers["x-audio-format"], "pcm_s16le")
            self.assertEqual(runtime.warmups, 1)

    def test_cancel_during_diffusion_rejects_audio_and_new_work_is_bounded(self):
        runtime = FakeRuntime()
        runtime.release.clear()
        with TestClient(service_app(runtime)) as client, ThreadPoolExecutor(max_workers=1) as executor:
            old = executor.submit(client.post, "/synthesize", json={"generation_id": "old", "text": "قديم"})
            try:
                self.assertTrue(runtime.started.wait(1))
                self.assertEqual(client.post("/cancel", json={"generation_id": "old"}).status_code, 200)
                busy = client.post("/synthesize", json={"generation_id": "new", "text": "جديد"})
                self.assertEqual((busy.status_code, busy.json()["code"]), (409, "busy"))
            finally:
                runtime.release.set()
            result = old.result(timeout=1)
            self.assertEqual((result.status_code, result.json()["code"]), (409, "cancelled"))
            self.assertEqual(client.post("/synthesize", json={"generation_id": "new", "text": "جديد"}).status_code, 200)
            replay = client.post("/synthesize", json={"generation_id": "old", "text": "قديم"})
            self.assertEqual(replay.json()["code"], "cancelled")

    def test_provider_to_service_roundtrip_uses_exact_pcm(self):
        runtime = FakeRuntime()
        with TestClient(service_app(runtime)) as client:
            provider = ApiProvider(client)
            try:
                audio = Queue()
                self.assertTrue(provider.synthesize("سلام", audio, threading.Event(), "gen-1"))
                self.assertEqual(audio.get_nowait(), runtime.pcm)
            finally:
                provider.shutdown()

    def test_invalid_text_and_generation_id_fail(self):
        with TestClient(service_app(FakeRuntime())) as client:
            for body in [{"generation_id": "one", "text": " "}, {"generation_id": "bad id", "text": "سلام"}]:
                self.assertEqual(client.post("/synthesize", json=body).status_code, 422)

    def test_typed_preview_delivers_existing_chunk_format_and_worklet(self):
        runtime = FakeRuntime()
        with TestClient(service_app(runtime)) as service:
            provider = ApiProvider(service)
            with TestClient(preview_app(provider)) as preview:
                worklet = preview.get("/static/ttsPlaybackProcessor.js")
                self.assertEqual(worklet.status_code, 200)
                self.assertIn("tts-playback-processor", worklet.text)
                with preview.websocket_connect("/ws/tts") as socket:
                    self.assertEqual(socket.receive_json()["status"], "ready")
                    socket.send_json({"type": "synthesize", "content": "سلام", "request_id": "browser-request"})
                    self.assertEqual(socket.receive_json()["type"], "stop_tts")
                    begin = socket.receive_json()
                    chunk = socket.receive_json()
                    self.assertEqual(chunk["type"], "tts_chunk")
                    self.assertEqual(chunk["request_id"], begin["request_id"])
                    self.assertEqual(base64.b64decode(chunk["content"]), runtime.pcm)
                    self.assertTrue(socket.receive_json()["completed"])
                    socket.send_json({"type": "stop_tts"})
                    self.assertEqual(socket.receive_json()["type"], "stop_tts")

    def test_saved_user_selection(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(selected_voice(), ("voice1", "main"))


if __name__ == "__main__":
    unittest.main()
