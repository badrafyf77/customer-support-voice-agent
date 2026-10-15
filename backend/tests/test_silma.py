import json
from pathlib import Path
from queue import Queue
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from core.model_artifacts import LOCK_PATH
from core.nodes.tts.factory import create_tts_provider
from core.nodes.tts.silma import SilmaTTSProvider
from core.nodes.tts.silma_jobs import SynthesisGate, SynthesisBusy, SynthesisCancelled
from core.nodes.tts.silma_text import estimated_frames, iter_phrases
from core.text_context import TextContext


def metadata():
    models = json.loads(LOCK_PATH.read_text())["models"]
    spec = models["tts"]
    voices = json.loads((LOCK_PATH.parent / "voices/voices.json").read_text())["voices"]
    return {"ready": True, "model_id": spec["repo_id"], "revision": spec["revision"],
            "sample_rate": 24000, "channels": 1, "audio_format": "pcm_s16le",
            "voice_id": "voice0", "variant": "ema", "max_phrase_bytes": 400,
            "tts_inference_time_ms": 25, "steps": 32,
            "reference_sha256": voices["voice0"]["sha256"],
            "vocoder_id": models["vocoder"]["repo_id"],
            "vocoder_revision": models["vocoder"]["revision"]}


class FakeProvider(SilmaTTSProvider):
    def __init__(self):
        self.phrases = []
        self.cancel_requests = []
        self.request_started = threading.Event()
        self.release_request = threading.Event()
        self.release_request.set()
        self.bad_format = False
        self.pcm = b"\x01\x00" * 12
        super().__init__()

    def _request(self, method, path, payload=None, timeout=None):
        if path == "/health":
            return 200, {}, json.dumps(metadata()).encode()
        if path == "/cancel":
            self.cancel_requests.append(payload["generation_id"])
            return 200, {}, b"{}"
        self.phrases.append(payload["text"])
        self.request_started.set()
        if not self.release_request.wait(3):
            raise RuntimeError("Test request was not released")
        headers = {"x-sample-rate": "24000", "x-channels": "1",
                   "x-audio-format": "invalid" if self.bad_format else "pcm_s16le",
                   "x-generation-id": payload["generation_id"]}
        return 200, headers, self.pcm


class PhraseTests(unittest.TestCase):
    def test_arabic_first_phrase_boundary_preserves_tail(self):
        first, tail = TextContext().get_context("بغيت نعرف واش الطلب ديالي واجد؟ عافاك جاوبني")
        self.assertEqual(first, "بغيت نعرف واش الطلب ديالي واجد؟")
        self.assertEqual(tail, " عافاك جاوبني")

    def test_stream_boundaries_and_tail_flush(self):
        self.assertEqual(list(iter_phrases(["كيفاش نقدر", " نعاونك؟ ", "سمّيتي ", "Salma"])),
                         ["كيفاش نقدر نعاونك؟", "سمّيتي Salma"])

    def test_decimal_and_foreign_name_are_not_split_at_period(self):
        phrases = list(iter_phrases(["الثمن هو 3.", "14 درهم. رابط example.", "com واجد"]))
        self.assertEqual(phrases, ["الثمن هو 3.14 درهم.", "رابط example.com واجد"])

    def test_quick_phrase_does_not_commit_an_ambiguous_decimal_or_name(self):
        context = TextContext(protect_identifiers=True)
        self.assertEqual(context.get_context("الثمن ديال الطلب هو 3."), (None, None))
        first, tail = context.get_context("الثمن ديال الطلب هو 3.14 درهم. والباقي")
        self.assertEqual((first, tail), ("الثمن ديال الطلب هو 3.14 درهم.", " والباقي"))
        first, _ = context.get_context("شوف الرابط example.com واش خدام؟ والباقي")
        self.assertEqual(first, "شوف الرابط example.com واش خدام؟")

    def test_unicode_limits_keep_every_character(self):
        text = "غ" * 75 + "123456"
        phrases = list(iter_phrases([text], max_chars=20, max_bytes=25))
        self.assertEqual("".join(phrases), text)
        self.assertTrue(all(len(p.encode("utf-8")) <= 25 for p in phrases))

    def test_reference_speaking_rate_sets_duration(self):
        self.assertEqual(estimated_frames("abcdefghijkl", "abcdefghijkl", 100), 200)
        self.assertEqual(estimated_frames("غدا", "شكرا", 100), 350)
        self.assertGreater(estimated_frames("جواب طويل بزاف", "شكرا", 100),
                           estimated_frames("نعم", "شكرا", 100))


