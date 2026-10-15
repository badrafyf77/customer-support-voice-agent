"""SILMA HTTP provider implementing the shared pipeline's TTS contract."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from collections import deque
import json
import logging
from queue import Full
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

from core.model_artifacts import LOCK_PATH
from core.nodes.tts.silma_text import iter_phrases

logger = logging.getLogger(__name__)


class SilmaTTSProvider:
    packet_bytes = 4800  # 100 ms of mono 24 kHz PCM16
    max_pending_packets = 20  # At most two seconds waiting in the pipeline queue
    max_response_bytes = 30 * 24000 * 2

    def __init__(
        self, base_url="http://127.0.0.1:8002", skip_prewarm=False,
        voice_id="voice0", variant="ema", request_timeout=120.0,
    ):
        self.base_url = base_url.rstrip("/")
        if not 0 < request_timeout <= 120:
            raise ValueError("SILMA request timeout must be greater than 0 and at most 120 seconds.")
        self.request_timeout = request_timeout
        self.engine_name = "silma"
        self.on_first_audio_chunk_synthesize = None
        self._state_lock = threading.RLock()
        self._synthesis_lock = threading.Lock()
        self._epoch = 0
        self._session_id = uuid.uuid4().hex
        self._closed = False
        self._active_generation = None
        self._pending_request = None
        self._last_generation = None
        self._cancelled = set()
        self._cancelled_order = deque()
        self._network = ThreadPoolExecutor(max_workers=1, thread_name_prefix="SilmaHTTP")
        self._cancellations = ThreadPoolExecutor(max_workers=1, thread_name_prefix="SilmaCancel")
        self._cancel_slots = threading.BoundedSemaphore(8)
        try:
            status, _, body = self._request("GET", "/health", timeout=10)
            metadata = json.loads(body)
            models = json.loads(LOCK_PATH.read_text())["models"]
            spec = models["tts"]
            if status != 200 or not metadata.get("ready"):
                raise RuntimeError("SILMA service is not ready.")
            if (metadata.get("model_id"), metadata.get("revision")) != (spec["repo_id"], spec["revision"]):
                raise RuntimeError("SILMA service is using a different model or revision.")
            if (metadata.get("sample_rate") != 24000 or metadata.get("channels") != 1 or
                    metadata.get("audio_format") != "pcm_s16le"):
                raise RuntimeError("SILMA service must return mono 24 kHz PCM16.")
            if metadata.get("voice_id") != voice_id or metadata.get("variant") != variant:
                raise RuntimeError("SILMA service voice/checkpoint differs from the backend configuration.")
            voices = json.loads((LOCK_PATH.parent / "voices/voices.json").read_text())["voices"]
            vocoder = models["vocoder"]
            if (metadata.get("reference_sha256") != voices[voice_id]["sha256"] or
                    metadata.get("vocoder_id") != vocoder["repo_id"] or
                    metadata.get("vocoder_revision") != vocoder["revision"] or
                    metadata.get("steps") != 32):
                raise RuntimeError("SILMA service reference/vocoder/sampling settings do not match.")
            self.max_phrase_bytes = min(400, int(metadata["max_phrase_bytes"]))
            if self.max_phrase_bytes < 4:
                raise RuntimeError("SILMA service advertised an invalid phrase limit.")
            self.tts_inference_time = float(metadata["tts_inference_time_ms"])
            self.metadata = metadata
        except Exception:
            self.shutdown()
            raise

    def _request(self, method, path, payload=None, timeout=None):
        request = Request(
            self.base_url + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None,
            headers={"Content-Type": "application/json"}, method=method,
        )
        try:
            response = urlopen(request, timeout=timeout or self.request_timeout)
        except HTTPError as exc:
            response = exc
        except (URLError, OSError) as exc:
            raise RuntimeError(f"SILMA service request failed: {path}") from exc
        with response:
            body = response.read(self.max_response_bytes + 1)
            if len(body) > self.max_response_bytes:
                raise RuntimeError("SILMA response exceeded the audio limit.")
            return response.status, {key.lower(): value for key, value in response.headers.items()}, body

    def _remote_cancel(self, generation_id):
        try:
            self._request("POST", "/cancel", {"generation_id": generation_id}, timeout=2)
        except Exception:
            logger.warning("SILMA remote cancellation failed; local audio remains suppressed.", exc_info=True)
        finally:
            self._cancel_slots.release()

    def _cancel_remote(self, generation_id):
        if generation_id and self._cancel_slots.acquire(blocking=False):
            try:
                self._cancellations.submit(self._remote_cancel, generation_id)
            except RuntimeError:
                self._cancel_slots.release()

    def stop_playback(self):
        with self._state_lock:
            self._epoch += 1
            generation_id = self._active_generation or self._last_generation
            if generation_id:
                if generation_id not in self._cancelled:
                    self._cancelled.add(generation_id)
                    self._cancelled_order.append(generation_id)
                while len(self._cancelled_order) > 256:
                    self._cancelled.discard(self._cancelled_order.popleft())
            # The epoch also invalidates calls that were waiting for the synthesis lock.
        self._cancel_remote(generation_id)

    def reset_session_state(self):
        self.stop_playback()
        with self._state_lock:
            self._session_id = uuid.uuid4().hex
            self._last_generation = None
            self._cancelled.clear()
            self._cancelled_order.clear()
            self.on_first_audio_chunk_synthesize = None

    def shutdown(self):
        self.stop_playback()
        with self._state_lock:
            self._closed = True
        self._network.shutdown(wait=False, cancel_futures=True)
        self._cancellations.shutdown(wait=False, cancel_futures=True)

    def _is_cancelled(self, epoch, generation_id, stop_event):
        with self._state_lock:
            return (self._closed or epoch != self._epoch or
                    generation_id in self._cancelled or stop_event.is_set())

    def synthesize(self, text, audio_chunks, stop_event, generation_string=""):
        return self.synthesize_generator(iter([text]), audio_chunks, stop_event, generation_string)

    def synthesize_generator(self, generator, audio_chunks, stop_event, generation_string=""):
        with self._state_lock:
            epoch = self._epoch
            generation_id = self._session_id + ":" + (generation_string or uuid.uuid4().hex)
        while not self._synthesis_lock.acquire(timeout=0.02):
            if self._is_cancelled(epoch, generation_id, stop_event):
                return False
        first_audio = True
        try:
            with self._state_lock:
                if self._is_cancelled(epoch, generation_id, stop_event):
                    return False
                self._active_generation = self._last_generation = generation_id
            for phrase in iter_phrases(generator, max_bytes=self.max_phrase_bytes):
                if self._is_cancelled(epoch, generation_id, stop_event):
                    return False
                started = time.monotonic()
                deadline = started + self.request_timeout
                while True:
                    # A canceled HTTP call may still be draining its response.
                    # Wait for that one call instead of accumulating executor work.
                    while self._pending_request is not None and not self._pending_request.done():
                        if self._is_cancelled(epoch, generation_id, stop_event):
                            return False
                        if time.monotonic() > deadline:
                            raise RuntimeError("SILMA previous request did not finish.")
                        stop_event.wait(0.02)
                    future = self._network.submit(
                        self._request, "POST", "/synthesize",
                        {"text": phrase, "generation_id": generation_id},
                    )
                    self._pending_request = future
                    while True:
                        if self._is_cancelled(epoch, generation_id, stop_event):
                            future.cancel()
                            self._cancel_remote(generation_id)
                            return False
                        try:
                            status, headers, pcm = future.result(timeout=0.02)
                            break
                        except FutureTimeout:
                            if time.monotonic() > deadline:
                                future.cancel()
                                self._cancel_remote(generation_id)
                                raise RuntimeError("SILMA synthesis timed out.")
                    if status == 409:
                        code = json.loads(pcm).get("code")
                        if code == "cancelled":
                            return False
                        if code == "busy" and time.monotonic() < deadline:
                            stop_event.wait(0.05)
                            if self._is_cancelled(epoch, generation_id, stop_event):
                                return False
                            continue
                    if status != 200:
                        raise RuntimeError(f"SILMA synthesis failed (HTTP {status}).")
                    if (headers.get("x-sample-rate") != "24000" or
                        headers.get("x-audio-format") != "pcm_s16le" or
                        headers.get("x-channels") != "1" or
                        headers.get("x-generation-id") != generation_id or not pcm or len(pcm) % 2):
                        raise RuntimeError("Invalid SILMA audio response; output discarded.")
                    break
                self.tts_inference_time = (time.monotonic() - started) * 1000
                for offset in range(0, len(pcm), self.packet_bytes):
                    while True:
                        with self._state_lock:
                            if self._is_cancelled(epoch, generation_id, stop_event):
                                return False
                            if audio_chunks.qsize() < self.max_pending_packets:
                                try:
                                    audio_chunks.put_nowait(pcm[offset:offset + self.packet_bytes])
                                except Full:
                                    pass
                                else:
                                    if first_audio and self.on_first_audio_chunk_synthesize:
                                        self.on_first_audio_chunk_synthesize()
                                    first_audio = False
                                    break
                        stop_event.wait(0.01)
            return not self._is_cancelled(epoch, generation_id, stop_event)
        finally:
            if self._is_cancelled(epoch, generation_id, stop_event):
                self._cancel_remote(generation_id)
            with self._state_lock:
                if self._active_generation == generation_id:
                    self._active_generation = None
            self._synthesis_lock.release()
