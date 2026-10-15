"""Atlas request contract and real pipeline streaming tests without GPU inference."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import logging
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Queue
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "studio"))
from services import atlas, llm as llm_module
from services.llm import LLM
from agents.chat.agent import build_chat_agent, DARIJA_SYSTEM_PROMPT, SYSTEM_PROMPT
from core.pipeline import SpeechPipelineManager
from core.text_context import TextContext
from chat_preview import TypedChatProvider


def chunk(text):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


class Stream:
    def __init__(self, chunks, pause_after_first=False):
        self.chunks = list(chunks)
        self.closed = threading.Event()
        self.first = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()
        self.pause = pause_after_first

    def __iter__(self):
        for i, text in enumerate(self.chunks):
            if i and self.pause:
                if not self.release.wait(3):
                    raise TimeoutError("Test stream was not released")
            if self.closed.is_set():
                return
            yield chunk(text)
            self.first.set()
        self.finished.set()

    def close(self):
        self.closed.set()
        self.release.set()


def make_llm(stream, model=atlas.MODEL_ID, create=None):
    with patch.object(llm_module, "OPENAI_AVAILABLE", True):
        llm = LLM("vllm", model, system_prompt=DARIJA_SYSTEM_PROMPT)
    create = create or Mock(return_value=stream)
    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    llm._client_initialized = True
    return llm, create


class AtlasTests(unittest.TestCase):
    def test_history_folding_preserves_transcript_names_and_ids(self):
        history = [{"role": "user", "content": "Sara AB-1203 0612345678 12.50", "timestamp": 123},
                   {"role": "assistant", "content": "واخا."},
                   {"role": "user", "content": "فين الطلب؟"}]
        before = deepcopy(history)
        messages = atlas.format_messages("فين الطلب؟", history, "تعليمات")
        self.assertEqual(history, before)
        self.assertEqual([m["role"] for m in messages], ["user", "assistant", "user"])
        self.assertEqual(messages[0]["content"], "تعليمات\n\nSara AB-1203 0612345678 12.50")
        self.assertNotIn("timestamp", messages[0])
        messages[0]["content"] = "changed"
        self.assertEqual(history, before)

    def test_unanswered_turns_and_system_measurement_are_supported(self):
        messages = atlas.format_messages("جديد", [{"role": "system", "content": "تعليمات"},
                                                 {"role": "user", "content": "قديم"}])
        self.assertEqual(messages, [{"role": "user", "content": "تعليمات\n\nقديم\n\nجديد"}])
        self.assertEqual(atlas.format_messages("", [{"role": "user", "content": "قياس"}]),
                         [{"role": "user", "content": "قياس"}])
        for history in ([{"role": "assistant", "content": "bad"}],
                        [{"role": "tool", "content": "bad"}], []):
            with self.assertRaises(ValueError):
                atlas.format_messages("", history)

    def test_every_split_of_role_marker_is_suppressed_with_tail(self):
        for marker in atlas.MARKERS:
            for split in range(len(marker) + 1):
                self.assertEqual("".join(atlas.spoken_chunks([
                    "سلام Sara 0612345678 "+marker[:split], marker[split:]+"model\nleak",
                ])), "سلام Sara 0612345678 ")
        self.assertEqual("".join(atlas.spoken_chunks(["سلام ", "<end_of_"])), "سلام ")
        self.assertEqual("".join(atlas.spoken_chunks(["12.", "50 AB-1203"])), "12.50 AB-1203")

    def test_order_identifier_does_not_become_a_quick_phrase_boundary(self):
        detector = TextContext(protect_identifiers=True)
        self.assertEqual(detector.get_context("رقم الطلب ديالك هو AB-"), (None, None))
        first, tail = detector.get_context("رقم الطلب ديالك هو AB-1203، واش صحيح؟")
        self.assertEqual(first, "رقم الطلب ديالك هو AB-1203،")
        self.assertEqual(tail, " واش صحيح؟")

    def test_response_caps_and_eos_cannot_be_overridden(self):
        result = atlas.generation_options({"max_tokens": 1024, "extra_body": {"ignore_eos": True}})
        self.assertEqual(result["max_tokens"], 256)
        self.assertEqual(result["extra_body"]["stop_token_ids"], [1, 107])
        self.assertFalse(result["extra_body"]["ignore_eos"])
        self.assertEqual(atlas.generation_options({"max_completion_tokens": 12})["max_tokens"], 12)
        for options in ({"extra_body": {"max_tokens": 999}}, {"max_tokens": 0},
                        {"n": 2}, {"extra_body": {"chat_template": "bad"}}):
            with self.assertRaises(ValueError):
                atlas.generation_options(options)

    def test_darija_agent_prompt_is_per_instance(self):
        darija, _ = build_chat_agent({"profile": "darija"})
        english, _ = build_chat_agent({})
        self.assertEqual(darija.system_prompt, DARIJA_SYSTEM_PROMPT)
        self.assertEqual(english.system_prompt, SYSTEM_PROMPT)
        darija.conversation_history.append({"role": "user", "content": "سلام"})
        self.assertEqual(english.conversation_history, [])

    def test_existing_client_streams_atlas_contract_and_cleans_registry(self):
        stream = Stream(["سلام ", "Sara.", "<end_", "of_turn>leak"])
        llm, create = make_llm(stream)
        self.assertEqual("".join(llm.generate("سلام", max_tokens=999)), "سلام Sara.")
        request = create.call_args.kwargs
        self.assertTrue(request["stream"])
        self.assertEqual(request["max_tokens"], 256)
        self.assertEqual(request["messages"][0]["role"], "user")
        self.assertEqual(request["extra_body"]["stop_token_ids"], [1, 107])
        self.assertTrue(stream.closed.is_set())
        self.assertFalse(llm._active_requests)

    def test_cancel_before_first_next_does_not_dispatch(self):
        llm, create = make_llm(Stream(["late"]))
        generator = llm.generate("سلام")
        llm.cancel_generation()
        self.assertEqual(list(generator), [])
        create.assert_not_called()

    def test_cancel_during_header_wait_closes_late_stream(self):
        entered, release = threading.Event(), threading.Event()
        stream = Stream(["late"])
        def create(**kwargs):
            entered.set()
            self.assertTrue(release.wait(2))
            return stream
        llm, _ = make_llm(stream, create=create)
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(lambda: list(llm.generate("سلام", request_id="pending")))
            try:
                self.assertTrue(entered.wait(1))
                self.assertTrue(llm.cancel_generation("pending"))
            finally:
                release.set()
            self.assertEqual(result.result(timeout=1), [])
        self.assertTrue(stream.closed.is_set())
        self.assertFalse(llm._active_requests)

    def test_cancel_closes_blocked_read_without_registry_deadlock(self):
        stream = Stream(["سلام ", "late"], pause_after_first=True)
        llm, _ = make_llm(stream)
        generator = llm.generate("سلام")
        self.assertEqual(next(generator), "سلام ")
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(lambda: list(generator))
            llm.cancel_generation()
            self.assertEqual(pending.result(timeout=1), [])
        self.assertFalse(llm._active_requests)

    def test_service_errors_are_visible_and_legacy_system_role_remains(self):
        def fail(**kwargs):
            raise RuntimeError("service down")
        llm, _ = make_llm(None, create=fail)
        with self.assertRaisesRegex(RuntimeError, "service down"):
            list(llm.generate("سلام"))
        self.assertFalse(llm._active_requests)
        llm, create = make_llm(Stream(["OK"]), model="english-model")
        self.assertEqual(list(llm.generate("Hi")), ["OK"])
        self.assertEqual(create.call_args.kwargs["messages"][0]["role"], "system")
        self.assertNotIn("extra_body", create.call_args.kwargs)


class SdkTests(unittest.TestCase):
    def test_locked_openai_sdk_serializes_and_parses_vllm_sse(self):
        received = Queue()
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                received.put(json.loads(body))
                events = []
                for text in ("سلام ", "Sara.", "<end_of_turn>"):
                    payload = {"id": "test", "object": "chat.completion.chunk", "created": 0,
                               "model": atlas.MODEL_ID, "choices": [{"index": 0,
                               "delta": {"content": text}, "finish_reason": None}]}
                    events.append("data: " + json.dumps(payload) + "\n\n")
                response = ("".join(events) + "data: [DONE]\n\n").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            llm = LLM("vllm", atlas.MODEL_ID, system_prompt=DARIJA_SYSTEM_PROMPT,
                      base_url=f"http://127.0.0.1:{server.server_port}/v1")
            self.assertEqual("".join(llm.generate("سلام")), "سلام Sara.")
            request = received.get(timeout=1)
            self.assertEqual(request["stop_token_ids"], [1, 107])
            self.assertEqual(request["max_tokens"], 256)
            self.assertTrue(request["stream"])
            self.assertNotIn("system", [m["role"] for m in request["messages"]])
            llm.client.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)


class FakeAudio:
    metadata = {"voice_id": "voice1", "variant": "main"}
    tts_inference_time = 1
    def __init__(self):
        self.spoken = []
        self.on_first_audio_chunk_synthesize = None

    def synthesize(self, text, queue, stop, generation_string=""):
        if stop.is_set():
            return False
        self.spoken.append(text)
        queue.put(text.encode())
        if self.on_first_audio_chunk_synthesize:
            self.on_first_audio_chunk_synthesize()
        return True

    def synthesize_generator(self, chunks, queue, stop, generation_string=""):
        for text in chunks:
            if not self.synthesize(text, queue, stop, generation_string):
                return False
        return not stop.is_set()

    def stop_playback(self):
        pass
    def reset_session_state(self):
        pass
    def shutdown(self):
        pass


class PipelineTests(unittest.TestCase):
    def setup_pipeline(self, stream):
        llm, create = make_llm(stream)
        audio = FakeAudio()
        with patch("core.pipeline.LLM", return_value=llm), patch("core.pipeline.create_tts_provider", return_value=audio):
            pipeline = SpeechPipelineManager(tts_engine="silma", llm_model=atlas.MODEL_ID,
                                            system_prompt=DARIJA_SYSTEM_PROMPT, skip_prewarm=True)
        provider = TypedChatProvider(pipeline)
        self.addCleanup(provider.shutdown)
        return provider, audio, create

    def test_quick_audio_precedes_llm_eos_and_remaining_tail_is_not_repeated(self):
        stream = Stream(["سلام، كيفاش نعاونك؟ ", "الطلب AB-1203.", " الثمن 12.50"], pause_after_first=True)
        provider, audio, create = self.setup_pipeline(stream)
        queue, stop = Queue(), threading.Event()
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(provider.synthesize, "سلام", queue, stop, "one")
            first = queue.get(timeout=1).decode()
            self.assertFalse(stream.finished.is_set(), "Quick speech must not wait for the complete LLM response")
            stream.release.set()
            self.assertTrue(result.result(timeout=2))
        text = first + "".join(item.decode() for item in list(queue.queue))
        self.assertEqual(text, "سلام، كيفاش نعاونك؟ الطلب AB-1203. الثمن 12.50")
        self.assertEqual(provider.history[-1], {"role": "assistant", "content": text})
        self.assertEqual(create.call_args.kwargs["messages"][0]["role"], "user")

    def test_stop_during_final_stream_then_new_turn_has_no_old_audio(self):
        stream = Stream(["سلام، كيفاش نعاونك؟ ", "صوت قديم"], pause_after_first=True)
        provider, audio, create = self.setup_pipeline(stream)
        queue, stop = Queue(), threading.Event()
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(provider.synthesize, "الطلب AB-1203", queue, stop, "old")
            queue.get(timeout=1)
            provider.stop_playback()
            self.assertFalse(result.result(timeout=2))
        self.assertTrue(stream.closed.is_set())
        self.assertTrue(queue.empty())
        self.assertNotIn("صوت قديم", "".join(audio.spoken))
        new = Stream(["واخا، ", "الطلب AB-1203."])
        create.return_value = new
        new_queue = Queue()
        self.assertTrue(provider.synthesize("شنو ندير دابا؟", new_queue, threading.Event(), "new"))
        messages = create.call_args.kwargs["messages"]
        self.assertIn("الطلب AB-1203\n\nشنو ندير دابا؟", messages[0]["content"])
        self.assertEqual("".join(c.decode() for c in list(new_queue.queue)), "واخا، الطلب AB-1203.")
        provider.reset_session_state()
        self.assertEqual(provider.history, [])
        self.assertEqual(provider.pipeline.llm.system_prompt, DARIJA_SYSTEM_PROMPT)

    def test_pipeline_abort_itself_closes_final_iterator_before_worker_wait(self):
        stream = Stream(["سلام، كيفاش نعاونك؟ ", "قديم"], pause_after_first=True)
        provider, audio, _ = self.setup_pipeline(stream)
        pipeline = provider.pipeline
        pipeline.process_prepare_generation("سلام")
        generation = pipeline.running_generation
        generation.audio_chunks.get(timeout=1)
        deadline = time.monotonic() + 1
        while not pipeline.tts_final_generation_active and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertTrue(pipeline.tts_final_generation_active)
        started = time.monotonic()
        pipeline.abort_generation(reason="direct pipeline interruption test")
        self.assertLess(time.monotonic() - started, 1)
        self.assertTrue(stream.closed.is_set())
        self.assertNotIn("قديم", "".join(audio.spoken))
        self.assertIsNone(pipeline.running_generation)

    def test_pipeline_failure_surfaces_in_typed_preview(self):
        provider, _, create = self.setup_pipeline(Stream([]))
        create.side_effect = RuntimeError("Atlas offline")
        with self.assertRaisesRegex(RuntimeError, "generation failed"):
            provider.synthesize("سلام", Queue(), threading.Event(), "failure")
        self.assertIsNone(provider.pipeline.running_generation)


class ChatHttpTests(unittest.TestCase):
    def test_real_pipeline_silma_http_provider_and_preview_stream_then_reconnect(self):
        from fastapi.testclient import TestClient
        from test_silma_http import FakeRuntime, ApiProvider
        from silma_service import create_app as service_app
        from tts_preview import create_app as preview_app
        from core.nodes.tts.silma import SilmaTTSProvider
        from core.model_artifacts import LOCK_PATH

        runtime = FakeRuntime()
        voices = json.loads((LOCK_PATH.parent / "voices/voices.json").read_text())["voices"]
        runtime.metadata.update(voice_id="voice1", variant="main", reference_sha256=voices["voice1"]["sha256"])
        spoken = []
        original = runtime.synthesize
        def synthesize(text):
            spoken.append(text)
            return original(text)
        runtime.synthesize = synthesize
        stream = Stream(["سلام، كيفاش نعاونك؟ ", "الطلب AB-1203.", " الثمن 12.50"], pause_after_first=True)
        llm, create = make_llm(stream)
        with TestClient(service_app(runtime)) as service:
            class SelectedProvider(ApiProvider):
                def __init__(self):
                    self.client = service
                    SilmaTTSProvider.__init__(self, voice_id="voice1", variant="main")
            audio = SelectedProvider()
            def factory():
                with patch("core.pipeline.LLM", return_value=llm), patch("core.pipeline.create_tts_provider", return_value=audio):
                    pipeline = SpeechPipelineManager(tts_engine="silma", llm_model=atlas.MODEL_ID,
                                                    system_prompt=DARIJA_SYSTEM_PROMPT, skip_prewarm=True)
                return TypedChatProvider(pipeline)
            with TestClient(preview_app(provider_factory=factory)) as client:
                with client.websocket_connect("/ws/tts") as ws:
                    ready = ws.receive_json()
                    self.assertEqual((ready["voice"]["mode"], ready["voice"]["voice_id"], ready["voice"]["variant"]),
                                     ("chat", "voice1", "main"))
                    ws.send_json({"type": "synthesize", "content": "سلام Sara", "request_id": "first"})
                    events = []
                    while True:
                        event = ws.receive_json()
                        events.append(event)
                        if event["type"] == "tts_chunk":
                            break
                    self.assertFalse(stream.finished.is_set())
                    stream.release.set()
                    while events[-1]["type"] != "tts_end":
                        events.append(ws.receive_json())
                    self.assertTrue(events[-1]["completed"])
                    self.assertEqual(spoken, ["سلام، كيفاش نعاونك؟", "الطلب AB-1203.", "الثمن 12.50"])
                    self.assertEqual([e for e in events if e["type"] == "assistant_partial"][-1]["content"],
                                     "سلام، كيفاش نعاونك؟ الطلب AB-1203. الثمن 12.50")
                    self.assertEqual(len([e for e in events if e["type"] == "tts_chunk"]), 3)
                # A second browser lease must not retain the prior conversation.
                create.return_value = Stream(["سلام Sara."])
                with client.websocket_connect("/ws/tts") as ws:
                    self.assertEqual(ws.receive_json()["status"], "ready")
                    ws.send_json({"type": "synthesize", "content": "جديد", "request_id": "new"})
                    while ws.receive_json()["type"] != "tts_end":
                        pass
                    self.assertEqual(len(create.call_args.kwargs["messages"]), 1)
                    self.assertNotIn("سلام Sara", create.call_args.kwargs["messages"][0]["content"])


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    unittest.main()
