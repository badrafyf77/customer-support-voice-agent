import asyncio
import logging
import time
from collections import deque
from typing import Deque, Optional

from audio_in import AudioInputProcessor
from speech_pipeline_manager import SpeechPipelineManager

logger = logging.getLogger(__name__)


class VoiceRuntimeCapacityError(RuntimeError):
    """
    Raised when a new runtime cannot be created within the instance's current capacity.
    """


class VoiceRuntime:
    """
    Reusable warmed speech runtime leased to one WebSocket session at a time.
    """
    def __init__(
            self,
            runtime_id: int,
            pipeline_config: dict,
            language: str,
            tts_engine: str,
        ) -> None:
        self.runtime_id = runtime_id
        pipeline_manager = None
        audio_processor = None

        try:
            pipeline_manager = SpeechPipelineManager(**pipeline_config)
            audio_processor = AudioInputProcessor(
                language,
                is_orpheus=tts_engine == "orpheus",
                pipeline_latency=pipeline_manager.full_output_pipeline_latency / 1000,
            )
        except Exception:
            if audio_processor is not None:
                try:
                    audio_processor.shutdown()
                except Exception:
                    logger.exception("🧰 Voice runtime %s audio processor shutdown failed during init rollback.", runtime_id)
            if pipeline_manager is not None:
                try:
                    pipeline_manager.shutdown()
                except Exception:
                    logger.exception("🧰 Voice runtime %s pipeline shutdown failed during init rollback.", runtime_id)
            raise

        self.pipeline_manager = pipeline_manager
        self.audio_processor = audio_processor

    def prepare_session(self, conversation_history: list, system_prompt: Optional[str], callbacks) -> None:
        """
        Resets the runtime and binds it to a new session's callbacks and history.
        """
        logger.info("🧰 Preparing warmed voice runtime %s for a new session.", self.runtime_id)
        self.reset_session_state()

        self.pipeline_manager.configure_session(
            history=conversation_history,
            system_prompt=system_prompt,
            on_partial_assistant_text=callbacks.on_partial_assistant_text,
        )

        self.audio_processor.realtime_callback = callbacks.on_partial
        self.audio_processor.transcriber.potential_sentence_end = callbacks.on_potential_sentence
        self.audio_processor.transcriber.on_tts_allowed_to_synthesize = callbacks.on_tts_allowed_to_synthesize
        self.audio_processor.transcriber.potential_full_transcription_callback = callbacks.on_potential_final
        self.audio_processor.transcriber.potential_full_transcription_abort_callback = callbacks.on_potential_abort
        self.audio_processor.transcriber.full_transcription_callback = callbacks.on_final
        self.audio_processor.transcriber.before_final_sentence = callbacks.on_before_final
        self.audio_processor.recording_start_callback = callbacks.on_recording_start
        self.audio_processor.silence_active_callback = callbacks.on_silence_active

    def reset_session_state(self) -> None:
        """
        Clears session-specific state so this runtime can be safely reused.
        """
        self.pipeline_manager.reset_session_state()
        self.audio_processor.reset_session_state(clear_callbacks=True)

    def shutdown(self) -> None:
        """
        Shuts down all resources owned by this runtime.
        """
        logger.info("🧰 Shutting down warmed voice runtime %s.", self.runtime_id)
        self.audio_processor.shutdown()
        self.pipeline_manager.shutdown()


