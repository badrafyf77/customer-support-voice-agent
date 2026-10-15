"""Prepare the selected Whisper LoRA directly from HF as a ready-to-run CT2 model.

Reproduces the inspected original export recipe on CPU. No training, GPU, Modal
access or manual model upload is required. All output hashes must match the known
correct export before it can replace the persistent runtime model.
"""
from __future__ import annotations

import argparse
import gc
from importlib.metadata import version
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from core.config import get_env
from core.model_artifacts import LOCK_PATH, inspect_model_files

RECIPE = {
    "torch": "2.6.0", "transformers": "4.57.6", "peft": "0.20.0",
    "huggingface-hub": "0.36.2", "accelerate": "1.6.0", "ctranslate2": "4.6.0",
}
EXPECTED_LORA_PARAMETERS = 13926400


class ExportError(RuntimeError):
    """A safe-to-display local validation failure."""


def normalize_fast_tokenizer(path, tokenizer_class):
    """Keep original token IDs while writing CT2-compatible BPE merge entries."""
    before = tokenizer_class.from_file(str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    data["model"]["merges"] = [" ".join(item) if isinstance(item, list) else item
                                for item in data["model"]["merges"]]
    if data["model"].get("ignore_merges") is False:
        data["model"].pop("ignore_merges")
    serialized = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    after = tokenizer_class.from_str(serialized)
    for text in ("بغيت نعرف واش", "شكرا بزاف", "عندي compte ونسيت الكود", "الطلب 1234"):
        if before.encode(text).ids != after.encode(text).ids:
            raise ExportError("Tokenizer conversion changed token IDs")
    path.write_text(serialized, encoding="utf-8")


def build_export(directory: Path, spec: dict, threads: int):
    import torch
    from ctranslate2.converters import TransformersConverter
    from peft import PeftModel
    from tokenizers import Tokenizer
    from transformers import WhisperForConditionalGeneration, WhisperProcessor, WhisperTokenizerFast

    installed = {name: version(name) for name in RECIPE}
    if any(installed[name].split("+")[0] != expected for name, expected in RECIPE.items()):
        raise ExportError("Use the pinned asr-export environment to reproduce the correct ASR export")
    torch.set_num_threads(threads)
    token = get_env("HF_TOKEN")
    print(f"Downloading pinned ASR base: {spec['base_model']}@{spec['base_revision']}", flush=True)
    base = WhisperForConditionalGeneration.from_pretrained(
        spec["base_model"], revision=spec["base_revision"], token=token,
        torch_dtype=torch.float16, low_cpu_mem_usage=True,
    )
    print(f"Loading trained Darija adapter: {spec['repo_id']}@{spec['revision']}", flush=True)
    adapter = PeftModel.from_pretrained(
        base, spec["repo_id"], revision=spec["revision"], token=token, is_trainable=False,
    )
    if adapter.peft_config["default"].base_model_name_or_path != spec["base_model"]:
        raise ExportError("Adapter base differs from the selected pinned Whisper base")
    lora = {key: parameter for key, parameter in adapter.named_parameters() if "lora_" in key}
    count = sum(parameter.numel() for parameter in lora.values())
    if count != EXPECTED_LORA_PARAMETERS or not any(
        torch.count_nonzero(parameter).item() for key, parameter in lora.items() if "lora_B" in key
    ):
        raise ExportError("Expected trained nonzero Darija LoRA weights were not loaded")
    print("Merging trained adapter on CPU; no training is performed.", flush=True)
    merged = adapter.merge_and_unload(safe_merge=True).eval()
    merged_root = directory / "merged"
    merged.save_pretrained(merged_root, safe_serialization=True)
    processor = WhisperProcessor.from_pretrained(spec["repo_id"], revision=spec["revision"], token=token)
    processor.save_pretrained(merged_root)
    tokenizer = WhisperTokenizerFast.from_pretrained(spec["repo_id"], revision=spec["revision"], token=token)
    tokenizer.save_pretrained(merged_root)
    normalize_fast_tokenizer(merged_root / "tokenizer.json", Tokenizer)
    del merged, adapter, base, lora
    gc.collect()
    converted = directory / "ctranslate2"
    print("Converting merged Whisper to FP16 CTranslate2.", flush=True)
    TransformersConverter(
        str(merged_root), copy_files=["tokenizer.json", "preprocessor_config.json"],
    ).convert(str(converted), quantization="float16")
    return {"packages": installed, "lora_parameters": count, "safe_merge": True,
            "device": "cpu", "quantization": "float16", "training_performed": False}


def prepare_export(root: Path, spec: dict, builder=build_export, threads=4):
    root.mkdir(parents=True, exist_ok=True)
    try:
        inspect_model_files(root, spec)
    except RuntimeError:
        pass
    else:
        print("Corrected ASR export already verified; reusing cached ready-to-run files.", flush=True)
        return root / spec["directory"]
    with tempfile.TemporaryDirectory(prefix=".asr-build-", dir=root) as temporary:
        workspace = Path(temporary)
        details = builder(workspace, spec, threads)
        try:
            files = inspect_model_files(workspace, {**spec, "directory": "ctranslate2"})
        except RuntimeError as exc:
            raise ExportError(str(exc)) from None
        # Never publish a partial/wrong export or silently accept another model.
        target, backup = root / spec["directory"], workspace / "previous"
        if target.exists():
            target.replace(backup)
        try:
            (workspace / "ctranslate2").replace(target)
        except BaseException:
            if backup.exists():
                backup.replace(target)
            raise
        report = {"repo_id": spec["repo_id"], "revision": spec["revision"],
                  "base_model": spec["base_model"], "base_revision": spec["base_revision"],
                  "files": files, **details}
        (root / "asr-export.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=get_env("ASR_EXPORT_CPU_THREADS", "4") or "4")
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be positive")
    spec = json.loads(LOCK_PATH.read_text())["models"]["stt"]
    try:
        output = prepare_export(args.root.expanduser().resolve(), spec, threads=args.threads)
    except Exception as exc:
        # HTTP errors can carry sensitive request details; keep auth errors terse.
        if isinstance(exc, ExportError):
            message = str(exc)
        else:
            message = f"{type(exc).__name__}; check HF_TOKEN/private-model access, CPU memory/disk and export logs"
        parser.exit(1, f"ASR export failed: {message}\n")
    print(f"Ready-to-run Darija ASR verified: {output}")


if __name__ == "__main__":
    main()
