"""Bounded phrase segmentation; leave display text and identifiers untouched."""
from __future__ import annotations

from collections.abc import Iterable, Iterator

END_MARKS = frozenset(".!?؟\n")
SOFT_MARKS = frozenset(",;:،؛")


def iter_phrases(
    chunks: Iterable[str], max_chars: int = 120, max_bytes: int = 400,
) -> Iterator[str]:
    if max_chars < 1 or max_bytes < 4:
        raise ValueError("Phrase limits must fit at least one Unicode character.")
    buffer = ""
    for chunk in chunks:
        for char in chunk:
            # Wait for a word boundary after a period, so decimals and names
            # such as 3.14 / example.com survive token chunk boundaries.
            if buffer.endswith(".") and char.isspace():
                if buffer.strip():
                    yield buffer.strip()
                buffer = ""
            if len(buffer) >= max_chars or len((buffer + char).encode("utf-8")) > max_bytes:
                # Prefer a word boundary; fall back to splitting a long identifier
                # without changing or dropping any of its characters.
                boundary = buffer.rfind(" ")
                if boundary > len(buffer) // 2:
                    head, buffer = buffer[:boundary], buffer[boundary + 1:]
                else:
                    head, buffer = buffer, ""
                if head.strip():
                    yield head.strip()
            buffer += char
            if (char in END_MARKS and char != ".") or (char in SOFT_MARKS and len(buffer.strip()) >= 12):
                if buffer.strip():
                    yield buffer.strip()
                buffer = ""
    if buffer.strip():
        yield buffer.strip()


def estimated_frames(
    text: str, reference_text: str, reference_frames: int, speed: float = 1.0,
) -> int:
    """F5 speaking-rate estimate using UTF-8 text length, including reference."""
    if not text.strip() or not reference_text.strip() or reference_frames <= 0 or speed <= 0:
        raise ValueError("Nonempty speech/reference and positive duration/speed are required.")
    text_bytes = len(text.encode("utf-8"))
    # The inspected F5 inference path slows very short text to avoid clipped
    # acknowledgments. This is synthesis duration, not a turn-detection wait.
    local_speed = speed * (0.3 if text_bytes < 10 else 1.0)
    generated = round(reference_frames * text_bytes /
                      len(reference_text.encode("utf-8")) / local_speed)
    return reference_frames + max(1, generated)
