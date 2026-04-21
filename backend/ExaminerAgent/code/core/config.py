"""Shared configuration helpers for the voice-agent backend.

Only this module and ``services.llm`` should read environment variables
directly. Other layers import these helpers so runtime configuration stays
centralized and easy to audit.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - startup will fail loudly if YAML is needed.
    yaml = None

logger = logging.getLogger(__name__)

CODE_ROOT = Path(__file__).resolve().parents[1]


def load_env_file_if_available() -> None:
    """Load a local .env file when python-dotenv is installed."""
    try:
        import importlib.util

        dotenv_spec = importlib.util.find_spec("dotenv")
        if dotenv_spec:
            from dotenv import load_dotenv

            load_dotenv()
    except Exception:
        logger.debug("Skipping optional .env loading for server configuration.", exc_info=False)


def get_env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def read_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def read_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        return int(raw_value)
    except ValueError:
        logger.warning("Invalid %s env var. Using default: %s", name, default)
        return default


def read_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        return float(raw_value)
    except ValueError:
        logger.warning("Invalid %s env var. Using default: %s", name, default)
        return default


def expand_env_placeholders(value: Any) -> Any:
    """Resolve simple ``${VAR}`` values in loaded YAML configuration."""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return get_env(value[2:-1], "")
    if isinstance(value, dict):
        return {key: expand_env_placeholders(item) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_env_placeholders(item) for item in value]
    return value


def load_agent_config(agent_name: str) -> dict[str, Any]:
    config_path = CODE_ROOT / "agents" / agent_name / "config.yaml"
    with config_path.open("r", encoding="utf-8") as f:
        if yaml is not None:
            return expand_env_placeholders(yaml.safe_load(f) or {})

        parsed: dict[str, Any] = {}
        for raw_line in f:
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            key, raw_value = line.split(":", 1)
            value = raw_value.strip()
            if value == "":
                parsed[key.strip()] = None
            elif value.lower() in {"true", "false"}:
                parsed[key.strip()] = value.lower() == "true"
            else:
                parsed[key.strip()] = value
        return expand_env_placeholders(parsed)
