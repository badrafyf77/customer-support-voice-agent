from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import collections
import threading
import queue
import time
import re

from core.config import get_env
from core import darija_turn
from core.darija_turn_text import normalize_turn_text

# Configuration constants
model_dir_local = "KoljaB/SentenceFinishedClassification"
model_dir_cloud = "/root/models/sentenceclassification/"
sentence_end_marks = ['.', '!', '?', '。', '؟'] # Characters considered sentence endings

# Anchor points for probability-to-pause interpolation
anchor_points = [
    (0.0, 1.0), # Probability 0.0 maps to pause 1.0
    (1.0, 0.0)  # Probability 1.0 maps to pause 0.0
]


def _resolve_turn_detection_device() -> torch.device:
    import torch
    configured_device = (get_env("TURN_DETECTION_DEVICE", "auto") or "auto").strip().lower()

    if configured_device == "cpu":
        return torch.device("cpu")

    if configured_device == "cuda":
        if torch.cuda.is_available():
            return torch.device("cuda")
        logger.warning("🎤⚠️ TURN_DETECTION_DEVICE=cuda but CUDA is unavailable; falling back to CPU.")
        return torch.device("cpu")

    return torch.device("cuda" if torch.cuda.is_available() else "cpu")

def ends_with_string(text: str, s: str) -> bool:
    """
    Checks if a string ends with a specific substring, allowing for one trailing character.

    Useful for checking punctuation even if there's a trailing space.

    Args:
        text: The input string to check.
        s: The substring to look for at the end.

    Returns:
        True if the text ends with s, or if text[:-1] ends with s. False otherwise.
    """
    if text.endswith(s):
        return True
    # Check if it ends if we ignore the very last character (e.g., trailing space)
    if len(text) > 1 and text[:-1].endswith(s):
        return True
    return False

def preprocess_text(text: str) -> str:
    """
    Cleans and normalizes the beginning of a text string.

    Applies the following steps:
    1. Removes leading whitespace.
    2. Removes leading ellipses ("...") if present.
    3. Removes leading whitespace again (after potential ellipses removal).
    4. Uppercases the first letter of the remaining text.

    Args:
        text: The input text string.

    Returns:
        The preprocessed text string.
    """
    text = text.lstrip() # Remove leading whitespaces
    if text.startswith("..."): #  Remove starting ellipses if present
        text = text[3:]
    text = text.lstrip() # Remove any leading whitespaces again after ellipses removal
    if text:
        text = text[0].upper() + text[1:] # Uppercase the first letter

    return text

def strip_ending_punctuation(text: str) -> str:
    """
    Removes trailing punctuation marks defined in `sentence_end_marks`.

    Removes trailing whitespace first, then iteratively removes any characters
    from `sentence_end_marks` found at the end of the string.

    Args:
        text: The input text string.

    Returns:
        The text string with specified trailing punctuation removed.
    """
    text = text.rstrip()
    for char in sentence_end_marks:
        # Repeatedly strip each punctuation mark in case of multiples (e.g., "!!")
        while text.endswith(char):
             text = text.rstrip(char)
    return text # Return the stripped text

def find_matching_texts(texts_without_punctuation: collections.deque) -> list[tuple[str, str]]:
    """
    Finds recent consecutive entries with the same stripped text.

    Iterates backwards through the deque of (original_text, stripped_text) tuples.
    It collects all entries matching the stripped text of the *last* entry,
    stopping as soon as a non-matching stripped text is encountered.

    Args:
        texts_without_punctuation: A deque of tuples, where each tuple is
                                   (original_text, stripped_text).

    Returns:
        A list of matching (original_text, stripped_text) tuples in their
        original order (oldest matching first). Returns an empty list if the
        input deque is empty.
    """
    if not texts_without_punctuation:
        return []

    # Get the stripped text from the last entry
    last_stripped_text = texts_without_punctuation[-1][1]

    matching_entries = []

    # Iterate through the deque backwards
    for entry in reversed(texts_without_punctuation):
        original_text, stripped_text = entry

        # If we find a non-match, stop collecting
        if stripped_text != last_stripped_text:
            break

        # Add the matching entry (will be reversed later)
        matching_entries.append(entry)

    # Reverse the results to maintain original insertion order
    matching_entries.reverse()

    return matching_entries

