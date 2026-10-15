"""Speech-to-text node; configuration helpers do not load recorder dependencies."""
__all__ = ["DEFAULT_RECORDER_CONFIG", "FasterWhisperSTTProvider"]


def __getattr__(name):
    if name in __all__:
        from core.nodes.stt import faster_whisper
        return getattr(faster_whisper, name)
    raise AttributeError(name)
