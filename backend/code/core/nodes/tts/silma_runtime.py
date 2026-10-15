"""Cached SILMA inference in the isolated GPU service process."""
from __future__ import annotations

import json
from pathlib import Path
import time

from core.config import get_env
from core.model_artifacts import LOCK_PATH, file_sha256, inspect_model_files
from core.nodes.tts.silma_model import load_model
from core.nodes.tts.silma_config import selected_voice
from core.nodes.tts.silma_text import estimated_frames


class SilmaRuntime:
    sample_rate = 24000
    audio_format = "pcm_s16le"

    def __init__(self, model_root: Path, voice_id: str = "voice0", variant: str = "ema"):
        import numpy as np
        import soundfile as sf
        import torch
        from vocos import Vocos

        if not torch.cuda.is_available():
            raise RuntimeError("SILMA requires an NVIDIA CUDA GPU.")
        lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        for role in ("tts", "vocoder"):
            inspect_model_files(model_root, lock["models"][role])
        voice_root = LOCK_PATH.parent / "voices"
        voices = json.loads((voice_root / "voices.json").read_text(encoding="utf-8"))["voices"]
        if voice_id not in voices:
            raise ValueError(f"Unknown SILMA voice: {voice_id}")
        voice = voices[voice_id]
        reference = voice_root / voice["audio"]
        if file_sha256(reference) != voice["sha256"]:
            raise RuntimeError("SILMA reference audio does not match its manifest.")
        waveform, rate = sf.read(reference, dtype="float32", always_2d=True)
        if rate != self.sample_rate or waveform.shape[1] != 1 or not np.isfinite(waveform).all():
            raise ValueError("Reference must be finite mono 24 kHz audio.")
        rms = float(np.sqrt(np.mean(waveform ** 2)))
        if rms <= 0.001:
            raise ValueError("Reference must contain audible speech.")
        self.reference_audio = torch.from_numpy(waveform.T.copy()).to("cuda")
        if rms < 0.1:
            self.reference_audio *= 0.1 / rms
        self.reference_text = voice["reference_text"].strip()
        self.model, self.config = load_model(
            model_root / lock["models"]["tts"]["directory"], variant=variant,
        )
        if self.config["mel_spec"]["target_sample_rate"] != self.sample_rate:
            raise ValueError("SILMA checkpoint must use a 24 kHz mel spectrogram.")
        vocoder_root = model_root / lock["models"]["vocoder"]["directory"]
        self.vocoder = Vocos.from_hparams(str(vocoder_root / "config.yaml"))
        self.vocoder.load_state_dict(torch.load(
            vocoder_root / "pytorch_model.bin", map_location="cpu", weights_only=True,
        ))
        self.vocoder.to("cuda").eval()
        self.hop = self.config["mel_spec"]["hop_length"]
        self.reference_frames = self.reference_audio.shape[-1] // self.hop
        self.max_total_frames = 30 * self.sample_rate // self.hop
        self.max_phrase_bytes = int(
            (self.max_total_frames - self.reference_frames) /
            self.reference_frames * len(self.reference_text.encode("utf-8"))
        )
        if self.max_phrase_bytes < 4:
            raise ValueError("Reference leaves no room for generated speech.")
        self.tts_inference_time_ms = 0.0
        self.metadata = {
            "model_id": lock["models"]["tts"]["repo_id"],
            "revision": lock["models"]["tts"]["revision"],
            "vocoder_id": lock["models"]["vocoder"]["repo_id"],
            "vocoder_revision": lock["models"]["vocoder"]["revision"],
            "voice_id": voice_id, "variant": variant, "reference_sha256": voice["sha256"],
            "sample_rate": self.sample_rate, "audio_format": self.audio_format,
            "channels": 1,
            "steps": 32, "max_phrase_bytes": self.max_phrase_bytes,
        }

    def synthesize(self, text: str) -> bytes:
        import numpy as np
        import torch

        text = text.strip()
        duration = estimated_frames(text, self.reference_text, self.reference_frames)
        if duration > self.max_total_frames:
            raise ValueError("Phrase exceeds the reference-based duration limit; split it.")
        started = time.monotonic()
        with torch.inference_mode():
            mel, _ = self.model.sample(
                cond=self.reference_audio, text=[self.reference_text + " " + text],
                duration=duration, steps=32, cfg_strength=2.0, sway_sampling_coef=-1.0,
            )
            waveform = self.vocoder.decode(
                mel[:, self.reference_frames:, :].float().permute(0, 2, 1)
            ).reshape(-1).cpu().numpy()
        if not waveform.size or not np.isfinite(waveform).all():
            raise RuntimeError("SILMA produced empty or nonfinite audio.")
        pcm = (np.clip(waveform, -1.0, 1.0) * 32767).round().astype("<i2").tobytes()
        self.tts_inference_time_ms = (time.monotonic() - started) * 1000
        return pcm

    def warmup(self):
        self.synthesize("سلام، كيفاش نقدر نعاونك؟")


def load_runtime() -> SilmaRuntime:
    root = get_env("DARIJA_MODEL_ROOT")
    if not root:
        raise RuntimeError("DARIJA_MODEL_ROOT is required for SILMA startup.")
    voice_id, variant = selected_voice()
    return SilmaRuntime(
        Path(root).expanduser().resolve(),
        voice_id=voice_id,
        variant=variant,
    )
