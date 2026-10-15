"""Typed Atlas -> existing quick/final pipeline -> SILMA browser preview."""
from __future__ import annotations

from pathlib import Path
from queue import Empty, Full
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from agents.chat.agent import DARIJA_SYSTEM_PROMPT
from core.pipeline import SpeechPipelineManager
from services.atlas import MODEL_ID
from tts_preview import create_app


class TypedChatProvider:
    """Preview transport adapter; generation and phrase scheduling stay in the pipeline."""

    def __init__(self, pipeline=None):
        self.pipeline = pipeline or SpeechPipelineManager(
            tts_engine="silma", llm_provider="vllm", llm_model=MODEL_ID,
            system_prompt=DARIJA_SYSTEM_PROMPT, llm_chat_format="atlas",
            llm_max_tokens=256, llm_context_limit=4096,
        )
        self.metadata = {**self.pipeline.audio.metadata, "mode": "chat", "llm_model": MODEL_ID}
        self.history = []
        self.assistant_text = ""
        self.assistant_generation_id = None
        self._turn_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._active_stop = None

    def synthesize(self, text, audio_queue, stop_event, generation_string=""):
        # Replacement turns wait until all previous workers have relinquished
        # their iterator and audio queue. A stopped queued turn never starts.
        with self._turn_lock:
            if stop_event.is_set():
                return False
            self.pipeline.abort_generation(reason="typed turn cleanup")
            with self._state_lock:
                if stop_event.is_set():
                    return False
                self._active_stop = stop_event
                self.assistant_text = ""
                self.assistant_generation_id = generation_string
                self.history.append({"role": "user", "content": text})
                self.pipeline.on_partial_assistant_text = lambda value: self._partial(value, stop_event)
                # The same preparation method used by the pipeline request worker.
                # Calling it here permits stop to atomically see the new generator.
                self.pipeline.process_prepare_generation({"text": text, "history_override": self.history})
                generation = self.pipeline.running_generation
            completed = False
            try:
                if generation is None:
                    raise RuntimeError("Atlas generation could not start")
                deadline = time.monotonic() + 180
                while not stop_event.is_set():
                    if time.monotonic() > deadline:
                        raise TimeoutError("Atlas/SILMA preview exceeded its turn deadline")
                    if generation.llm_aborted or generation.audio_quick_aborted or generation.audio_final_aborted:
                        raise RuntimeError("Atlas/SILMA generation failed; inspect the service logs")
                    if generation.llm_finished and not generation.quick_answer:
                        raise RuntimeError("Atlas returned no spoken text")
                    try:
                        chunk = generation.audio_chunks.get(timeout=0.01)
                    except Empty:
                        if generation.audio_quick_finished and generation.audio_final_finished:
                            completed = True
                            break
                        continue
                    while not stop_event.is_set():
                        try:
                            audio_queue.put(chunk, timeout=0.01)
                            break
                        except Full:
                            if time.monotonic() > deadline:
                                raise TimeoutError("Preview playback queue remained blocked")
                if completed:
                    self.history.append({"role": "assistant", "content": self.assistant_text})
                return completed
            finally:
                # On interruption only the user turn remains in history. Atlas's
                # request formatter coalesces adjacent unanswered user turns.
                with self._state_lock:
                    self._active_stop = None
                self.pipeline.abort_generation(reason="typed turn finished")
                self.pipeline.on_partial_assistant_text = None

    def _partial(self, value, stop_event):
        if not stop_event.is_set():
            self.assistant_text = value

    def stop_playback(self):
        with self._state_lock:
            if self._active_stop is not None:
                self._active_stop.set()
            self.pipeline.stop_llm_request_event.set()
            self.pipeline.stop_tts_quick_request_event.set()
            self.pipeline.stop_tts_final_request_event.set()
            self.pipeline.llm.cancel_generation()
            self.pipeline.audio.stop_playback()

    def reset_session_state(self):
        self.stop_playback()
        with self._turn_lock:
            self.pipeline.reset_session_state()
            self.pipeline.set_system_prompt(DARIJA_SYSTEM_PROMPT)
            self.history = []
            self.assistant_text = ""
            self.assistant_generation_id = None

    def shutdown(self):
        self.stop_playback()
        with self._turn_lock:
            self.pipeline.abort_generation(reason="typed preview shutdown")
            self.pipeline.shutdown()


app = create_app(provider_factory=TypedChatProvider)
