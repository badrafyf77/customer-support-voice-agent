"""One active diffusion job, bounded cancellation tombstones, no GPU queue."""
from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time


class SynthesisBusy(RuntimeError):
    pass


class SynthesisCancelled(RuntimeError):
    pass


@dataclass
class Job:
    generation_id: str
    cancelled: threading.Event = field(default_factory=threading.Event)


class SynthesisGate:
    def __init__(self, ttl_seconds: float = 300, max_tombstones: int = 1024):
        self._lock = threading.Lock()
        self._active: Job | None = None
        self._cancelled: dict[str, float] = {}
        self.ttl_seconds = ttl_seconds
        self.max_tombstones = max_tombstones

    def _expire(self):
        now = time.monotonic()
        self._cancelled = {key: until for key, until in self._cancelled.items() if until > now}

    def start(self, generation_id: str) -> Job:
        with self._lock:
            self._expire()
            if generation_id in self._cancelled:
                raise SynthesisCancelled("Generation was cancelled.")
            if self._active is not None:
                raise SynthesisBusy("A diffusion pass is still running.")
            self._active = Job(generation_id)
            return self._active

    def cancel(self, generation_id: str):
        with self._lock:
            self._expire()
            if self._active and self._active.generation_id == generation_id:
                self._active.cancelled.set()
            if generation_id not in self._cancelled and len(self._cancelled) >= self.max_tombstones:
                # Never evict a cancellation prematurely and accept a late request.
                raise SynthesisBusy("Cancellation registry is at capacity.")
            self._cancelled[generation_id] = time.monotonic() + self.ttl_seconds

    def finish(self, job: Job):
        with self._lock:
            if self._active is job:
                self._active = None

    def run(self, job: Job, synthesize, text: str) -> bytes:
        # This finally runs in the GPU worker, even if its HTTP task disconnects.
        try:
            if job.cancelled.is_set():
                raise SynthesisCancelled("Generation was cancelled.")
            pcm = synthesize(text)
            if job.cancelled.is_set():
                raise SynthesisCancelled("Cancelled diffusion output was discarded.")
            return pcm
        finally:
            self.finish(job)
