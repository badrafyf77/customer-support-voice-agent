"""Build the LangChain chat model of an agent from its ``config.yaml``."""
from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI

from core.config import get_env


def build_chat_model(config: dict[str, Any], default_model: str) -> ChatOpenAI:
    """OpenAI by default; ``llm_provider: vllm`` uses a local OpenAI-compatible server.

    GPT-5 models only accept tools together with a reasoning effort through
    OpenAI's Responses API, so that is the default (``use_responses_api``).
    """
    provider = (config.get("llm_provider") or "openai").strip().lower()
    effort = config.get("reasoning_effort") or None
    kwargs: dict[str, Any] = {
        "model": config.get("llm_model") or default_model,
        "stream_usage": True,
        "timeout": 30,
        "max_retries": 2,
    }

    if provider == "vllm":
        kwargs["base_url"] = get_env("VLLM_BASE_URL", "http://127.0.0.1:8000/v1")
        kwargs["api_key"] = "vllm-key"
        kwargs["use_responses_api"] = False
        return ChatOpenAI(**kwargs)

    use_responses_api = bool(config.get("use_responses_api", True))
    kwargs["use_responses_api"] = use_responses_api
    if effort:
        if use_responses_api:
            kwargs["reasoning"] = {"effort": effort}
        else:
            kwargs["reasoning_effort"] = effort
    return ChatOpenAI(**kwargs)