class GateTests(unittest.TestCase):
    def test_cancel_before_dispatch_rejects_late_request(self):
        gate = SynthesisGate()
        gate.cancel("old")
        with self.assertRaises(SynthesisCancelled):
            gate.start("old")

    def test_cancel_discards_diffusion_result_and_keeps_slot_until_finished(self):
        gate = SynthesisGate()
        started, release = threading.Event(), threading.Event()
        def synthesize(text):
            started.set()
            if not release.wait(2):
                raise RuntimeError("Test pass not released")
            return b"old"
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(gate.run, gate.start("old"), synthesize, "text")
            try:
                self.assertTrue(started.wait(1))
                gate.cancel("old")
                with self.assertRaises(SynthesisBusy):
                    gate.start("new")
            finally:
                release.set()
            with self.assertRaises(SynthesisCancelled):
                future.result(timeout=1)
        self.assertIsNotNone(gate.start("new"))

    def test_registry_capacity_does_not_evict_cancellation(self):
        gate = SynthesisGate(max_tombstones=1)
        gate.cancel("old")
        with self.assertRaises(SynthesisBusy):
            gate.cancel("next")
        with self.assertRaises(SynthesisCancelled):
            gate.start("old")


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = FakeProvider()
        self.addCleanup(self.provider.release_request.set)
        self.addCleanup(self.provider.shutdown)

    def test_phrases_are_ordered_tail_is_kept_and_callback_fires_once(self):
        callback = Mock()
        self.provider.on_first_audio_chunk_synthesize = callback
        audio = Queue()
        self.assertTrue(self.provider.synthesize_generator(
            iter(["كيفاش نقدر نعاونك؟", " الباقي ", "بلا نقطة"]), audio, threading.Event(), "gen-1"))
        self.assertEqual(self.provider.phrases, ["كيفاش نقدر نعاونك؟", "الباقي بلا نقطة"])
        self.assertEqual(audio.get_nowait() + audio.get_nowait(), self.provider.pcm * 2)
        callback.assert_called_once()
        self.assertGreater(self.provider.tts_inference_time, 0)

    def test_stop_while_service_is_running_suppresses_late_audio(self):
        self.provider.release_request.clear()
        audio, stop = Queue(), threading.Event()
        callback = Mock()
        self.provider.on_first_audio_chunk_synthesize = callback
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.provider.synthesize, "سلام", audio, stop, "gen-1")
            try:
                self.assertTrue(self.provider.request_started.wait(1))
                self.provider.stop_playback()
                self.assertFalse(future.result(timeout=0.5))
            finally:
                self.provider.release_request.set()
        self.assertTrue(audio.empty())
        callback.assert_not_called()

    def test_stop_event_alone_suppresses_late_audio(self):
        self.provider.release_request.clear()
        audio, stop = Queue(), threading.Event()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.provider.synthesize, "سلام", audio, stop)
            try:
                self.assertTrue(self.provider.request_started.wait(1))
                stop.set()
                self.assertFalse(future.result(timeout=0.5))
            finally:
                self.provider.release_request.set()
        self.assertTrue(audio.empty())

    def test_buffer_backpressure_cancels_without_dropping_or_accumulating(self):
        self.provider.pcm *= 100
        self.provider.max_pending_packets = 1
        self.provider.packet_bytes = 4
        audio, stop = Queue(), threading.Event()
        queued = threading.Event()
        self.provider.on_first_audio_chunk_synthesize = queued.set
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.provider.synthesize, "سلام", audio, stop)
            self.assertTrue(queued.wait(1))
            self.assertEqual(audio.qsize(), 1)
            stop.set()
            self.assertFalse(future.result(timeout=0.5))

    def test_reset_does_not_reactivate_old_call_and_new_session_can_speak(self):
        self.provider.release_request.clear()
        old_audio = Queue()
        with ThreadPoolExecutor(max_workers=1) as executor:
            old = executor.submit(self.provider.synthesize, "قديم", old_audio, threading.Event(), "gen-1")
            try:
                self.assertTrue(self.provider.request_started.wait(1))
                self.provider.reset_session_state()
                self.assertFalse(old.result(timeout=0.5))
            finally:
                self.provider.release_request.set()
        new_audio = Queue()
        self.assertTrue(self.provider.synthesize("جديد", new_audio, threading.Event(), "gen-1"))
        self.assertTrue(old_audio.empty())
        self.assertFalse(new_audio.empty())

    def test_cancel_between_quick_and_final_rejects_old_final(self):
        audio = Queue()
        self.assertTrue(self.provider.synthesize("العبارة اللولة", audio, threading.Event(), "gen-1"))
        self.provider.stop_playback()
        self.assertFalse(self.provider.synthesize_generator(iter(["الباقي"]), audio, threading.Event(), "gen-1"))
        self.assertEqual(len(self.provider.phrases), 1)

    def test_invalid_pcm_contract_fails_without_audio(self):
        self.provider.bad_format = True
        audio = Queue()
        with self.assertRaisesRegex(RuntimeError, "Invalid SILMA audio"):
            self.provider.synthesize("سلام", audio, threading.Event())
        self.assertTrue(audio.empty())

    def test_legacy_factory_preserves_engine_arguments(self):
        legacy = Mock()
        with patch.dict(sys.modules, {"core.nodes.tts.realtime": Mock(RealtimeTTSProvider=legacy)}):
            create_tts_provider("orpheus", orpheus_model="existing-model", skip_prewarm=True)
        legacy.assert_called_once_with(engine="orpheus", orpheus_model="existing-model", skip_prewarm=True)


if __name__ == "__main__":
    unittest.main()
