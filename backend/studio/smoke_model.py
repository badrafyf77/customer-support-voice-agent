"""Load a single pinned model in its own process; no session integration."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from core.model_artifacts import LOCK_PATH, inspect_model_files


def smoke(role: str, root: Path, audio: str | None, variant: str) -> dict:
    lock = json.loads(LOCK_PATH.read_text())
    spec = lock["models"][role]
    root = root.expanduser().resolve()
    inspect_model_files(root, spec)
    directory = root / spec["directory"]
    started = time.monotonic()
    result = {"role": role, "repo_id": spec["repo_id"], "revision": spec["revision"]}
    if role == "stt":
        import ctranslate2
        from faster_whisper import WhisperModel
        if not ctranslate2.get_cuda_device_count():
            raise RuntimeError("An NVIDIA GPU is required for the Studio ASR check.")
        model = WhisperModel(str(directory), device="cuda", compute_type="float16")
        if audio:
            segments, _ = model.transcribe(audio, language="ar", beam_size=1)
            result["transcript"] = " ".join(segment.text for segment in segments)
        result["memory_note"] = "Use nvidia-smi; PyTorch counters exclude CTranslate2."
    else:
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification, AutoModelForCausalLM
        if role != "turn" and not torch.cuda.is_available():
            raise RuntimeError("An NVIDIA GPU is required for this Studio check.")
        if role != "turn" and torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
        if role == "turn":
            from core.turndetect import TurnDetection
            detector = TurnDetection(None, profile="darija", model_path=str(directory))
            try:
                cases = json.loads(Path(__file__).with_name("turn_cases.json").read_text())
                result["decisions"] = [{**case,
                                        **detector.get_completion_decision(case["text"]).diagnostics()}
                                       for case in cases]
            finally:
                detector.shutdown()
            result["device"] = "cpu"
            result["note"] = "Calibrated Darija contract; recorder replay and live quality review remain separate."
        elif role == "llm":
            tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
            model = AutoModelForCausalLM.from_pretrained(
                directory, local_files_only=True, torch_dtype=torch.bfloat16,
            ).to("cuda").eval()
            inputs = tokenizer.apply_chat_template(
                [{"role": "user", "content": "جاوب بالدارجة المغربية: السلام عليكم"}],
                add_generation_prompt=True, return_tensors="pt", return_dict=True,
            ).to("cuda")
            with torch.inference_mode():
                generated = model.generate(**inputs, max_new_tokens=32, do_sample=False)
            result["reply"] = tokenizer.decode(generated[0, inputs["input_ids"].shape[-1]:], skip_special_tokens=True)
            result["eos_token_id"] = model.generation_config.eos_token_id
        elif role == "tts":
            from silma_loader import load_model
            from vocos import Vocos
            vocoder_spec = lock["models"]["vocoder"]
            inspect_model_files(root, vocoder_spec)
            vocoder_dir = root / vocoder_spec["directory"]
            model, _ = load_model(directory, variant=variant)
            vocoder = Vocos.from_hparams(str(vocoder_dir / "config.yaml"))
            vocoder.load_state_dict(torch.load(
                vocoder_dir / "pytorch_model.bin", map_location="cpu", weights_only=True,
            ))
            vocoder.to("cuda").eval()
            result["variant"] = variant
            result["note"] = "Strict weights + vocoder load only; listening/synthesis is phase 2."
        if role != "turn" and torch.cuda.is_available():
            torch.cuda.synchronize()
            result["torch_peak_allocated_mib"] = round(torch.cuda.max_memory_allocated() / 2**20, 1)
    result["load_and_probe_seconds"] = round(time.monotonic() - started, 3)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=["stt", "turn", "llm", "tts"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--audio", help="Optional Darija WAV for STT")
    parser.add_argument("--variant", choices=["main", "ema"], default="ema")
    args = parser.parse_args()
    try:
        print(json.dumps(smoke(args.role, args.root, args.audio, args.variant), ensure_ascii=False, indent=2))
    except Exception as exc:
        parser.exit(1, f"{args.role} independent model check failed: {exc}\n")
