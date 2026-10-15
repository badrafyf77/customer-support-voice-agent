"""Recorder configuration changes for Darija, without changing decoding or VAD."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path


def darija_recorder_config(base: dict, model_path: str, realtime_model_path: str | None = None) -> dict:
    model = Path(model_path).expanduser().resolve()
    if not model_path or not model.is_dir():
        raise ValueError("Darija STT requires the prepared CTranslate2 export directory")
    if realtime_model_path and Path(realtime_model_path).expanduser().resolve() != model:
        raise ValueError("Darija partial and final STT must use the same prepared export")
    config = deepcopy(base)
    config.update(model=str(model), realtime_model_type=str(model),
                  use_main_model_for_realtime=True, language="ar",
                  initial_prompt=None, initial_prompt_realtime=None)
    return config


def normalize_transcript_comparison(text: str) -> str:
    """Normalize only comparison keys; keep raw callback/transcript content intact."""
    return " ".join("".join(char for char in text.lower()
                            if char.isalnum() or char.isspace()).split())
