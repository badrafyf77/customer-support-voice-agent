"""Recorder callback and runtime configuration integration without model loading."""
from contextlib import asynccontextmanager
from copy import deepcopy
import importlib
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from core.config import load_runtime_config, get_env
from core.nodes.stt.configuration import normalize_transcript_comparison
from test_runtime_selection import load_function, CODE_ROOT


class Recorder:
    def __init__(self, **kwargs):
        self.config = kwargs
        for name, value in kwargs.items():
            setattr(self,name,value)
        self.frames = []
        self.frames_lock = __import__('threading').Lock()
    def text(self, callback):
        callback("Sara، رقم الطلب AB-1203 والتليفون 0612345678.")
    def shutdown(self):
        pass


# Only the external recorder is replaced. Execute the actual provider methods.
with patch.dict(sys.modules,{"RealtimeSTT":SimpleNamespace(AudioToTextRecorder=Recorder)}):
    stt = importlib.import_module("core.nodes.stt.faster_whisper")


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.turn = Mock()
        self.turn_patch = patch.object(stt,"TurnDetection",return_value=self.turn)
        self.turn_factory = self.turn_patch.start()
        self.addCleanup(self.turn_patch.stop)
        self.monitor_patch = patch.object(stt.FasterWhisperSTTProvider,"_start_silence_monitor")
        self.monitor_patch.start()
        self.addCleanup(self.monitor_patch.stop)
        config = deepcopy(stt.DEFAULT_RECORDER_CONFIG)
        config.update(model=self.folder.name,realtime_model_type=self.folder.name)
        self.partial,self.final,self.potential = Mock(),Mock(),Mock()
        self.provider = stt.FasterWhisperSTTProvider(
            "ar", profile="darija", turn_model_path=self.folder.name,
            recorder_config=config, realtime_transcription_callback=self.partial,
            full_transcription_callback=self.final,potential_sentence_end=self.potential,
        )
        self.addCleanup(self.provider.shutdown)

    def test_same_correct_asr_and_arabic_callbacks_without_rewriting(self):
        config = self.provider.recorder.config
        self.assertEqual(config["language"],"ar")
        self.assertEqual(config["model"],config["realtime_model_type"])
        self.assertTrue(config["use_main_model_for_realtime"])
        self.assertIsNone(config["initial_prompt"])
        self.assertIsNone(config["initial_prompt_realtime"])
        self.assertEqual(config["beam_size"],1)
        self.assertEqual(config["post_speech_silence_duration"],0.6)
        text = "Sara، الطلب AB-1203 والتليفون 0612345678؟"
        callback = config["on_realtime_transcription_update"]
        for _ in range(3):
            callback(text)
        self.partial.assert_called_once_with(text)
        self.potential.assert_called_once_with(text)
        self.turn.calculate_waiting_time.assert_called_once_with(text=text)
        self.provider.transcribe_loop()
        self.final.assert_called_once_with("Sara، رقم الطلب AB-1203 والتليفون 0612345678.")
        self.turn.reset.assert_called_once()

    def test_punctuation_update_does_not_erase_arabic_or_create_empty_comparison(self):
        text = "واش الطلب ديال Élodie واجد؟"
        self.assertEqual(self.provider._normalize_text(text),"واش الطلب ديال élodie واجد")
        self.provider.detect_potential_sentence_end(text,force_yield=True)
        self.potential.assert_called_once_with(text)
        self.assertTrue(self.provider.sentence_end_cache[0]["text"])
        self.provider.detect_potential_sentence_end("خلي نفكر…")
        self.potential.assert_called_once()

    def test_vad_callbacks_and_dynamic_waiting_time_keep_recorder_contract(self):
        config=self.provider.recorder.config
        silence = Mock()
        self.provider.silence_active_callback=silence
        self.provider.on_new_waiting_time(0.82,"بغيت نعرف واش")
        self.assertEqual(self.provider.recorder.post_speech_silence_duration,0.82)
        config["on_turn_detection_start"]()
        self.assertTrue(self.provider.silence_active)
        config["on_turn_detection_stop"]()
        self.assertFalse(self.provider.silence_active)
        self.assertEqual(self.provider.silence_time,0)
        self.assertEqual(silence.call_args_list[0].args,(True,))
        self.assertEqual(silence.call_args_list[1].args,(False,))

    def test_reset_invalidates_classifier_before_next_lease_and_restores_initial_silence(self):
        self.provider.on_new_waiting_time(1.8,"قديم")
        self.provider.recorder.config["on_realtime_transcription_update"]("قديم")
        self.provider.reset_session_state(clear_callbacks=True)
        self.turn.reset.assert_called_once()
        self.assertEqual(self.provider.recorder.post_speech_silence_duration,0.6)
        self.assertIsNone(self.provider.realtime_text)
        self.assertEqual(self.provider.stripped_partial_user_text,"")
        self.assertIsNone(self.provider.full_transcription_callback)
        self.assertIsNone(self.provider.potential_sentence_end)
        self.assertIsNone(self.provider.realtime_transcription_callback)
        self.assertFalse(self.provider.sentence_end_cache)

    def test_english_retains_english_recorder_hints_and_models(self):
        provider=stt.FasterWhisperSTTProvider()
        self.addCleanup(provider.shutdown)
        self.assertEqual(provider.recorder.config["initial_prompt"],stt.DEFAULT_RECORDER_CONFIG["initial_prompt"])
        self.assertEqual(provider.recorder.config["language"],"en")
        self.assertEqual(self.turn_factory.call_args.kwargs["profile"],"english")