def interpolate_detection(prob: float) -> float:
    """
    Linearly interpolates a value based on probability using predefined anchor points.

    Maps an input probability `prob` (clamped between 0.0 and 1.0) to an output
    value based on the `anchor_points` list. It finds the segment within
    `anchor_points` where `prob` falls and performs linear interpolation.

    Args:
        prob: The input probability, expected between 0.0 and 1.0.

    Returns:
        The interpolated value. Returns 4.0 as a fallback if interpolation fails
        (though this shouldn't happen if anchor points cover the [0,1] range).
    """
    # Clamp probability between 0.0 and 1.0 just in case
    p = max(0.0, min(prob, 1.0))

    # Check if probability exactly matches an anchor point
    for ap_p, ap_val in anchor_points:
        if abs(ap_p - p) < 1e-9: # Use tolerance for float comparison
            return ap_val

    # Find the segment [p1, p2] where p resides
    for i in range(len(anchor_points) - 1):
        p1, v1 = anchor_points[i]
        p2, v2 = anchor_points[i+1]
        # Ensure anchor points are sorted by probability for this logic to work
        if p1 <= p <= p2:
            # Avoid division by zero if anchor points have the same probability
            if abs(p2 - p1) < 1e-9:
                return v1 # or v2, they should be close if p1=p2
            # Linear interpolation formula
            ratio = (p - p1) / (p2 - p1)
            return v1 + ratio * (v2 - v1)

    # Fallback: Should not be reached if anchor_points cover [0,1] properly.
    logger.warning(f"🎤⚠️ Probability {p} fell outside defined anchor points {anchor_points}. Returning fallback value.")
    return 4.0

