"""
Per-connection helper that verifies the student's voice during an oral exam
against a permanent reference stored on their profile.

The reference is recorded once by the student before their first exam (voice
enrollment). It is loaded from the profile at WebSocket connect time and
reused for every attempt they ever take, making mid-exam impersonation
detectable even if the substitute stays for the full session.

Random sampling: not every answer is verified — the sampling probability
(default 0.6) is chosen at runtime so the student cannot predict which turns
will be checked. Extraction runs in a background thread to keep the live
audio pipeline unblocked.
"""
from __future__ import annotations

import logging
import os
import random
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from speaker_verification import (
    DEFAULT_MATCH_THRESHOLD,
    TARGET_SAMPLE_RATE,
    cosine_similarity,
    extract_embedding_from_samples,
    list_to_embedding,
)

logger = logging.getLogger(__name__)

DEFAULT_SAMPLING_PROBABILITY = float(os.getenv("VOICE_VERIFICATION_SAMPLE_PROB", "0.6"))


class VoiceVerificationManager:
    """Passive speaker-verification for a single exam attempt."""

    def __init__(
        self,
        attempt_id: Optional[str],
        threshold: float = DEFAULT_MATCH_THRESHOLD,
        sampling_probability: float = DEFAULT_SAMPLING_PROBABILITY,
    ):
        self.attempt_id = attempt_id
        self.threshold = threshold
        self.sampling_probability = max(0.0, min(1.0, sampling_probability))
        self._reference: Optional[np.ndarray] = None
        self._reference_meta: Dict[str, Any] = {}
        self._checks: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._answer_index = 0

    # --------------------------------------------------------------- reference
    def has_reference(self) -> bool:
        return self._reference is not None

    def set_reference_from_embedding(
        self,
        embedding,
        meta: Optional[Dict[str, Any]] = None,
    ) -> bool:
        parsed = list_to_embedding(embedding) if not isinstance(embedding, np.ndarray) else embedding
        if parsed is None or parsed.size == 0:
            return False
        with self._lock:
            self._reference = parsed
            self._reference_meta = dict(meta or {})
        logger.info(
            "🗣️🔐 User voice reference loaded for attempt=%s (dim=%d)",
            self.attempt_id,
            parsed.size,
        )
        return True

    # ------------------------------------------------------------- per-answer
    def submit_answer_audio(
        self,
        samples: np.ndarray,
        transcript: str,
        sample_rate: int = TARGET_SAMPLE_RATE,
    ) -> None:
        """Possibly verify an answer's audio against the stored user reference.

        If no reference is loaded (student hasn't enrolled yet), the check is
        silently skipped. Otherwise the answer is randomly sampled with
        ``sampling_probability`` so the student cannot predict which turns
        are checked.
        """
        if self._reference is None:
            logger.debug("🗣️🔐 No user voice reference — verification skipped for this turn")
            return
        if samples is None or samples.size == 0:
            return

        with self._lock:
            current_index = self._answer_index
            self._answer_index += 1

        if random.random() >= self.sampling_probability:
            logger.debug(
                "🗣️🔐 Answer %d not selected for sampling (p=%.2f)",
                current_index,
                self.sampling_probability,
            )
            return

        snippet = (transcript or "").strip()
        snippet = snippet[:200] + ("…" if len(snippet) > 200 else "")

        thread = threading.Thread(
            target=self._verify_in_thread,
            args=(np.copy(samples), sample_rate, current_index, snippet),
            name=f"VoiceVerify-{current_index}",
            daemon=True,
        )
        thread.start()

    def _verify_in_thread(
        self,
        samples: np.ndarray,
        sample_rate: int,
        answer_index: int,
        transcript_excerpt: str,
    ) -> None:
        started = time.time()
        try:
            embedding = extract_embedding_from_samples(samples, sample_rate)
            if embedding is None:
                logger.info("🗣️🔐 Answer %d skipped (audio too short for embedding)", answer_index)
                self._record_check(
                    {
                        "answer_index": answer_index,
                        "score": None,
                        "is_match": None,
                        "skipped_reason": "audio_too_short",
                        "transcript_excerpt": transcript_excerpt,
                        "checked_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                return

            with self._lock:
                reference = self._reference
            if reference is None:
                return

            score = cosine_similarity(reference, embedding)
            is_match = score >= self.threshold
            elapsed = time.time() - started
            logger.info(
                "🗣️🔐 Answer %d voice score=%.3f (threshold=%.2f, match=%s, %.2fs)",
                answer_index,
                score,
                self.threshold,
                is_match,
                elapsed,
            )
            self._record_check(
                {
                    "answer_index": answer_index,
                    "score": round(float(score), 4),
                    "is_match": bool(is_match),
                    "transcript_excerpt": transcript_excerpt,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        except Exception as exc:
            logger.error("🗣️🔐 Verification failed for answer %d: %s", answer_index, exc, exc_info=True)
            self._record_check(
                {
                    "answer_index": answer_index,
                    "score": None,
                    "is_match": None,
                    "skipped_reason": f"error: {exc}",
                    "transcript_excerpt": transcript_excerpt,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    def _record_check(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._checks.append(payload)

    # -------------------------------------------------------------- summary
    def build_summary(self) -> Dict[str, Any]:
        with self._lock:
            checks = list(self._checks)
            has_reference = self._reference is not None
            reference_meta = dict(self._reference_meta)

        scored = [c for c in checks if isinstance(c.get("score"), (int, float))]
        flagged = [c for c in scored if c.get("is_match") is False]

        if scored:
            scores = [float(c["score"]) for c in scored]
            average_score = round(sum(scores) / len(scores), 4)
            min_score = round(min(scores), 4)
        else:
            average_score = None
            min_score = None

        return {
            "enabled": True,
            "has_reference": has_reference,
            "threshold": self.threshold,
            "sampling_probability": self.sampling_probability,
            "checks": checks,
            "summary": {
                "total_checks": len(scored),
                "flagged_count": len(flagged),
                "average_score": average_score,
                "min_score": min_score,
                "any_mismatch": bool(flagged),
            },
            "reference_meta": reference_meta,
        }
