"""Shared normalization for Darija classification training and inference."""
import unicodedata


def normalize_turn_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(str.maketrans({"ݣ": "گ", "ڴ": "گ", "ڭ": "گ"}))
    # Remove punctuation cues so the classifier cannot just learn ASR punctuation.
    # Preserve Arabic letters, Latin code-switches, numbers and accents.
    text = "".join(
        " " if unicodedata.category(c).startswith("P") else c
        for c in text if unicodedata.category(c) != "Cf"
    )
    return " ".join(text.split())
