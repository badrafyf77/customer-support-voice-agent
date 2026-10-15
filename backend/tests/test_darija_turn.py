"""Darija calibration, dynamic timing and reset races using fake classifier logits."""
from contextlib import nullcontext
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from core import darija_turn
from core.darija_turn_text import normalize_turn_text
from core.darija_turn_policy import completion_override
from core.nodes.stt.configuration import darija_recorder_config, normalize_transcript_comparison
from core.turndetect import TurnDetection, interpolate_detection

CONFIG = json.loads((Path(__file__).resolve().parent / "fixtures/darija_turn_config.json").read_text())


class Tensor:
    def __init__(self, value):
        self.value = value
    def to(self, device):
        return self
    def detach(self):
        return self
    def cpu(self):
        return self
    def tolist(self):
        return self.value


class Tokenizer:
    def __init__(self):
        self.calls = []
        self.truncation_side = "right"
    def __call__(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return {"input_ids": Tensor([text])}


class Model:
    def __init__(self):
        self.config = SimpleNamespace(**deepcopy(CONFIG))
        self.logits = [0, 4]
        self.device = None
    def to(self, device):
        self.device = device
        return self
    def eval(self):
        return self
    def __call__(self, **kwargs):
        return SimpleNamespace(logits=Tensor([self.logits]))


def make_detector(path, callback=None, profile="darija", model=None):
    tokenizer, model = Tokenizer(), model or Model()
    token_factory = Mock(return_value=tokenizer)
    model_factory = Mock(return_value=model)
    transformers = SimpleNamespace(
        AutoTokenizer=SimpleNamespace(from_pretrained=token_factory),
        AutoModelForSequenceClassification=SimpleNamespace(from_pretrained=model_factory),
        DistilBertTokenizerFast=SimpleNamespace(from_pretrained=token_factory),
        DistilBertForSequenceClassification=SimpleNamespace(from_pretrained=model_factory),
    )
    torch = SimpleNamespace(device=lambda value:value, no_grad=nullcontext,
                            cuda=SimpleNamespace(is_available=lambda:False))
    with patch.dict(sys.modules, {"torch":torch, "transformers":transformers}):
        detector = TurnDetection(callback, model_path=path, profile=profile, pipeline_latency=0.05)
    return detector, tokenizer, model, token_factory


class ContractTests(unittest.TestCase):
    def test_normalization_matches_training_and_preserves_names_and_digits(self):
        self.assertEqual(normalize_turn_text("  ڭال: Jean-Luc، 0612345678\u200f  12.50!  "),
                         "گال Jean Luc 0612345678 12 50")
        self.assertEqual(normalize_transcript_comparison(" واش Sara وÉlodie جاو؟ ٠٦١٢ 123!"),
                         "واش sara وélodie جاو ٠٦١٢ 123")

    def test_syntax_cases_are_exact_and_model_probability_remains_separate(self):
        for text in ("بغيت نعرف واش", "رقم الطلب ديال", "ولكن", "غادي نصيفط", "تسنى شوية", "اممم", ""):
            with self.subTest(text=text):
                result = darija_turn.decision(text, 0.99)
                self.assertEqual(result.decision_score, 0)
                self.assertFalse(result.is_complete)
                self.assertEqual(result.completion_probability, 0.99)
        for text in ("واخا", "واخا فهمت", "شكرا بزاف", "لا شكرا", "السلام عليكم", "ما فهمتش", "إيوا صافي"):
            self.assertEqual(darija_turn.decision(text, 0.01).decision_score, 1)
        self.assertIsNone(completion_override("الطلب AB-1203 وصل اليوم"))
        self.assertTrue(darija_turn.decision("وصل الطلب", darija_turn.THRESHOLD).is_complete)
        self.assertFalse(darija_turn.decision("وصل الطلب", darija_turn.THRESHOLD-1e-8).is_complete)

    def test_temperature_and_invalid_logits(self):
        expected = 1 / (1 + math.exp(-4 / 3.9))
        self.assertAlmostEqual(darija_turn.calibrated_probability([0, 4]), expected)
        self.assertEqual(darija_turn.calibrated_probability([-10000, 10000]), 1)
        for logits in ([0], [0,float('nan')], [0,float('inf')]):
            with self.assertRaises(ValueError):
                darija_turn.calibrated_probability(logits)

    def test_wrong_checkpoint_contract_is_rejected(self):
        for field, invalid in (("turn_detection_temperature",1), ("turn_detection_max_length",512),
                               ("turn_detection_policy","other"), ("turn_detection_threshold",0.5),
                               ("id2label",{"0":"complete","1":"incomplete"})):
            config = {**CONFIG, field:invalid}
            with self.assertRaises(ValueError):
                darija_turn.validate_model_config(SimpleNamespace(**config))

    def test_recorder_changes_only_model_language_hints_and_shares_main_model(self):
        with tempfile.TemporaryDirectory() as path:
            base = {"model":"medium.en", "realtime_model_type":"small.en", "beam_size":1,
                    "beam_size_realtime":1, "silero_sensitivity":0.25, "webrtc_sensitivity":3,
                    "post_speech_silence_duration":0.6, "initial_prompt":"English", "initial_prompt_realtime":"English",
                    "use_microphone":False, "language":"en", "use_main_model_for_realtime":False}
            before = deepcopy(base)
            configured = darija_recorder_config(base,path,path)
            self.assertEqual(base,before)
            self.assertEqual(configured["model"],configured["realtime_model_type"])
            self.assertEqual(configured["language"],"ar")
            self.assertIsNone(configured["initial_prompt"])
            self.assertIsNone(configured["initial_prompt_realtime"])
            changed = {key for key in base if configured[key] != base[key]}
            self.assertEqual(changed,{"model","realtime_model_type","language","initial_prompt","initial_prompt_realtime","use_main_model_for_realtime"})
            with self.assertRaises(ValueError):
                darija_recorder_config(base,path,path+"/wrong-export")


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.callback = Mock()
        self.detector, self.tokenizer, self.model, self.factory = make_detector(self.directory.name,self.callback)
        self.addCleanup(self.detector.shutdown)

    def process(self,text):
        self.detector.calculate_waiting_time(text)
        self.detector.text_queue.join()
        return self.detector.last_decision

    def test_local_cpu_last_128_contract_and_calibration(self):
        self.factory.assert_called_once_with(self.directory.name,local_files_only=True,trust_remote_code=False)
        self.assertEqual(self.model.device,"cpu")
        self.assertEqual(self.tokenizer.truncation_side,"left")
        score = self.process("الطلب ديالي وصل اليوم؟")
        self.assertEqual(self.tokenizer.calls[-1][0],"الطلب ديالي وصل اليوم")
        self.assertEqual(self.tokenizer.calls[-1][1]["max_length"],128)
        self.assertTrue(self.tokenizer.calls[-1][1]["truncation"])
        self.assertAlmostEqual(score.completion_probability,1/(1+math.exp(-4/3.9)))
        self.assertEqual(self.callback.call_args.args[1],"الطلب ديالي وصل اليوم؟")

    def test_existing_pause_formula_uses_score_and_threshold_does_not_pick_schedule(self):
        for text in ("وصل الطلب ديالي", "رقم الطلب ديال", "واخا", "اممم", "0612345678", "واش الطلب واجد؟"):
            self.detector.reset()
            completion = self.process(text)
            punct = self.detector.get_suggested_whisper_pause(text)
            expected = max((0.65*punct+0.35*(1-completion.decision_score))*0.5, 0.15)
            self.assertAlmostEqual(self.callback.call_args.args[0],expected)
        self.detector.pipeline_latency=2
        self.detector.pipeline_latency_overhead=0.1
        self.detector.reset()
        self.process("واخا")
        self.assertEqual(self.callback.call_args.args[0],2.1)

    def test_arabic_question_and_ellipsis_keep_existing_punctuation_timing(self):
        self.assertEqual(self.detector.get_suggested_whisper_pause("واش واجد؟"), self.detector.question_pause)
        self.assertEqual(self.detector.get_suggested_whisper_pause("واش واجد?"), self.detector.question_pause)
        self.assertEqual(self.detector.get_suggested_whisper_pause("خلي نفكر…"), self.detector.ellipsis_pause)
        self.process("خلي نفكر…")
        expected = (0.65*2.3 + 0.35)*0.5 + 0.2
        self.assertAlmostEqual(self.callback.call_args.args[0],expected)

    def test_reset_discards_inflight_and_queued_old_results(self):
        started, release = threading.Event(), threading.Event()
        original = self.detector._predict_probability
        def blocked(text):
            started.set()
            if not release.wait(2):
                raise RuntimeError("Test prediction was not released")
            return original(text)
        self.detector._predict_probability = blocked
        self.detector.calculate_waiting_time("قديم الطلب وصل")
        try:
            self.assertTrue(started.wait(1))
            self.detector.calculate_waiting_time("قديم آخر")
            self.detector.reset()
            self.assertIsNone(self.detector.last_decision)
            self.assertEqual(self.detector.current_waiting_time,-1)
        finally:
            release.set()
        self.detector.text_queue.join()
        self.callback.assert_not_called()
        self.assertEqual(list(self.detector._completion_probability_cache),[])
        self.detector._predict_probability = original
        self.process("جديد الطلب وصل")
        self.assertEqual(self.callback.call_args.args[1],"جديد الطلب وصل")
        self.assertNotIn("قديم",str(self.detector.text_time_deque))

    def test_classifier_error_keeps_worker_alive_and_does_not_reuse_completion(self):
        self.process("واخا")
        self.detector.reset()
        self.model.logits = [float('nan'),1]
        self.process("كلام ناقص")
        self.assertIsNone(self.detector.last_decision)
        self.assertTrue(self.detector.text_worker.is_alive())
        self.assertAlmostEqual(self.callback.call_args.args[0],1.25*0.5)
        self.model.logits = [0,4]
        self.assertIsNotNone(self.process("الطلب ديالي وصل"))

    def test_english_uses_original_temperature_and_right_truncation(self):
        detector, tokenizer, _, _ = make_detector(self.directory.name,self.callback,profile="english")
        self.addCleanup(detector.shutdown)
        detector.calculate_waiting_time("This is complete.")
        detector.text_queue.join()
        self.assertEqual(tokenizer.truncation_side,"right")
        self.assertAlmostEqual(detector.get_completion_probability("This is complete"),1/(1+math.exp(-4)))
        self.assertIsNone(detector.last_decision)


if __name__ == '__main__':
    unittest.main()