class StartupTests(unittest.IsolatedAsyncioTestCase):
    def namespace(self,factory):
        return {"asynccontextmanager":asynccontextmanager,"logger":logging.getLogger(__name__),
                "load_runtime_config":load_runtime_config,"get_env":get_env,
                "Colors":SimpleNamespace(apply=lambda value:SimpleNamespace(blue=value)),
                "UpsampleOverlap":Mock(),"VoiceRuntimeManager":factory,"_wait_for_vllm_ready":AsyncMock(),
                "LLM_START_PROVIDER":"vllm","LLM_START_MODEL":"baseline","TTS_START_ENGINE":"kokoro",
                "LANGUAGE":"en","TTS_ORPHEUS_MODEL":"unused","NO_THINK":False,
                "VOICE_RUNTIME_ACQUIRE_TIMEOUT_SECONDS":30,"VOICE_RUNTIME_MIN_WARM":1,
                "VOICE_RUNTIME_MAX_CONCURRENT":4,"VOICE_RUNTIME_IDLE_TTL_SECONDS":300}

    async def test_darija_startup_uses_verified_paths_and_passes_instance_config_to_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            from agents.chat.agent import DARIJA_SYSTEM_PROMPT
            root=Path(directory).resolve()
            (root/'asr').mkdir()
            (root/'turn').mkdir()
            models={"stt":{"path":str(root/'asr'),"repo_id":"correct-asr","revision":"pinned"},
                    "turn":{"path":str(root/'turn'),"repo_id":"darija-turn","revision":"pinned"}}
            runtime=Mock(startup=AsyncMock(),shutdown=AsyncMock())
            factory=Mock(return_value=runtime)
            namespace=self.namespace(factory)
            lifespan=load_function(CODE_ROOT/'core/session.py','lifespan',namespace)
            app=SimpleNamespace(state=SimpleNamespace())
            environment={"VOICE_AGENT":"chat","VOICE_PROFILE":"darija","DARIJA_MODEL_ROOT":directory,
                         "STT_MODEL":str(root/'asr'),"VLLM_BASE_URL":"http://127.0.0.1:8001/v1"}
            with (patch.dict(os.environ,environment,clear=True),patch('core.config.load_env_file_if_available'),
                  patch('core.model_artifacts.validate_prepared_models',return_value=models) as verify,
                  patch.dict(stt.DEFAULT_RECORDER_CONFIG,deepcopy(stt.DEFAULT_RECORDER_CONFIG),clear=True)):
                async with lifespan(app):
                    verify.assert_called_once_with(directory)
                    args=factory.call_args.kwargs
                    self.assertEqual(args["max_concurrent"],1)
                    self.assertEqual(args["language"],"ar")
                    self.assertEqual(args["stt_config"]["profile"],"darija")
                    self.assertEqual(args["stt_config"]["turn_model_path"],str(root/'turn'))
                    self.assertEqual(args["stt_config"]["recorder_config"]["model"],str(root/'asr'))
                    self.assertEqual(args["pipeline_config"]["system_prompt"],DARIJA_SYSTEM_PROMPT)
                    self.assertEqual(args["pipeline_config"]["llm_max_tokens"],256)
                    self.assertEqual(args["pipeline_config"]["llm_context_limit"],4096)
            runtime.startup.assert_awaited_once()
            runtime.shutdown.assert_awaited_once()

    async def test_wrong_asr_export_or_language_override_fails_before_warmup(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            (root/'asr').mkdir()
            models={"stt":{"path":str(root/'asr'),"repo_id":"correct-asr","revision":"pin"},
                    "turn":{"path":str(root/'turn'),"repo_id":"darija-turn","revision":"pin"}}
            for override in ({"STT_MODEL":"/wrong-125h/ctranslate2"}, {"CHAT_LANGUAGE":"en"},
                             {"STT_REALTIME_MODEL":"/other-partial"}):
                factory=Mock()
                lifespan=load_function(CODE_ROOT/'core/session.py','lifespan',self.namespace(factory))
                environment={"VOICE_AGENT":"chat","VOICE_PROFILE":"darija","DARIJA_MODEL_ROOT":directory,**override}
                with (patch.dict(os.environ,environment,clear=True),patch('core.config.load_env_file_if_available'),
                      patch('core.model_artifacts.validate_prepared_models',return_value=models)):
                    with self.assertRaises(ValueError):
                        async with lifespan(SimpleNamespace(state=SimpleNamespace())):
                            pass
                    factory.assert_not_called()


if __name__=='__main__':
    unittest.main()