class VoiceRuntimeManager:
    """
    Elastic application-owned manager for warmed speech runtimes.

    Runtime states:
    - idle: available for immediate lease
    - leased: assigned to exactly one active WebSocket session
    - creating: slot reserved while a new runtime is being built
    """
    def __init__(
            self,
            min_warm: int,
            max_concurrent: int,
            idle_ttl_seconds: float,
            pipeline_config: dict,
            language: str,
            tts_engine: str,
        ) -> None:
        requested_min_warm = max(0, min_warm)
        requested_max_concurrent = max(1, max_concurrent)

        if requested_min_warm > requested_max_concurrent:
            logger.warning(
                "🧰 Requested min warm runtimes (%s) exceeds max concurrent (%s); clamping min warm to max.",
                requested_min_warm,
                requested_max_concurrent,
            )
            requested_min_warm = requested_max_concurrent

        self.min_warm = requested_min_warm
        self.max_concurrent = requested_max_concurrent
        self.idle_ttl_seconds = max(0.0, idle_ttl_seconds)
        self.pipeline_config = dict(pipeline_config)
        self.language = language
        self.tts_engine = tts_engine

        self._condition = asyncio.Condition()
        self._idle: Deque[VoiceRuntime] = deque()
        self._idle_ids: set[int] = set()
        self._leased_ids: set[int] = set()
        self._resetting_ids: set[int] = set()
        self._runtimes: dict[int, VoiceRuntime] = {}
        self._idle_since: dict[int, float] = {}
        self._creating_count = 0
        self._next_runtime_id = 1
        self._shutdown = False
        self._idle_reaper_task: Optional[asyncio.Task] = None

    @property
    def available_count(self) -> int:
        return len(self._idle)

    @property
    def idle_count(self) -> int:
        return len(self._idle)

    @property
    def busy_count(self) -> int:
        return len(self._leased_ids)

    @property
    def resetting_count(self) -> int:
        return len(self._resetting_ids)

    @property
    def total_count(self) -> int:
        return len(self._runtimes)

    @property
    def creating_count(self) -> int:
        return self._creating_count

    @property
    def at_capacity(self) -> bool:
        return self.available_count == 0 and (self.total_count + self.creating_count) >= self.max_concurrent

    def _build_runtime(self, runtime_id: int) -> VoiceRuntime:
        return VoiceRuntime(
            runtime_id=runtime_id,
            pipeline_config=self.pipeline_config,
            language=self.language,
            tts_engine=self.tts_engine,
        )

    def _shutdown_runtime_safely(self, runtime: VoiceRuntime, reason: str) -> None:
        try:
            runtime.shutdown()
        except Exception:
            logger.exception(
                "🧰 Voice runtime %s raised while shutting down during %s.",
                runtime.runtime_id,
                reason,
            )

    def _register_idle_runtime_locked(self, runtime: VoiceRuntime, *, idle_since: Optional[float] = None) -> None:
        if runtime.runtime_id in self._idle_ids:
            return

        self._idle.append(runtime)
        self._idle_ids.add(runtime.runtime_id)
        self._idle_since[runtime.runtime_id] = time.monotonic() if idle_since is None else idle_since

    def _lease_idle_runtime_locked(self) -> Optional[VoiceRuntime]:
        while self._idle:
            runtime = self._idle.popleft()
            runtime_id = runtime.runtime_id
            self._idle_ids.discard(runtime_id)
            self._idle_since.pop(runtime_id, None)

            if self._runtimes.get(runtime_id) is not runtime:
                continue

            self._leased_ids.add(runtime_id)
            return runtime

        return None

    def _reserve_new_runtime_slot_locked(self) -> Optional[int]:
        if len(self._runtimes) + self._creating_count >= self.max_concurrent:
            return None

        runtime_id = self._next_runtime_id
        self._next_runtime_id += 1
        self._creating_count += 1
        return runtime_id

    def _retire_expired_idle_runtimes_locked(self, now: float) -> list[VoiceRuntime]:
        retired_runtimes: list[VoiceRuntime] = []

        while self._idle and len(self._runtimes) > self.min_warm:
            runtime = self._idle[0]
            runtime_id = runtime.runtime_id
            managed_runtime = self._runtimes.get(runtime_id)

            if managed_runtime is not runtime:
                self._idle.popleft()
                self._idle_ids.discard(runtime_id)
                self._idle_since.pop(runtime_id, None)
                continue

            idle_since = self._idle_since.get(runtime_id)
            if idle_since is None:
                self._idle_since[runtime_id] = now
                break

            if (now - idle_since) <= self.idle_ttl_seconds:
                break

            self._idle.popleft()
            self._idle_ids.discard(runtime_id)
            self._idle_since.pop(runtime_id, None)
            self._runtimes.pop(runtime_id, None)
            retired_runtimes.append(runtime)

        return retired_runtimes

    def _get_idle_reap_interval_seconds(self) -> float:
        if self.idle_ttl_seconds <= 0:
            return 0.1

        return min(max(0.1, self.idle_ttl_seconds / 2.0), self.idle_ttl_seconds, 30.0)

    async def _collect_expired_idle_runtimes(self) -> list[VoiceRuntime]:
        now = time.monotonic()

        async with self._condition:
            if self._shutdown or self.total_count <= self.min_warm:
                return []

            retired_runtimes = self._retire_expired_idle_runtimes_locked(now)
            if retired_runtimes:
                self._condition.notify_all()

            return retired_runtimes

    async def _idle_reaper_loop(self) -> None:
        interval_seconds = self._get_idle_reap_interval_seconds()
        logger.info(
            "🧰 Idle runtime reaper started (interval=%ss, ttl=%ss, min_warm=%s).",
            interval_seconds,
            self.idle_ttl_seconds,
            self.min_warm,
        )

        try:
            while True:
                await asyncio.sleep(interval_seconds)
                retired_runtimes = await self._collect_expired_idle_runtimes()

                for runtime in retired_runtimes:
                    logger.info(
                        "🧰 Retiring idle voice runtime %s after %.1fs idle (idle=%s, busy=%s, total=%s/%s).",
                        runtime.runtime_id,
                        self.idle_ttl_seconds,
                        self.idle_count,
                        self.busy_count,
                        self.total_count,
                        self.max_concurrent,
                    )
                    self._shutdown_runtime_safely(runtime, reason="idle shrink-back")
        except asyncio.CancelledError:
            logger.info("🧰 Idle runtime reaper stopped.")
            raise

    async def startup(self) -> None:
        """
        Creates the configured minimum number of warmed runtimes during app startup.
        """
        logger.info(
            "🧰 Initializing voice runtime manager (min_warm=%s, max_concurrent=%s, idle_ttl=%ss)...",
            self.min_warm,
            self.max_concurrent,
            self.idle_ttl_seconds,
        )

        try:
            for _ in range(self.min_warm):
                runtime_id = self._next_runtime_id
                self._next_runtime_id += 1
                runtime = self._build_runtime(runtime_id)
                self._runtimes[runtime_id] = runtime
                self._register_idle_runtime_locked(runtime)
        except Exception:
            await self.shutdown()
            raise

        logger.info(
            "🧰 Voice runtime manager ready (idle=%s, busy=%s, total=%s/%s).",
            self.idle_count,
            self.busy_count,
            self.total_count,
            self.max_concurrent,
        )

        if self._idle_reaper_task is None:
            self._idle_reaper_task = asyncio.create_task(
                self._idle_reaper_loop(),
                name="VoiceRuntimeIdleReaper",
            )

    async def acquire(self, timeout: Optional[float] = None) -> VoiceRuntime:
        """
        Leases an idle runtime immediately, creates a new one if capacity remains,
        and waits only after the hard concurrent limit is reached.
        """
        loop = asyncio.get_running_loop()
        deadline = None if timeout is None else loop.time() + timeout

        while True:
            reserved_runtime_id: Optional[int] = None

            async with self._condition:
                if self._shutdown:
                    raise RuntimeError("Voice runtime manager is shutting down.")

                leased_runtime = self._lease_idle_runtime_locked()
                if leased_runtime is not None:
                    logger.info(
                        "🧰 Leased idle voice runtime %s (idle=%s, busy=%s, total=%s/%s).",
                        leased_runtime.runtime_id,
                        self.idle_count,
                        self.busy_count,
                        self.total_count,
                        self.max_concurrent,
                    )
                    return leased_runtime

                reserved_runtime_id = self._reserve_new_runtime_slot_locked()
                if reserved_runtime_id is None:
                    if timeout is None:
                        await self._condition.wait()
                        continue

                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        raise asyncio.TimeoutError

                    await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                    continue

                logger.info(
                    "🧰 Creating voice runtime %s on demand (busy=%s, total_reserved=%s/%s).",
                    reserved_runtime_id,
                    self.busy_count,
                    self.total_count + self._creating_count,
                    self.max_concurrent,
                )

            try:
                runtime = self._build_runtime(reserved_runtime_id)
            except Exception as exc:
                async with self._condition:
                    self._creating_count -= 1
                    self._condition.notify_all()
                logger.warning(
                    "🧰 Voice runtime %s creation failed; treating the instance as temporarily full.",
                    reserved_runtime_id,
                    exc_info=True,
                )
                raise VoiceRuntimeCapacityError(
                    f"Voice runtime {reserved_runtime_id} could not be created."
                ) from exc

            async with self._condition:
                self._creating_count -= 1

                if self._shutdown:
                    self._condition.notify_all()
                else:
                    self._runtimes[runtime.runtime_id] = runtime
                    self._leased_ids.add(runtime.runtime_id)
                    self._condition.notify_all()
                    logger.info(
                        "🧰 Leased new voice runtime %s (idle=%s, busy=%s, total=%s/%s).",
                        runtime.runtime_id,
                        self.idle_count,
                        self.busy_count,
                        self.total_count,
                        self.max_concurrent,
                    )
                    return runtime

            self._shutdown_runtime_safely(runtime, reason="manager shutdown during acquire")
            raise RuntimeError("Voice runtime manager is shutting down.")

    async def release(self, runtime: VoiceRuntime) -> None:
        """
        Returns a runtime to the idle set after clearing session state.

        If reset fails, the runtime is retired so a later acquire can create a
        replacement instead of risking unsafe reuse.
        """
        runtime_id = runtime.runtime_id

        async with self._condition:
            managed_runtime = self._runtimes.get(runtime_id)
            if managed_runtime is not runtime:
                if not self._shutdown:
                    logger.warning("🧰 Ignoring release for unmanaged voice runtime %s.", runtime_id)
                return

            if runtime_id not in self._leased_ids:
                if runtime_id in self._idle_ids:
                    logger.warning("🧰 Voice runtime %s is already idle; ignoring duplicate release.", runtime_id)
                elif runtime_id in self._resetting_ids:
                    logger.warning("🧰 Voice runtime %s is already resetting; ignoring duplicate release.", runtime_id)
                else:
                    logger.warning("🧰 Voice runtime %s was not marked leased during release.", runtime_id)
                return

            self._leased_ids.remove(runtime_id)
            self._resetting_ids.add(runtime_id)

        if self._shutdown:
            self._shutdown_runtime_safely(runtime, reason="manager shutdown during release")
            async with self._condition:
                self._resetting_ids.discard(runtime_id)
                self._runtimes.pop(runtime_id, None)
                self._idle_ids.discard(runtime_id)
                self._idle_since.pop(runtime_id, None)
                self._condition.notify_all()
            return

        try:
            runtime.reset_session_state()
        except Exception:
            logger.exception("🧰 Voice runtime %s failed to reset; retiring it from the manager.", runtime_id)
            try:
                self._shutdown_runtime_safely(runtime, reason="release reset failure")
            finally:
                async with self._condition:
                    self._resetting_ids.discard(runtime_id)
                    self._runtimes.pop(runtime_id, None)
                    self._idle_ids.discard(runtime_id)
                    self._idle_since.pop(runtime_id, None)
                    self._condition.notify_all()
            return

        async with self._condition:
            self._resetting_ids.discard(runtime_id)
            if self._shutdown:
                self._runtimes.pop(runtime_id, None)
                self._idle_ids.discard(runtime_id)
                self._idle_since.pop(runtime_id, None)
                self._condition.notify_all()
            else:
                if self._runtimes.get(runtime_id) is runtime:
                    self._register_idle_runtime_locked(runtime)
                self._condition.notify_all()
                logger.info(
                    "🧰 Returned voice runtime %s to idle state (idle=%s, busy=%s, total=%s/%s).",
                    runtime_id,
                    self.idle_count,
                    self.busy_count,
                    self.total_count,
                    self.max_concurrent,
                )
                return

        self._shutdown_runtime_safely(runtime, reason="manager shutdown after reset")

    async def shutdown(self) -> None:
        """
        Shuts down every runtime owned by the manager.
        """
        idle_reaper_task = None

        async with self._condition:
            if self._shutdown:
                return

            self._shutdown = True
            idle_reaper_task = self._idle_reaper_task
            self._idle_reaper_task = None
            self._condition.notify_all()

        if idle_reaper_task:
            idle_reaper_task.cancel()
            await asyncio.gather(idle_reaper_task, return_exceptions=True)

        async with self._condition:
            while self._resetting_ids:
                await self._condition.wait()

            runtimes = list(self._runtimes.values())
            self._idle.clear()
            self._idle_ids.clear()
            self._leased_ids.clear()
            self._resetting_ids.clear()
            self._idle_since.clear()
            self._runtimes.clear()
            self._condition.notify_all()

        logger.info("🧰 Shutting down voice runtime manager...")
        for runtime in runtimes:
            self._shutdown_runtime_safely(runtime, reason="manager shutdown")


VoiceRuntimePool = VoiceRuntimeManager
