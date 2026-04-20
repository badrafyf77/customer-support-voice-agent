"""
Speaker verification utilities backed by SpeechBrain's ECAPA-TDNN model.

Used by the oral exam pipeline to compare answers spoken during an attempt
against a reference voice captured at exam start. Embeddings are 192-d
float vectors; we compare with cosine similarity.

The model is heavy (loads PyTorch + speechbrain weights) so it is loaded
lazily on first use and reused for the lifetime of the process.
"""
from __future__ import annotations

import io
import logging
import os
import threading
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# 16 kHz mono is the model's expected input.
TARGET_SAMPLE_RATE = 16000
# ECAPA-TDNN needs at least ~2s of audio to produce a stable embedding.
MIN_SAMPLES_FOR_EMBEDDING = TARGET_SAMPLE_RATE * 2
# Default similarity threshold below which we flag a likely speaker mismatch.
DEFAULT_MATCH_THRESHOLD = float(os.getenv("VOICE_VERIFICATION_THRESHOLD", "0.65"))


_model = None
_model_lock = threading.Lock()


def _get_model():
    """Lazy-load the SpeechBrain ECAPA-TDNN speaker recognition model."""
    global _model
    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model
        from speechbrain.inference.speaker import SpeakerRecognition

        savedir = os.getenv(
            "SPEAKER_VERIFICATION_MODEL_DIR",
            "pretrained_models/spkrec-ecapa-voxceleb",
        )
        logger.info("🗣️🔐 Loading speaker verification model (savedir=%s)", savedir)
        _model = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir=savedir,
        )
        logger.info("🗣️🔐 Speaker verification model ready")
        return _model


def _normalize_audio_to_float32(samples: np.ndarray) -> np.ndarray:
    """Convert int16 / float64 inputs to float32 in the [-1, 1] range."""
    if samples.dtype == np.int16:
        return samples.astype(np.float32) / 32768.0
    if samples.dtype == np.float32:
        return samples
    return samples.astype(np.float32)


def extract_embedding_from_samples(
    samples: np.ndarray,
    sample_rate: int,
) -> Optional[np.ndarray]:
    """Compute a single 192-d speaker embedding from raw audio samples.

    Returns ``None`` if the audio is too short or empty. Resamples to 16 kHz
    when needed.
    """
    if samples is None or samples.size == 0:
        return None

    audio = _normalize_audio_to_float32(samples)

    if sample_rate != TARGET_SAMPLE_RATE:
        import torch
        import torchaudio

        tensor = torch.from_numpy(audio).unsqueeze(0)
        tensor = torchaudio.functional.resample(tensor, sample_rate, TARGET_SAMPLE_RATE)
        audio = tensor.squeeze(0).cpu().numpy()

    if audio.shape[0] < MIN_SAMPLES_FOR_EMBEDDING:
        logger.debug(
            "🗣️🔐 Audio too short for embedding (%d samples, need %d)",
            audio.shape[0],
            MIN_SAMPLES_FOR_EMBEDDING,
        )
        return None

    import torch

    model = _get_model()
    tensor = torch.from_numpy(audio).unsqueeze(0)
    with torch.no_grad():
        embedding = model.encode_batch(tensor).squeeze(0).squeeze(0).detach().cpu().numpy()
    return embedding.astype(np.float32)


def extract_embedding_from_wav_bytes(wav_bytes: bytes) -> Optional[np.ndarray]:
    """Read a WAV/audio blob and compute the speaker embedding.

    The blob may be WAV, MP3, or anything torchaudio can decode (handled via
    soundfile + ffmpeg fallback). We also accept WebM/OGG by routing through
    pydub when torchaudio fails.
    """
    if not wav_bytes:
        return None

    samples, sample_rate = _decode_audio_bytes(wav_bytes)
    if samples is None:
        return None
    return extract_embedding_from_samples(samples, sample_rate)


def _decode_audio_bytes(blob: bytes) -> Tuple[Optional[np.ndarray], int]:
    """Decode an audio container into mono float samples.

    Tries torchaudio first (handles WAV/FLAC), then falls back to pydub which
    can decode WebM/OGG/MP3 via ffmpeg — useful because browsers usually
    deliver WebM from MediaRecorder.
    """
    try:
        import torchaudio

        wav_io = io.BytesIO(blob)
        waveform, sample_rate = torchaudio.load(wav_io)
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)
        return waveform.squeeze(0).cpu().numpy(), int(sample_rate)
    except Exception as exc:
        logger.debug("🗣️🔐 torchaudio decode failed (%s); trying pydub fallback", exc)

    try:
        from pydub import AudioSegment

        segment = AudioSegment.from_file(io.BytesIO(blob))
        segment = segment.set_channels(1)
        sample_rate = segment.frame_rate
        samples = np.array(segment.get_array_of_samples(), dtype=np.int16)
        return samples, int(sample_rate)
    except Exception as exc:
        logger.error("🗣️🔐 Could not decode audio blob for verification: %s", exc)
        return None, 0


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Standard cosine similarity in [-1, 1]."""
    a = np.asarray(a, dtype=np.float32).flatten()
    b = np.asarray(b, dtype=np.float32).flatten()
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def embedding_to_list(embedding: np.ndarray) -> List[float]:
    """JSON-serializable representation of an embedding."""
    return [float(x) for x in np.asarray(embedding).flatten().tolist()]


def list_to_embedding(values) -> Optional[np.ndarray]:
    """Inverse of ``embedding_to_list`` — tolerates None / empty input."""
    if not values:
        return None
    try:
        return np.asarray(values, dtype=np.float32)
    except Exception as exc:
        logger.warning("🗣️🔐 Could not parse stored embedding: %s", exc)
        return None
