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
CONFIG_ROOT = CODE_ROOT / "config"


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


def _parse_scalar(value: str) -> Any:
    normalized = value.strip()
    if normalized == "":
        return None
    if normalized.lower() in {"true", "false"}:
        return normalized.lower() == "true"
    if normalized.lower() in {"none", "null"}:
        return None
    try:
        return int(normalized)
    except ValueError:
        pass
    try:
        return float(normalized)
    except ValueError:
        return normalized


def _load_yaml_file(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}

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
                parsed[key.strip()] = _parse_scalar(value)
        return expand_env_placeholders(parsed)


def _merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def _apply_env_overrides(config: dict[str, Any], agent_name: str) -> dict[str, Any]:
    merged = dict(config)
    agent_prefix = agent_name.upper().replace("-", "_")

    for key in list(merged.keys()):
        env_suffix = key.upper().replace("-", "_")
        for env_name in (f"VOICE_AGENT_{env_suffix}", f"{agent_prefix}_{env_suffix}"):
            if env_name in os.environ:
                merged[key] = _parse_scalar(os.environ[env_name])

    return merged


def load_agent_config(agent_name: str) -> dict[str, Any]:
    global_config = _load_yaml_file(CONFIG_ROOT / "global.yaml")
    agent_config = _load_yaml_file(CODE_ROOT / "agents" / agent_name / "config.yaml")
    merged = _merge_config(global_config, agent_config)
    return _apply_env_overrides(merged, agent_name)