class TurnDetection:
    """
    Manages turn detection logic based on text input and sentence completion model.

    This class receives text segments, uses a transformer model to predict sentence
    completion probability, considers punctuation, and calculates a suggested waiting
    time (pause duration) before the next speaker might start. It uses a background
    thread for processing and provides a callback for new waiting time suggestions.
    It also maintains a history of recent texts and uses caching for model predictions.
    """

    def __init__(
        self,
        on_new_waiting_time: callable,
        local: bool = False,
        pipeline_latency: float = 0.5,
        pipeline_latency_overhead: float = 0.1,
        profile: str = "english",
        model_path: str | None = None,
    ) -> None:
        if profile not in {"english", "darija"}:
            raise ValueError("Unknown turn detection profile")
        self.profile = profile
        self.on_new_waiting_time = on_new_waiting_time
        self.pipeline_latency = pipeline_latency
        self.pipeline_latency_overhead = pipeline_latency_overhead
        self.current_waiting_time = -1
        self.last_decision = None
        self.text_time_deque = collections.deque(maxlen=100)
        self.texts_without_punctuation = collections.deque(maxlen=20)
        self._completion_probability_cache = collections.OrderedDict()
        self._completion_probability_cache_max_size = 256
        self._state_lock = threading.RLock()
        self._inference_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._epoch = 0
        self.text_queue = queue.Queue()
        self.max_length = 128
        self.temperature = 1.0
        model_dir = model_path or (get_env("TURN_DETECTION_MODEL") if profile == "darija" else None)
        if profile == "darija" and not model_dir:
            raise ValueError("Darija turn detection requires the prepared model path")
        model_dir = model_dir or (model_dir_local if local else model_dir_cloud)
        self._load_model(model_dir)
        self.update_settings(speed_factor=0.0)
        # All model and timing state must exist before any queued work can run.
        self.text_worker = threading.Thread(target=self._text_worker, daemon=True,
                                            name="TurnDetectionWorker")
        self.text_worker.start()

    def _load_model(self, model_dir):
        import torch
        import transformers
        self._torch = torch
        self.device = torch.device("cpu") if self.profile == "darija" else _resolve_turn_detection_device()
        logger.info("Turn detector: profile=%s device=%s path=%s", self.profile, self.device, model_dir)
        if self.profile == "darija":
            from pathlib import Path
            if not Path(model_dir).is_dir():
                raise ValueError("Darija turn model must be a prepared local directory")
            self.tokenizer = transformers.AutoTokenizer.from_pretrained(
                model_dir, local_files_only=True, trust_remote_code=False,
            )
            self.classification_model = transformers.AutoModelForSequenceClassification.from_pretrained(
                model_dir, local_files_only=True, trust_remote_code=False,
            )
            darija_turn.validate_model_config(self.classification_model.config)
            self.tokenizer.truncation_side = "left"
            self.temperature = darija_turn.TEMPERATURE
        else:
            self.tokenizer = transformers.DistilBertTokenizerFast.from_pretrained(model_dir)
            self.classification_model = transformers.DistilBertForSequenceClassification.from_pretrained(model_dir)
        self.classification_model.to(self.device)
        self.classification_model.eval()
        self._predict_probability(normalize_turn_text("سلام، بغيت نعرف فين وصل الطلب.")
                                  if self.profile == "darija" else "This is a warmup sentence.")
        logger.info("Turn detector warmed up")

    def _predict_probability(self, sentence):
        inputs = self.tokenizer(sentence, return_tensors="pt", truncation=True,
                                padding="max_length", max_length=self.max_length)
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with self._torch.no_grad():
            logits = self.classification_model(**inputs).logits.detach().cpu().tolist()
        if len(logits) != 1:
            raise ValueError("Turn classifier must return one pair of logits")
        return darija_turn.calibrated_probability(logits[0], self.temperature)

    def update_settings(self, speed_factor: float) -> None:
        """
        Adjusts dynamic pause parameters based on a speed factor.

        Linearly interpolates between 'fast' (speed_factor=0.0) and 'very_slow'
        (speed_factor=1.0) settings for various pause durations used in calculation.
        Clamps speed_factor between 0.0 and 1.0.

        Args:
            speed_factor: A float between 0.0 (fastest) and 1.0 (slowest) controlling
                          the interpolation between predefined settings.
        """
        speed_factor = max(0.0, min(speed_factor, 1.0)) # Clamp factor

        # Base 'fast' settings (speed_factor = 0.0)
        fast = {
            'detection_speed': 0.5,
            'ellipsis_pause': 2.3,
            'punctuation_pause': 0.39,
            'exclamation_pause': 0.35,
            'question_pause': 0.33,
            'unknown_sentence_detection_pause': 1.25
        }

        # Target 'very slow' settings (speed_factor = 1.0)
        very_slow = {
            'detection_speed': 1.7,
            'ellipsis_pause': 3.0,
            'punctuation_pause': 0.9,
            'exclamation_pause': 0.8,
            'question_pause': 0.8,
            'unknown_sentence_detection_pause': 1.9
        }

        # Linear interpolation for each parameter
        self.detection_speed = fast['detection_speed'] + speed_factor * (very_slow['detection_speed'] - fast['detection_speed'])
        self.ellipsis_pause = fast['ellipsis_pause'] + speed_factor * (very_slow['ellipsis_pause'] - fast['ellipsis_pause'])
        self.punctuation_pause = fast['punctuation_pause'] + speed_factor * (very_slow['punctuation_pause'] - fast['punctuation_pause'])
        self.exclamation_pause = fast['exclamation_pause'] + speed_factor * (very_slow['exclamation_pause'] - fast['exclamation_pause'])
        self.question_pause = fast['question_pause'] + speed_factor * (very_slow['question_pause'] - fast['question_pause'])
        self.unknown_sentence_detection_pause = fast['unknown_sentence_detection_pause'] + speed_factor * (very_slow['unknown_sentence_detection_pause'] - fast['unknown_sentence_detection_pause'])
        logger.info(f"🎤⚙️ Updated turn detection settings with speed_factor={speed_factor:.2f}")


    def suggest_time(self, time_val: float, text: str = None, epoch: int | None = None) -> None:
        # Publish under the same lock used by reset. After reset returns, no
        # callback or diagnostic from the old utterance can reach the recorder.
        with self._state_lock:
            if self._stop_event.is_set() or (epoch is not None and epoch != self._epoch):
                return
            if time_val == self.current_waiting_time:
                return
            self.current_waiting_time = time_val
            if self.on_new_waiting_time:
                self.on_new_waiting_time(time_val, text)

    def get_completion_probability(self, sentence: str, epoch: int | None = None) -> float:
        if self.profile == "darija":
            sentence = normalize_turn_text(sentence)
        with self._state_lock:
            epoch = self._epoch if epoch is None else epoch
            if sentence in self._completion_probability_cache:
                self._completion_probability_cache.move_to_end(sentence)
                return self._completion_probability_cache[sentence]
        with self._inference_lock:
            probability = 0.0 if self.profile == "darija" and not sentence else self._predict_probability(sentence)
        with self._state_lock:
            if epoch == self._epoch and not self._stop_event.is_set():
                self._completion_probability_cache[sentence] = probability
                self._completion_probability_cache.move_to_end(sentence)
                if len(self._completion_probability_cache) > self._completion_probability_cache_max_size:
                    self._completion_probability_cache.popitem(last=False)
        return probability

    def get_completion_decision(self, text: str, epoch: int | None = None):
        if self.profile != "darija":
            raise ValueError("Calibrated Darija decisions require the Darija profile")
        return darija_turn.decision(text, self.get_completion_probability(text, epoch))

    def get_suggested_whisper_pause(self, text: str) -> float:
        """
        Determines a base pause duration based on the text's ending punctuation.

        Checks for specific ending patterns ('...', '.', '!', '?') and returns
        a corresponding pause duration defined by the instance's settings
        (e.g., `self.ellipsis_pause`). Returns `self.unknown_sentence_detection_pause`
        if no specific punctuation is matched.

        Args:
            text: The input text string.

        Returns:
            The suggested pause duration in seconds based on ending punctuation.
        """
        if ends_with_string(text, "...") or ends_with_string(text, "…"):
            return self.ellipsis_pause
        elif ends_with_string(text, "."):
            return self.punctuation_pause
        elif ends_with_string(text, "!"):
            return self.exclamation_pause
        elif ends_with_string(text, "?") or ends_with_string(text, "؟"):
            return self.question_pause
        else:
            # No specific ending detected, use the general pause for unknown endings
            return self.unknown_sentence_detection_pause

    def _text_worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                epoch, text = self.text_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._process_text(text, epoch)
            except Exception:
                # A failed classifier must not kill the worker or reuse an old
                # high completion score. Retain the existing unknown/floor pause.
                logger.exception("Turn classification failed for profile=%s", self.profile)
                with self._state_lock:
                    if epoch == self._epoch:
                        self.last_decision = None
                        fallback = max(self.unknown_sentence_detection_pause * self.detection_speed,
                                       self.pipeline_latency + self.pipeline_latency_overhead)
                        self.suggest_time(fallback, text, epoch)
            finally:
                self.text_queue.task_done()

    def _process_text(self, text, epoch):
        with self._state_lock:
            if epoch != self._epoch or self._stop_event.is_set():
                return
            processed_text = text.strip() if self.profile == "darija" else preprocess_text(text)
            self.text_time_deque.append((time.time(), processed_text))
            self.texts_without_punctuation.append((processed_text, strip_ending_punctuation(processed_text)))
            matches = find_matching_texts(self.texts_without_punctuation)
            pauses = [self.get_suggested_whisper_pause(match[0]) for match in matches]
            whisper_suggested_pause = sum(pauses) / len(pauses) if pauses else self.get_suggested_whisper_pause(processed_text)
            contains_ellipses = any(ends_with_string(value, "...") or ends_with_string(value, "…")
                                   for value, _ in matches or [(processed_text, "")])
        if self.profile == "darija":
            completion = self.get_completion_decision(processed_text, epoch)
            prob_complete = completion.decision_score
        else:
            # Preserve the legacy English classifier's request normalization.
            import string
            transtext = processed_text.translate(str.maketrans('', '', string.punctuation))
            cleaned_for_model = re.sub(r'[^a-zA-Z\s]+$', '', transtext).rstrip()
            prob_complete = self.get_completion_probability(cleaned_for_model, epoch)
            completion = None
        sentence_finished_model_pause = interpolate_detection(prob_complete)
        weight_towards_whisper = 0.65
        weighted_pause = (weight_towards_whisper * whisper_suggested_pause +
                          (1 - weight_towards_whisper) * sentence_finished_model_pause)
        final_pause = weighted_pause * self.detection_speed
        if contains_ellipses:
            final_pause += 0.2
        final_pause = max(final_pause, self.pipeline_latency + self.pipeline_latency_overhead)
        with self._state_lock:
            if epoch != self._epoch or self._stop_event.is_set():
                return
            self.last_decision = completion
            if completion is not None:
                logger.info("Darija turn: probability=%.4f score=%.4f override=%s threshold=%.10f complete=%s pause=%.3f",
                            completion.completion_probability, completion.decision_score,
                            completion.syntax_override, completion.threshold, completion.is_complete, final_pause)
            else:
                logger.info("English turn: probability=%.4f pause=%.3f", prob_complete, final_pause)
            self.suggest_time(final_pause, processed_text, epoch)

    def calculate_waiting_time(self, text: str) -> None:
        with self._state_lock:
            if not self._stop_event.is_set():
                self.text_queue.put((self._epoch, text))

    def reset(self) -> None:
        with self._state_lock:
            self._epoch += 1
            self.text_time_deque.clear()
            self.texts_without_punctuation.clear()
            self.current_waiting_time = -1
            self.last_decision = None
            self._completion_probability_cache.clear()
            while True:
                try:
                    self.text_queue.get_nowait()
                    self.text_queue.task_done()
                except queue.Empty:
                    break

    def shutdown(self) -> None:
        self._stop_event.set()
        self.reset()
        if threading.current_thread() is not self.text_worker:
            self.text_worker.join(timeout=2)
