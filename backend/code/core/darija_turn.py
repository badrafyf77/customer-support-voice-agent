"""Pinned Darija completion contract; timing remains in core.turndetect."""
from __future__ import annotations

from dataclasses import dataclass, asdict
import math

from core.darija_turn_text import normalize_turn_text
from core.darija_turn_policy import completion_override

TEMPERATURE = 3.9
THRESHOLD = 0.7780777968696678  # Full saved precision (0.7781 in the plan).
MAX_LENGTH = 128


@dataclass(frozen=True)
class CompletionDecision:
    normalized_text: str
    completion_probability: float
    decision_score: float
    syntax_override: int | None
    threshold: float = THRESHOLD

    @property
    def is_complete(self) -> bool:
        return self.decision_score >= self.threshold

    def diagnostics(self) -> dict:
        return {**asdict(self), "is_complete": self.is_complete}


def calibrated_probability(logits, temperature=TEMPERATURE) -> float:
    if len(logits) != 2 or not all(math.isfinite(float(value)) for value in logits):
        raise ValueError("Turn classifier must return two finite logits")
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError("Turn temperature must be finite and positive")
    difference = (float(logits[1]) - float(logits[0])) / temperature
    # Stable two-class softmax, including extreme logits.
    if difference >= 0:
        return 1 / (1 + math.exp(-difference))
    exp_difference = math.exp(difference)
    return exp_difference / (1 + exp_difference)


def decision(text: str, probability: float) -> CompletionDecision:
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("Turn completion probability must be finite and in [0,1]")
    override = completion_override(text)
    return CompletionDecision(normalize_turn_text(text), probability,
                              probability if override is None else float(override), override)


def validate_model_config(config) -> None:
    expected = {"turn_detection_max_length": MAX_LENGTH,
                "turn_detection_normalization": "darija_v1",
                "turn_detection_policy": "darija_calls_v2"}
    for name, value in expected.items():
        if getattr(config, name, None) != value:
            raise ValueError(f"Darija completion configuration mismatch: {name}")
    for name, value in (("turn_detection_temperature", TEMPERATURE),
                        ("turn_detection_threshold", THRESHOLD)):
        actual = getattr(config, name, None)
        if not isinstance(actual, (int, float)) or not math.isclose(actual, value, rel_tol=0, abs_tol=1e-12):
            raise ValueError(f"Darija completion calibration mismatch: {name}")
    labels = getattr(config, "id2label", {})
    if {str(key): value for key, value in labels.items()} != {"0": "incomplete", "1": "complete"}:
        raise ValueError("Darija completion label mapping must be incomplete=0, complete=1")
