import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from core.config import load_agent_config, load_runtime_config
from core.model_artifacts import inspect_model_files, validate_prepared_models


class RuntimeSelectionTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.dotenv = patch("core.config.load_env_file_if_available")
        self.dotenv.start()
        self.addCleanup(self.environment.stop)
        self.addCleanup(self.dotenv.stop)

    def test_default_warms_chat_in_english(self):
        agent, profile, config = load_runtime_config()
        self.assertEqual((agent, profile, config["language"]), ("chat", "english", "en"))
        self.assertEqual(config["stt_model"], "medium.en")

    def test_darija_selects_intended_models(self):
        os.environ.update(VOICE_AGENT="chat", VOICE_PROFILE="darija", STT_MODEL="/models/asr")
        agent, profile, config = load_runtime_config()
        self.assertEqual((agent, profile), ("chat", "darija"))
        self.assertEqual(config["language"], "ar")
        self.assertEqual(config["stt_model"], "/models/asr")
        self.assertEqual(config["stt_realtime_model"], "/models/asr")
        self.assertEqual(config["llm_model"], "MBZUAI-Paris/Atlas-Chat-2B")
        self.assertEqual(config["tts_engine"], "silma")

    def test_deployment_stt_values_survive_yaml(self):
        os.environ.update(STT_MODEL="/custom/final", STT_REALTIME_MODEL="/custom/partial")
        config = load_agent_config("chat")
        self.assertEqual((config["stt_model"], config["stt_realtime_model"]),
                         ("/custom/final", "/custom/partial"))

    def test_explicit_exam_remains_available(self):
        os.environ["VOICE_AGENT"] = "exam"
        self.assertEqual(load_runtime_config()[0], "exam")

    def test_rejects_invalid_selection_and_darija_exam(self):
        for agent, profile in [("missing", "english"), ("chat", "missing"), ("exam", "darija")]:
            with self.subTest(agent=agent, profile=profile):
                with self.assertRaises(ValueError):
                    load_agent_config(agent, profile)

    def test_scoped_overrides_keep_precedence(self):
        os.environ.update(VOICE_AGENT_LANGUAGE="ar", CHAT_LANGUAGE="fr")
        self.assertEqual(load_agent_config("chat")["language"], "fr")


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / "asr").mkdir()
        (self.root / "asr" / "model.bin").write_bytes(b"correct-export")
        self.files = {"model.bin": {
            "sha256": hashlib.sha256(b"correct-export").hexdigest(),
            "bytes": len(b"correct-export"),
        }}
        self.spec = {"repo_id": "correct-darija", "revision": "a" * 40,
                     "directory": "asr", "files": self.files}
        self.lock = self.root / "lock.json"
        self.lock.write_text(json.dumps({"models": {"stt": self.spec}}))
        self.receipt = {"models": {"stt": {
            "repo_id": self.spec["repo_id"], "revision": self.spec["revision"], "files": self.files,
        }}}
        (self.root / "prepared.json").write_text(json.dumps(self.receipt))

    def test_accepts_correct_export(self):
        result = validate_prepared_models(self.root, self.lock)
        self.assertEqual(result["stt"]["path"], str(self.root / "asr"))

    def test_subset_receipt_does_not_claim_all_models_are_ready(self):
        other = {**self.spec, "directory": "turn"}
        self.lock.write_text(json.dumps({"models": {"stt": self.spec, "turn": other}}))
        self.assertIn("stt", validate_prepared_models(self.root, self.lock, roles=["stt"]))
        with self.assertRaisesRegex(RuntimeError, "identity or revision"):
            validate_prepared_models(self.root, self.lock)
        with self.assertRaises(ValueError):
            validate_prepared_models(self.root, self.lock, roles=["unknown"])

    def test_rejects_different_asr_export(self):
        (self.root / "asr" / "model.bin").write_bytes(b"wrong-125h")
        with self.assertRaisesRegex(RuntimeError, "provenance mismatch"):
            validate_prepared_models(self.root, self.lock)

    def test_missing_private_model_fails_with_identity(self):
        (self.root / "asr" / "model.bin").unlink()
        with self.assertRaisesRegex(RuntimeError, "Missing correct-darija@"):
            inspect_model_files(self.root, self.spec)

    def test_missing_receipt_fails(self):
        (self.root / "prepared.json").unlink()
        with self.assertRaisesRegex(RuntimeError, "Missing model preparation receipt"):
            validate_prepared_models(self.root, self.lock)

    def test_receipt_cannot_claim_another_revision(self):
        self.receipt["models"]["stt"]["revision"] = "b" * 40
        (self.root / "prepared.json").write_text(json.dumps(self.receipt))
        with self.assertRaisesRegex(RuntimeError, "identity or revision"):
            validate_prepared_models(self.root, self.lock)

    def test_detects_changes_to_unhashed_snapshot_files(self):
        self.spec["files"] = {"model.bin": {}}
        self.lock.write_text(json.dumps({"models": {"stt": self.spec}}))
        (self.root / "asr" / "model.bin").write_bytes(b"changed-after-preparation")
        with self.assertRaisesRegex(RuntimeError, "changed since download"):
            validate_prepared_models(self.root, self.lock)


if __name__ == "__main__":
    unittest.main()
