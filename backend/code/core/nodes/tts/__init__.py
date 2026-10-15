"""Text-to-speech node."""
def __getattr__(name):
    if name == "RealtimeTTSProvider":
        from core.nodes.tts.realtime import RealtimeTTSProvider
        return RealtimeTTSProvider
    raise AttributeError(name)

__all__ = ["RealtimeTTSProvider"]
