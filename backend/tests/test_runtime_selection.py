"""Exercise production startup/routing bodies without importing GPU libraries."""
import ast
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from core.config import load_runtime_config

CODE_ROOT = Path(__file__).resolve().parents[1] / "code"


def load_function(path, name, namespace):
    # Compile the actual function body; model imports remain outside this test.
    tree = ast.parse(path.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == name)
    if name == "ws_endpoint":
        function.decorator_list = []
    module = ast.Module(body=[function], type_ignores=[])
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[name]


class StartupRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_ignores_stale_exam_state_and_routes_selected_chat_config(self):
        app = SimpleNamespace(state=SimpleNamespace(AGENT_NAME="exam"))
        recorder = SimpleNamespace(DEFAULT_RECORDER_CONFIG={"model": "medium.en"})
        runtime_manager = Mock()
        runtime_manager.startup = AsyncMock()
        runtime_manager.shutdown = AsyncMock()
        factory = Mock(return_value=runtime_manager)
        namespace = {
            "asynccontextmanager": asynccontextmanager, "logger": logging.getLogger(__name__),
            "load_runtime_config": load_runtime_config, "get_env": lambda name, default=None: default,
            "Colors": SimpleNamespace(apply=lambda value: SimpleNamespace(blue=value)),
            "UpsampleOverlap": Mock(), "VoiceRuntimeManager": factory,
            "_wait_for_vllm_ready": AsyncMock(),
            "LLM_START_PROVIDER": "vllm", "LLM_START_MODEL": "baseline-model",
            "TTS_START_ENGINE": "kokoro", "LANGUAGE": "en", "TTS_ORPHEUS_MODEL": "unused",
            "NO_THINK": False, "VOICE_RUNTIME_ACQUIRE_TIMEOUT_SECONDS": 30,
            "VOICE_RUNTIME_MIN_WARM": 1, "VOICE_RUNTIME_MAX_CONCURRENT": 1,
            "VOICE_RUNTIME_IDLE_TTL_SECONDS": 300,
        }
        lifespan = load_function(CODE_ROOT / "core/session.py", "lifespan", namespace)
        stt_package = SimpleNamespace(faster_whisper=recorder)
        environment = {"VOICE_AGENT": "chat", "VOICE_PROFILE": "english",
                       "CHAT_LANGUAGE": "fr", "STT_MODEL": "/configured/asr"}
        with (
            patch.dict(os.environ, environment, clear=True),
            patch("core.config.load_env_file_if_available"),
            patch.dict(sys.modules, {"core.nodes.stt": stt_package}),
        ):
            async with lifespan(app):
                self.assertEqual(app.state.AGENT_NAME, "chat")
                self.assertEqual(factory.call_args.kwargs["language"], "fr")
                self.assertEqual(recorder.DEFAULT_RECORDER_CONFIG["model"], "/configured/asr")
                run_session = AsyncMock()
                brain = object()
                endpoint = load_function(CODE_ROOT / "server.py", "ws_endpoint", {
                    "WebSocket": object, "app": app, "run_session": run_session,
                    "build_chat_agent": lambda context: (brain, {}),
                })
                socket = object()
                await endpoint(socket)
                self.assertIs(run_session.call_args.args[1], brain)
                self.assertEqual(run_session.call_args.args[2],
                                 {**app.state.AGENT_CONFIG, "agent_name": "chat"})
        runtime_manager.startup.assert_awaited_once()
        runtime_manager.shutdown.assert_awaited_once()

    async def test_darija_exam_parameters_are_rejected_before_database_access(self):
        socket = SimpleNamespace(close=AsyncMock())
        database = SimpleNamespace(load_session_context=AsyncMock())
        run_session = AsyncMock()
        endpoint = load_function(CODE_ROOT / "server.py", "ws_endpoint", {
            "WebSocket": object, "app": SimpleNamespace(state=SimpleNamespace(VOICE_PROFILE="darija")),
            "database": database, "run_session": run_session,
        })
        await endpoint(socket, user_id="exam-user")
        socket.close.assert_awaited_once_with(code=1008, reason="Darija supports general chat only.")
        database.load_session_context.assert_not_awaited()
        run_session.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
