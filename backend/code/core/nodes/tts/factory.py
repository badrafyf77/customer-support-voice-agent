"""One lazy provider boundary for the existing engines and SILMA."""
from core.config import get_env, read_float_env


def create_tts_provider(engine="kokoro", orpheus_model=None, skip_prewarm=False):
    if engine == "silma":
        from core.nodes.tts.silma import SilmaTTSProvider
        from core.nodes.tts.silma_config import selected_voice
        voice_id, variant = selected_voice()
        return SilmaTTSProvider(
            base_url=get_env("SILMA_TTS_BASE_URL", "http://127.0.0.1:8002"),
            voice_id=voice_id,
            variant=variant,
            request_timeout=read_float_env("SILMA_REQUEST_TIMEOUT_SECONDS", 120),
            skip_prewarm=skip_prewarm,
        )
    if engine not in {"kokoro", "coqui", "orpheus"}:
        raise ValueError(f"Unsupported TTS engine: {engine}")
    from core.nodes.tts.realtime import RealtimeTTSProvider
    options = {"engine": engine, "skip_prewarm": skip_prewarm}
    if orpheus_model is not None:
        options["orpheus_model"] = orpheus_model
    return RealtimeTTSProvider(**options)
