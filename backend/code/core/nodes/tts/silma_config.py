"""One persisted voice selection for the backend and inference service."""
import json
from core.config import get_env
from core.model_artifacts import LOCK_PATH


def selected_voice() -> tuple[str, str]:
    selection = json.loads((LOCK_PATH.parent / "voices/selection.json").read_text(encoding="utf-8"))
    return (
        get_env("SILMA_VOICE_ID", selection["voice_id"]) or selection["voice_id"],
        get_env("SILMA_CHECKPOINT_VARIANT", selection["variant"]) or selection["variant"],
    )
