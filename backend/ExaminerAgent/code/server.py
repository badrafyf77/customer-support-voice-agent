# server.py
from queue import Queue, Empty
import logging
from logsetup import setup_logging
setup_logging(logging.INFO)
logger = logging.getLogger(__name__)

# Clean logging helper - only show important events
def log_event(emoji: str, message: str, level: str = "info"):
    """Log important events in a clean, readable format"""
    if level == "info":
        logger.info(f"{emoji} {message}")
    elif level == "warning":
        logger.warning(f"{emoji} {message}")
    elif level == "error":
        logger.error(f"{emoji} {message}")

if __name__ == "__main__":
    log_event("🎙️", "Voice Chat Server Starting...")

from upsample_overlap import UpsampleOverlap
from datetime import datetime, timezone
from colors import Colors
import uvicorn
import asyncio
import struct
import json
import time
import threading # Keep threading for SpeechPipelineManager internals and AbortWorker
import sys
import os # Added for environment variable access
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from typing import Any, Dict, Optional, Callable # Added for type hints in docstrings
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import HTMLResponse, JSONResponse, Response, FileResponse


def _load_env_file_if_available() -> None:
    """
    Loads a local .env file when python-dotenv is available.

    This keeps server-side environment handling consistent for local runs while
    remaining a no-op in deployments that inject environment variables directly.
    """
    try:
        import importlib.util

        dotenv_spec = importlib.util.find_spec("dotenv")
        if dotenv_spec:
            from dotenv import load_dotenv

            load_dotenv()
    except Exception:
        logger.debug("🖥️⚙️ Skipping optional .env loading for server configuration.", exc_info=False)


def _read_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        return int(raw_value)
    except ValueError:
        logger.warning("🖥️⚠️ Invalid %s env var. Using default: %s", name, default)
        return default


def _read_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        return float(raw_value)
    except ValueError:
        logger.warning("🖥️⚠️ Invalid %s env var. Using default: %s", name, default)
        return default


def _parse_datetime_utc(value: Any) -> Optional[datetime]:
    """
    Parse best-effort datetime values from DB strings and return UTC-aware datetimes.
    """
    if value is None:
        return None

    raw = str(value).strip().strip('"').strip("'")
    if not raw:
        return None

    # If the value is embedded in surrounding text, extract the first ISO-like token.
    token_match = re.search(
        r"\d{4}-\d{2}-\d{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:?[0-9]{2})?",
        raw,
    )
    candidate = token_match.group(0) if token_match else raw

    if candidate.endswith(("Z", "z")):
        candidate = candidate[:-1] + "+00:00"

    # Normalize offsets like +0000 to +00:00 for fromisoformat.
    if re.search(r"[+-][0-9]{4}$", candidate):
        candidate = f"{candidate[:-5]}{candidate[-5:-2]}:{candidate[-2:]}"

    # Trim excessive fractional precision to microseconds.
    frac_match = re.search(r"\.([0-9]+)", candidate)
    if frac_match and len(frac_match.group(1)) > 6:
        candidate = candidate.replace(frac_match.group(0), "." + frac_match.group(1)[:6], 1)

    parse_attempts = [candidate]
    if " " in candidate and "T" not in candidate:
        parse_attempts.append(candidate.replace(" ", "T", 1))
    if "T" in candidate:
        parse_attempts.append(candidate.replace("T", " ", 1))

    for attempt in parse_attempts:
        try:
            parsed = datetime.fromisoformat(attempt)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue

    return None


_load_env_file_if_available()

USE_SSL = False
# TTS_START_ENGINE = "orpheus"
TTS_START_ENGINE = "kokoro"
# TTS_START_ENGINE = "coqui"
TTS_ORPHEUS_MODEL = "Orpheus_3B-1BaseGGUF/mOrpheus_3B-1Base_Q4_K_M.gguf"
TTS_ORPHEUS_MODEL = "orpheus-3b-0.1-ft-Q8_0-GGUF/orpheus-3b-0.1-ft-q8_0.gguf"

# LLM configuration - only vLLM and OpenAI are supported.
LLM_START_PROVIDER = os.getenv("LLM_PROVIDER", "vllm").strip().lower()
if LLM_START_PROVIDER not in {"vllm", "openai"}:
    logger.warning(
        "🖥️⚠️ Unsupported LLM_PROVIDER '%s'. Falling back to 'vllm'. Supported: vllm, openai.",
        LLM_START_PROVIDER,
    )
    LLM_START_PROVIDER = "vllm"
LLM_START_MODEL = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-72B-Instruct-AWQ")

NO_THINK = False
DIRECT_STREAM = TTS_START_ENGINE=="orpheus"

# Global pipeline configuration used to build warmed runtimes at app startup.
PIPELINE_CONFIG = {}

if __name__ == "__main__":
    logger.info(f"🖥️⚙️ {Colors.apply('[PARAM]').blue} Starting engine: {Colors.apply(TTS_START_ENGINE).blue}")
    logger.info(f"🖥️⚙️ {Colors.apply('[PARAM]').blue} Direct streaming: {Colors.apply('ON' if DIRECT_STREAM else 'OFF').blue}")

# Define the maximum allowed size for the incoming audio queue
try:
    MAX_AUDIO_QUEUE_SIZE = int(os.getenv("MAX_AUDIO_QUEUE_SIZE", 50))
    if __name__ == "__main__":
        logger.info(f"🖥️⚙️ {Colors.apply('[PARAM]').blue} Audio queue size limit set to: {Colors.apply(str(MAX_AUDIO_QUEUE_SIZE)).blue}")
except ValueError:
    if __name__ == "__main__":
        logger.warning("🖥️⚠️ Invalid MAX_AUDIO_QUEUE_SIZE env var. Using default: 50")
    MAX_AUDIO_QUEUE_SIZE = 50

LEGACY_VOICE_RUNTIME_POOL_SIZE = _read_int_env("VOICE_RUNTIME_POOL_SIZE", 1)
VOICE_RUNTIME_MIN_WARM = max(0, _read_int_env("VOICE_RUNTIME_MIN_WARM", LEGACY_VOICE_RUNTIME_POOL_SIZE))
VOICE_RUNTIME_MAX_CONCURRENT = max(1, _read_int_env("VOICE_RUNTIME_MAX_CONCURRENT", LEGACY_VOICE_RUNTIME_POOL_SIZE))
VOICE_RUNTIME_IDLE_TTL_SECONDS = max(0.0, _read_float_env("VOICE_RUNTIME_IDLE_TTL_SECONDS", 300.0))
VOICE_RUNTIME_ACQUIRE_TIMEOUT_SECONDS = max(
    0.1,
    _read_float_env("VOICE_RUNTIME_ACQUIRE_TIMEOUT_SECONDS", 30.0),
)
VLLM_STARTUP_TIMEOUT_SECONDS = max(
    5.0,
    _read_float_env("VLLM_STARTUP_TIMEOUT_SECONDS", 180.0),
)
VLLM_HEALTHCHECK_INTERVAL_SECONDS = max(
    0.5,
    _read_float_env("VLLM_HEALTHCHECK_INTERVAL_SECONDS", 2.0),
)
DEFAULT_EVALUATOR_AGENT_BASE_URL = "http://162.243.59.37:8090"
EVALUATOR_AGENT_BASE_URL = os.getenv(
    "EVALUATOR_AGENT_BASE_URL",
    DEFAULT_EVALUATOR_AGENT_BASE_URL,
).strip().rstrip("/")
EVALUATOR_TRIGGER_TIMEOUT_SECONDS = max(
    1.0,
    _read_float_env("EVALUATOR_TRIGGER_TIMEOUT_SECONDS", 5.0),
)

if VOICE_RUNTIME_MAX_CONCURRENT < VOICE_RUNTIME_MIN_WARM:
    logger.warning(
        "🖥️⚠️ VOICE_RUNTIME_MAX_CONCURRENT (%s) is lower than VOICE_RUNTIME_MIN_WARM (%s). Clamping max to min.",
        VOICE_RUNTIME_MAX_CONCURRENT,
        VOICE_RUNTIME_MIN_WARM,
    )
    VOICE_RUNTIME_MAX_CONCURRENT = VOICE_RUNTIME_MIN_WARM


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

#from handlerequests import LanguageProcessor
#from audio_out import AudioOutProcessor
from database import get_database_client
from user_context import SystemPromptBuilder
from exam_graph import ExamSessionGraphController
from voice_runtime_pool import VoiceRuntimeManager, VoiceRuntimeCapacityError
from speech_pipeline_manager import _strip_control_leak

LANGUAGE = "en"
# TTS_FINAL_TIMEOUT = 0.5 # unsure if 1.0 is needed for stability
TTS_FINAL_TIMEOUT = 1.0 # unsure if 1.0 is needed for stability


def _candidate_vllm_probe_urls(base_url: str) -> list[str]:
    """
    Builds a small set of readiness probe URLs for a vLLM OpenAI-compatible base URL.
    """
    parsed = urlsplit(base_url)
    scheme = parsed.scheme or "http"
    netloc = parsed.netloc or parsed.path
    raw_path = parsed.path if parsed.netloc else ""
    base_path = raw_path.rstrip("/")

    if base_path.endswith("/v1"):
        root_path = base_path[:-3]
    else:
        root_path = base_path

    root = urlunsplit((scheme, netloc, root_path or "", "", "")).rstrip("/")
    api_root = urlunsplit((scheme, netloc, base_path or "/v1", "", "")).rstrip("/")

    return [
        f"{root}/health",
        f"{root}/ping",
        f"{api_root}/models",
    ]


def _probe_http_endpoint(url: str) -> bool:
    """
    Returns True when the given HTTP endpoint responds successfully.
    """
    try:
        with urlopen(url, timeout=5.0) as response:
            status = getattr(response, "status", None) or response.getcode()
            return 200 <= status < 300
    except (HTTPError, URLError, OSError, ValueError):
        return False


async def _wait_for_vllm_ready(base_url: str) -> None:
    """
    Waits until the configured vLLM server reports readiness.
    """
    probe_urls = _candidate_vllm_probe_urls(base_url)
    deadline = time.monotonic() + VLLM_STARTUP_TIMEOUT_SECONDS
    attempt = 0

    logger.info(
        "🖥️⏳ Waiting for vLLM readiness before warming runtimes (timeout=%ss, probes=%s).",
        VLLM_STARTUP_TIMEOUT_SECONDS,
        ", ".join(probe_urls),
    )

    while True:
        attempt += 1
        for probe_url in probe_urls:
            if await asyncio.to_thread(_probe_http_endpoint, probe_url):
                logger.info("🖥️✅ vLLM is ready at %s", probe_url)
                return

        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Timed out waiting for vLLM readiness after {VLLM_STARTUP_TIMEOUT_SECONDS:.1f}s "
                f"(base URL: {base_url})."
            )

        if attempt == 1 or attempt % 5 == 0:
            logger.info("🖥️⏳ vLLM is not ready yet; retrying in %.1fs...", VLLM_HEALTHCHECK_INTERVAL_SECONDS)

        await asyncio.sleep(VLLM_HEALTHCHECK_INTERVAL_SECONDS)


def _post_json(url: str, payload: Dict[str, Any], timeout_seconds: float) -> Dict[str, Any]:
    """Send a small JSON payload and return parsed JSON body when available."""
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read()
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}


async def trigger_attempt_evaluation(
    attempt_id: str,
    exam_id: Optional[str] = None,
    triggered_by_user_id: Optional[str] = None,
) -> None:
    """
    Request asynchronous evaluation for a submitted attempt.

    This call is best-effort and must never block oral session finalization.
    """
    if not attempt_id:
        return

    if not EVALUATOR_AGENT_BASE_URL:
        logger.warning("⚠️ Evaluator handoff skipped because EVALUATOR_AGENT_BASE_URL is empty")
        return

    url = f"{EVALUATOR_AGENT_BASE_URL}/evaluate-attempt"
    payload: Dict[str, Any] = {
        "attempt_id": attempt_id,
        "mode": "async",
    }
    if exam_id:
        payload["exam_id"] = exam_id
    if triggered_by_user_id:
        payload["triggered_by_user_id"] = triggered_by_user_id

    try:
        response_payload = await asyncio.to_thread(
            _post_json,
            url,
            payload,
            EVALUATOR_TRIGGER_TIMEOUT_SECONDS,
        )
        accepted = bool(response_payload.get("accepted"))
        status = str(response_payload.get("status") or "unknown")
        if accepted:
            log_event("🤖", f"Evaluator queued for attempt {attempt_id[-4:]} (status={status})")
        else:
            logger.warning(
                "⚠️ Evaluator trigger returned accepted=false for attempt %s: %s",
                attempt_id,
                response_payload,
            )
    except HTTPError as exc:
        body = ""
        with suppress(Exception):
            body = exc.read().decode("utf-8")
        logger.warning(
            "⚠️ Evaluator trigger HTTP error for attempt %s: status=%s body=%s",
            attempt_id,
            getattr(exc, "code", "unknown"),
            body or str(exc),
        )
    except URLError as exc:
        logger.warning("⚠️ Evaluator trigger network error for attempt %s: %s", attempt_id, exc)
    except TimeoutError:
        logger.warning("⚠️ Evaluator trigger timed out for attempt %s", attempt_id)
    except Exception as exc:
        logger.error("⚠️ Evaluator trigger failed for attempt %s: %s", attempt_id, exc)

# --------------------------------------------------------------------
# Custom no-cache StaticFiles
# --------------------------------------------------------------------
class NoCacheStaticFiles(StaticFiles):
    """
    Serves static files without allowing client-side caching.

    Overrides the default Starlette StaticFiles to add 'Cache-Control' headers
    that prevent browsers from caching static assets. Useful for development.
    """
    async def get_response(self, path: str, scope: Dict[str, Any]) -> Response:
        """
        Gets the response for a requested path, adding no-cache headers.

        Args:
            path: The path to the static file requested.
            scope: The ASGI scope dictionary for the request.

        Returns:
            A Starlette Response object with cache-control headers modified.
        """
        response: Response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        # These might not be strictly necessary with no-store, but belt and suspenders
        if "etag" in response.headers:
             response.headers.__delitem__("etag")
        if "last-modified" in response.headers:
             response.headers.__delitem__("last-modified")
        return response

# --------------------------------------------------------------------
# Lifespan management
# --------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the application's lifespan, initializing shared resources.

    Args:
        app: The FastAPI application instance.
    """
    logger.info("🖥️▶️ Server starting up")
    
    # Log LLM configuration
    logger.info(f"🖥️⚙️ {Colors.apply('[LLM]').blue} Provider: {Colors.apply(LLM_START_PROVIDER).blue}, Model: {Colors.apply(LLM_START_MODEL).blue}")
    
    # Store the configuration used to build speech runtimes.
    global PIPELINE_CONFIG
    PIPELINE_CONFIG = {
        "tts_engine": TTS_START_ENGINE,
        "llm_provider": LLM_START_PROVIDER,
        "llm_model": LLM_START_MODEL,
        "no_think": NO_THINK,
        "orpheus_model": TTS_ORPHEUS_MODEL,
    }
    
    # Store configuration and shared components
    app.state.PIPELINE_CONFIG = PIPELINE_CONFIG
    app.state.RUNTIME_ACQUIRE_TIMEOUT_SECONDS = VOICE_RUNTIME_ACQUIRE_TIMEOUT_SECONDS
    app.state.Upsampler = UpsampleOverlap()  # Stateless, can be shared

    if LLM_START_PROVIDER == "vllm":
        await _wait_for_vllm_ready(os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8000/v1"))

    app.state.RUNTIME_MANAGER = VoiceRuntimeManager(
        min_warm=VOICE_RUNTIME_MIN_WARM,
        max_concurrent=VOICE_RUNTIME_MAX_CONCURRENT,
        idle_ttl_seconds=VOICE_RUNTIME_IDLE_TTL_SECONDS,
        pipeline_config=PIPELINE_CONFIG,
        language=LANGUAGE,
        tts_engine=TTS_START_ENGINE,
    )
    await app.state.RUNTIME_MANAGER.startup()

    logger.info(
        "🖥️⚙️ Voice runtime manager ready (min_warm=%s, max_concurrent=%s, idle_ttl=%ss, acquire_timeout=%ss)",
        VOICE_RUNTIME_MIN_WARM,
        VOICE_RUNTIME_MAX_CONCURRENT,
        VOICE_RUNTIME_IDLE_TTL_SECONDS,
        VOICE_RUNTIME_ACQUIRE_TIMEOUT_SECONDS,
    )
    
    logger.info("🖥️✅ Server initialized - ready for connections")

    yield

    logger.info("🖥️⏹️ Server shutting down")
    await app.state.RUNTIME_MANAGER.shutdown()

# --------------------------------------------------------------------
# FastAPI app instance
# --------------------------------------------------------------------
app = FastAPI(lifespan=lifespan)
STATIC_DIR = Path(__file__).resolve().parent / "static"
HAS_STATIC_ASSETS = STATIC_DIR.is_dir()

# Enable CORS if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files with no cache when this backend is used in standalone mode.
# In the monorepo setup, the React frontend is a separate app and these assets
# are intentionally absent.
if HAS_STATIC_ASSETS:
    app.mount("/static", NoCacheStaticFiles(directory=str(STATIC_DIR)), name="static")
else:
    logger.warning(
        "Static frontend assets not found at %s; serving WebSocket/API only.",
        STATIC_DIR,
    )

@app.get("/favicon.ico")
async def favicon():
    """
    Serves the favicon.ico file.

    Returns:
        A FileResponse containing the favicon.
    """
    favicon_path = STATIC_DIR / "favicon.ico"
    if not favicon_path.is_file():
        return Response(status_code=404)
    return FileResponse(favicon_path)

@app.get("/app.js")
async def app_js():
    """
    Serves the app.js file.

    Returns:
        A FileResponse containing the app.js
    """
    app_js_path = STATIC_DIR / "app.js"
    if not app_js_path.is_file():
        return Response(status_code=404)
    return FileResponse(app_js_path)

@app.get("/app.css")
async def app_css():
    """
    Serves the app.css file.

    Returns:
        A FileResponse containing the app.css
    """
    app_css_path = STATIC_DIR / "app.css"
    if not app_css_path.is_file():
        return Response(status_code=404)
    return FileResponse(app_css_path)


@app.get("/voice-reference")
async def check_voice_reference(user_id: str):
    """Return whether a permanent voice reference exists for a user."""
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    db = get_database_client()
    payload = db.get_user_voice_reference(user_id)
    return JSONResponse({"exists": bool(payload)})


@app.post("/voice-reference")
async def upload_voice_reference(
    user_id: str = Form(...),
    audio: UploadFile = File(...),
):
    """
    Receive a short voice sample, extract a SpeechBrain ECAPA-TDNN embedding,
    and persist it permanently on the user's profile. This runs once per user;
    subsequent oral exam attempts load the stored embedding automatically.
    """
    from speaker_verification import (
        DEFAULT_MATCH_THRESHOLD,
        embedding_to_list,
        extract_embedding_from_wav_bytes,
    )

    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    blob = await audio.read()
    if not blob:
        raise HTTPException(status_code=400, detail="Empty audio upload")

    try:
        embedding = extract_embedding_from_wav_bytes(blob)
    except Exception as exc:
        logger.exception("🗣️🔐 Failed to extract voice reference embedding: %s", exc)
        raise HTTPException(status_code=500, detail=f"Embedding failure: {exc}") from exc

    if embedding is None:
        raise HTTPException(
            status_code=422,
            detail="Could not produce an embedding. Please record at least 2 seconds of clear speech.",
        )

    payload = {
        "embedding": embedding_to_list(embedding),
        "model": "speechbrain/spkrec-ecapa-voxceleb",
        "threshold": DEFAULT_MATCH_THRESHOLD,
        "enrolled_at": datetime.now(timezone.utc).isoformat(),
        "audio_bytes": len(blob),
    }

    db = get_database_client()
    saved = db.update_user_voice_reference(user_id, payload)

    return JSONResponse(
        {
            "ok": True,
            "saved": saved,
            "embedding_dim": len(payload["embedding"]),
        }
    )


@app.get("/")
async def get_index() -> HTMLResponse:
    """
    Serves the main index.html page.

    Reads the content of static/index.html and returns it as an HTML response.

    Returns:
        An HTMLResponse containing the content of index.html.
    """
    index_path = STATIC_DIR / "index.html"
    if not index_path.is_file():
        return HTMLResponse(
            content=(
                "<html><body><h1>examiner-agent backend is running.</h1>"
                "<p>This deployment exposes the WebSocket endpoint at <code>/ws</code> "
                "and does not bundle a frontend.</p></body></html>"
            )
        )

    with open(index_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

# --------------------------------------------------------------------
# Utility functions
# --------------------------------------------------------------------
def parse_json_message(text: str) -> dict:
    """
    Safely parses a JSON string into a dictionary.

    Logs a warning if the JSON is invalid and returns an empty dictionary.

    Args:
        text: The JSON string to parse.

    Returns:
        A dictionary representing the parsed JSON, or an empty dictionary on error.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("🖥️⚠️ Ignoring client message with invalid JSON")
        return {}

def format_timestamp_ns(timestamp_ns: int) -> str:
    """
    Formats a nanosecond timestamp into a human-readable HH:MM:SS.fff string.

    Args:
        timestamp_ns: The timestamp in nanoseconds since the epoch.

    Returns:
        A string formatted as hours:minutes:seconds.milliseconds.
    """
    # Split into whole seconds and the nanosecond remainder
    seconds = timestamp_ns // 1_000_000_000
    remainder_ns = timestamp_ns % 1_000_000_000

    # Convert seconds part into a datetime object (local time)
    dt = datetime.fromtimestamp(seconds)

    # Format the main time as HH:MM:SS
    time_str = dt.strftime("%H:%M:%S")

    # For instance, if you want milliseconds, divide the remainder by 1e6 and format as 3-digit
    milliseconds = remainder_ns // 1_000_000
    formatted_timestamp = f"{time_str}.{milliseconds:03d}"

    return formatted_timestamp


def _conversation_message(role: str, content: str, timestamp: datetime | None = None) -> dict[str, str]:
    return {
        "role": role,
        "content": content,
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
    }


def _normalize_conversation_history(history: list | None) -> list[dict[str, str]]:
    normalized_history: list[dict[str, str]] = []

    for item in list(history or []):
        if not isinstance(item, dict):
            continue

        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant", "system"} or not content:
            continue

        timestamp = _parse_datetime_utc(item.get("timestamp"))
        normalized_history.append(_conversation_message(role, content, timestamp))

    return normalized_history


async def trigger_orchestrated_exam_turn(
    conn_state,
    callbacks: 'TranscriptionCallbacks',
    message_queue: asyncio.Queue,
    reason: str,
) -> bool:
    """
    Ask LangGraph for the next Veridex turn and start generation for it.
    """
    exam_controller = getattr(conn_state, "exam_controller", None)
    if not exam_controller:
        return False

    if conn_state.session_finished or getattr(conn_state, "finish_in_progress", False):
        return False

    if conn_state.pipeline_manager.is_valid_gen():
        logger.info("🧭 Skipping orchestrated turn trigger because generation is already active (%s).", reason)
        return False

    planned_turn = None
    if exam_controller.has_pending_student_turn:
        try:
            planned_turn = exam_controller.plan_student_turn_response(conn_state.conversation_history)
        except Exception as exc:
            logger.exception("🧭 Failed to build the student-turn exam response: %s", exc)
            return False

    if not planned_turn:
        planned_turn = exam_controller.plan_next_turn(conn_state.conversation_history)
    if not planned_turn and reason == "session_ready":
        planned_turn = exam_controller.plan_resume_turn(conn_state.conversation_history)

    if not planned_turn:
        logger.info("🧭 No orchestrated exam turn to trigger (%s).", reason)
        return False

    logger.info(
        "🧭 Triggering orchestrated exam turn (%s): kind=%s question=%s",
        reason,
        planned_turn.kind,
        planned_turn.question_number,
    )

    if planned_turn.should_auto_finish:
        logger.info("🧭 Controller decided the exam is complete. Finishing silently without another spoken turn.")
        await trigger_exam_finish(
            conn_state,
            callbacks,
            conn_state.user_id,
            conn_state.exam_id,
            conn_state.attempt_id,
            message_queue,
            reason="controller_decided_exam_complete",
        )
        return True

    callbacks.prepare_assistant_turn(keep_microphone_blocked=planned_turn.should_auto_finish)
    conn_state.pipeline_manager.history = conn_state.conversation_history
    conn_state.pipeline_manager.prepare_generation(
        planned_turn.control_prompt,
        expects_control_block=planned_turn.expects_control_block,
        history_override=planned_turn.history_override,
    )
    return True


async def trigger_exam_finish(
    conn_state,
    callbacks: 'TranscriptionCallbacks',
    user_id: str,
    exam_id: str,
    attempt_id: str,
    message_queue: asyncio.Queue,
    reason: str,
) -> None:
    """
    Starts the shared finish flow once, whether it was requested manually or automatically.
    """
    if conn_state.session_finished:
        logger.info("🏁 Finish already completed, ignoring duplicate request (%s).", reason)
        return

    if getattr(conn_state, "finish_in_progress", False):
        logger.info("🏁 Finish already in progress, ignoring duplicate request (%s).", reason)
        return

    conn_state.finish_in_progress = True
    conn_state.lock_microphone_until_finish = True
    conn_state.audio_processor.interrupted = True
    callbacks.interruption_time = time.time()

    try:
        await handle_finish_exam_attempt(
            conn_state,
            user_id,
            exam_id,
            attempt_id,
            message_queue,
        )
    finally:
        if not conn_state.session_finished:
            conn_state.finish_in_progress = False
            conn_state.lock_microphone_until_finish = False

# --------------------------------------------------------------------
# WebSocket data processing
# --------------------------------------------------------------------

async def process_incoming_data(
    ws: WebSocket,
    conn_state,
    incoming_chunks: asyncio.Queue,
    callbacks: 'TranscriptionCallbacks',
    message_queue: asyncio.Queue,
    user_id: str = None,
    exam_id: str = None,
    attempt_id: str = None,
) -> None:
    """
    Receives messages via WebSocket, processes audio and text messages.

    Handles binary audio chunks, extracting metadata (timestamp, flags) and
    putting the audio PCM data with metadata into the `incoming_chunks` queue.
    Applies back-pressure if the queue is full.
    Parses text messages (assumed JSON) and triggers actions based on message type
    (e.g., updates client TTS state via `callbacks`, clears history, sets speed).

    Args:
        ws: The WebSocket connection instance.
        conn_state: Connection state containing pipeline manager and audio processor.
        incoming_chunks: An asyncio queue to put processed audio metadata dictionaries into.
        callbacks: The TranscriptionCallbacks instance for this connection to manage state.
        message_queue: Queue for sending messages to the client.
        user_id: Optional user UUID from WebSocket connection.
        exam_id: Optional exam UUID from WebSocket connection.
        attempt_id: Optional exam attempt UUID from WebSocket connection.
    """
    try:
        while True:
            msg = await ws.receive()
            if "bytes" in msg and msg["bytes"]:
                if getattr(conn_state, "finish_in_progress", False):
                    continue

                raw = msg["bytes"]

                # Ensure we have at least an 8‑byte header: 4 bytes timestamp_ms + 4 bytes flags
                if len(raw) < 8:
                    logger.warning("🖥️⚠️ Received packet too short for 8‑byte header.")
                    continue

                # Unpack big‑endian uint32 timestamp (ms) and uint32 flags
                timestamp_ms, flags = struct.unpack("!II", raw[:8])
                client_sent_ns = timestamp_ms * 1_000_000

                # Build metadata using fixed fields
                metadata = {
                    "client_sent_ms":           timestamp_ms,
                    "client_sent":              client_sent_ns,
                    "client_sent_formatted":    format_timestamp_ns(client_sent_ns),
                    "isTTSPlaying":             bool(flags & 1),
                }

                # Record server receive time
                server_ns = time.time_ns()
                metadata["server_received"] = server_ns
                metadata["server_received_formatted"] = format_timestamp_ns(server_ns)

                # The rest of the payload is raw PCM bytes
                metadata["pcm"] = raw[8:]

                # Check queue size before putting data
                current_qsize = incoming_chunks.qsize()
                if current_qsize < MAX_AUDIO_QUEUE_SIZE:
                    # Now put only the metadata dict (containing PCM audio) into the processing queue.
                    await incoming_chunks.put(metadata)
                else:
                    # Queue is full, drop the chunk and log a warning
                    logger.warning(
                        f"🖥️⚠️ Audio queue full ({current_qsize}/{MAX_AUDIO_QUEUE_SIZE}); dropping chunk. Possible lag."
                    )

            elif "text" in msg and msg["text"]:
                # Text-based message: parse JSON
                data = parse_json_message(msg["text"])
                msg_type = data.get("type")
                logger.info(Colors.apply(f"🖥️📥 ←←Client: {data}").orange)


                if msg_type == "tts_start":
                    logger.info("🖥️ℹ️ Received tts_start from client.")
                    # Update connection-specific state via callbacks
                    callbacks.tts_client_playing = True
                elif msg_type == "tts_stop":
                    logger.info("🖥️ℹ️ Received tts_stop from client.")
                    # Update connection-specific state via callbacks
                    callbacks.tts_client_playing = False
                # Add to the handleJSONMessage function in server.py
                elif msg_type == "clear_history":
                    logger.info("🖥️ℹ️ Received clear_history from client.")
                    conn_state.pipeline_manager.reset()
                elif msg_type == "set_speed":
                    speed_value = data.get("speed", 0)
                    speed_factor = speed_value / 100.0  # Convert 0-100 to 0.0-1.0
                    turn_detection = conn_state.audio_processor.transcriber.turn_detection
                    if turn_detection:
                        turn_detection.update_settings(speed_factor)
                        logger.info(f"🖥️⚙️ Updated turn detection settings to factor: {speed_factor:.2f}")
                elif msg_type == "finish_exam":
                    logger.info("🖥️🏁 Received finish_exam from client (oral exam).")
                    
                    # STEP 1: IMMEDIATELY send stop signals to frontend to clear TTS buffer
                    logger.info("🖥️🛑 Sending TTS stop signals to client (finish oral exam)")
                    message_queue.put_nowait({
                        "type": "tts_interruption",
                        "content": ""
                    })
                    message_queue.put_nowait({
                        "type": "stop_tts",
                        "content": ""
                    })
                    
                    # STEP 2: Stop server-side TTS streaming and generation
                    callbacks.tts_to_client = False
                    callbacks.user_interrupted = True
                    
                    # STEP 3: Abort any ongoing generation (LLM + TTS)
                    logger.info("🖥️🛑 Aborting all ongoing generation (finish oral exam)")
                    conn_state.audio_processor.abort_generation()
                    if conn_state.pipeline_manager.running_generation:
                        conn_state.pipeline_manager.abort_generation(reason="Oral exam finished by user")
                    
                    # STEP 4: Wait a moment for everything to stop cleanly
                    await asyncio.sleep(0.2)
                    
                    # STEP 5: Finalize the oral exam attempt (no scoring in examiner-agent)
                    logger.info("🖥️🧾 Finalizing oral exam attempt...")
                    asyncio.create_task(
                        trigger_exam_finish(
                            conn_state,
                            callbacks,
                            user_id,
                            exam_id,
                            attempt_id,
                            message_queue,
                            reason="manual_finish_requested_by_student",
                        )
                    )


    except asyncio.CancelledError:
        pass # Task cancellation is expected on disconnect
    except WebSocketDisconnect as e:
        logger.warning(f"🖥️⚠️ {Colors.apply('WARNING').red} disconnect in process_incoming_data: {repr(e)}")
    except RuntimeError as e:  # Often raised on closed transports
        logger.error(f"🖥️💥 {Colors.apply('RUNTIME_ERROR').red} in process_incoming_data: {repr(e)}")
    except Exception as e:
        logger.exception(f"🖥️💥 {Colors.apply('EXCEPTION').red} in process_incoming_data: {repr(e)}")

async def send_text_messages(ws: WebSocket, message_queue: asyncio.Queue) -> None:
    """
    Continuously sends text messages from a queue to the client via WebSocket.

    Waits for messages on the `message_queue`, formats them as JSON, and sends
    them to the connected WebSocket client. Logs non-TTS messages.

    Args:
        ws: The WebSocket connection instance.
        message_queue: An asyncio queue yielding dictionaries to be sent as JSON.
    """
    try:
        while True:
            await asyncio.sleep(0.001) # Yield control
            data = await message_queue.get()
            msg_type = data.get("type")
            if msg_type != "tts_chunk":
                logger.info(Colors.apply(f"🖥️📤 →→Client: {data}").orange)
            else:
                logger.debug("🖥️📤 sent tts_chunk")
            await ws.send_json(data)
    except asyncio.CancelledError:
        pass # Task cancellation is expected on disconnect
    except WebSocketDisconnect as e:
        logger.warning(f"🖥️⚠️ {Colors.apply('WARNING').red} disconnect in send_text_messages: {repr(e)}")
    except RuntimeError as e:  # Often raised on closed transports
        logger.error(f"🖥️💥 {Colors.apply('RUNTIME_ERROR').red} in send_text_messages: {repr(e)}")
    except Exception as e:
        logger.exception(f"🖥️💥 {Colors.apply('EXCEPTION').red} in send_text_messages: {repr(e)}")

async def _reset_interrupt_flag_async(audio_processor, callbacks: 'TranscriptionCallbacks'):
    """
    Resets the microphone interruption flag after a delay (async version).

    Waits for 1 second, then checks if the AudioInputProcessor is still marked
    as interrupted. If so, resets the flag on both the processor and the
    connection-specific callbacks instance.

    Args:
        audio_processor: The connection-specific AudioInputProcessor instance.
        callbacks: The TranscriptionCallbacks instance for the connection.
    """
    await asyncio.sleep(1)
    if getattr(callbacks.conn_state, "lock_microphone_until_finish", False):
        return
    # Check the AudioInputProcessor's own interrupted state
    if audio_processor.interrupted:
        logger.info(f"{Colors.apply('🖥️🎙️ ▶️ Microphone continued (async reset)').cyan}")
        audio_processor.interrupted = False
        # Reset connection-specific interruption time via callbacks
        callbacks.interruption_time = 0
        logger.info(Colors.apply("🖥️🎙️ interruption flag reset after TTS chunk (async)").cyan)

async def send_tts_chunks(conn_state, message_queue: asyncio.Queue, callbacks: 'TranscriptionCallbacks') -> None:
    """
    Continuously sends TTS audio chunks from the SpeechPipelineManager to the client.

    Monitors the state of the current speech generation (if any) and the client
    connection (via `callbacks`). Retrieves audio chunks from the active generation's
    queue, upsamples/encodes them, and puts them onto the outgoing `message_queue`
    for the client. Handles the end-of-generation logic and state resets.

    Args:
        app: The FastAPI application instance (to access global components).
        message_queue: An asyncio queue to put outgoing TTS chunk messages onto.
        callbacks: The TranscriptionCallbacks instance managing this connection's state.
    """
    try:
        logger.info("🖥️🔊 Starting TTS chunk sender")
        last_quick_answer_chunk = 0
        last_chunk_sent = 0
        prev_status = None

        while True:
            # Use connection-specific interruption_time via callbacks
            if (
                conn_state.audio_processor.interrupted
                and not getattr(conn_state, "lock_microphone_until_finish", False)
                and callbacks.interruption_time
                and time.time() - callbacks.interruption_time > 2.0
            ):
                conn_state.audio_processor.interrupted = False
                callbacks.interruption_time = 0 # Reset via callbacks
                logger.info(Colors.apply("🖥️🎙️ interruption flag reset after 2 seconds").cyan)

            is_tts_finished = conn_state.pipeline_manager.is_valid_gen() and conn_state.pipeline_manager.running_generation.audio_quick_finished

            def log_status():
                nonlocal prev_status
                last_quick_answer_chunk_decayed = (
                    last_quick_answer_chunk
                    and time.time() - last_quick_answer_chunk > TTS_FINAL_TIMEOUT
                    and time.time() - last_chunk_sent > TTS_FINAL_TIMEOUT
                )

                curr_status = (
                    # Access connection-specific state via callbacks
                    int(callbacks.tts_to_client),
                    int(callbacks.tts_client_playing),
                    int(callbacks.tts_chunk_sent),
                    1, # Placeholder?
                    int(callbacks.is_hot), # from callbacks
                    int(callbacks.synthesis_started), # from callbacks
                    int(conn_state.pipeline_manager.running_generation is not None), # Connection-specific manager state
                    int(conn_state.pipeline_manager.is_valid_gen()), # Connection-specific manager state
                    int(is_tts_finished), # Calculated local variable
                    int(conn_state.audio_processor.interrupted) # Connection-specific processor state
                )

                if curr_status != prev_status:
                    status = Colors.apply("🖥️🚦 State ").red
                    logger.info(
                        f"{status} ToClient {curr_status[0]}, "
                        f"ttsClientON {curr_status[1]}, " # Renamed slightly for clarity
                        f"ChunkSent {curr_status[2]}, "
                        f"hot {curr_status[4]}, synth {curr_status[5]}"
                        f" gen {curr_status[6]}"
                        f" valid {curr_status[7]}"
                        f" tts_q_fin {curr_status[8]}"
                        f" mic_inter {curr_status[9]}"
                    )
                    prev_status = curr_status

            # CRITICAL: Check for user interruption FIRST
            if callbacks.user_interrupted:
                log_status()
                # Clear the audio queue
                if conn_state.pipeline_manager.running_generation:
                    try:
                        while not conn_state.pipeline_manager.running_generation.audio_chunks.empty():
                            conn_state.pipeline_manager.running_generation.audio_chunks.get_nowait()
                    except:
                        pass
                await asyncio.sleep(0.001)
                continue
            
            # Use connection-specific state via callbacks
            if not callbacks.tts_to_client:
                log_status()
                await asyncio.sleep(0.001)  # Only sleep when waiting
                continue

            if not conn_state.pipeline_manager.running_generation:
                log_status()
                await asyncio.sleep(0.001)  # Only sleep when waiting
                continue

            if conn_state.pipeline_manager.running_generation.abortion_started:
                log_status()
                await asyncio.sleep(0.001)  # Only sleep when waiting
                continue

            if not conn_state.pipeline_manager.running_generation.audio_quick_finished:
                conn_state.pipeline_manager.running_generation.tts_quick_allowed_event.set()

            if not conn_state.pipeline_manager.running_generation.quick_answer_first_chunk_ready:
                log_status()
                await asyncio.sleep(0.001)  # Only sleep when waiting
                continue

            chunk = None
            try:
                chunk = conn_state.pipeline_manager.running_generation.audio_chunks.get_nowait()
                if chunk:
                    last_quick_answer_chunk = time.time()
                    # TTS chunk received - no need to log every chunk
            except Empty:
                final_expected = conn_state.pipeline_manager.running_generation.quick_answer_provided
                audio_final_finished = conn_state.pipeline_manager.running_generation.audio_final_finished
                llm_finished = conn_state.pipeline_manager.running_generation.llm_finished

                # Only send final answer when BOTH audio AND LLM are finished
                if (not final_expected or audio_final_finished) and llm_finished:
                    # Wait for LLM to be completely done (not just finished flag, but actually stopped)
                    if conn_state.pipeline_manager.running_generation:
                        # Wait for the LLM finished event to ensure all processing is complete
                        llm_finished_event = conn_state.pipeline_manager.running_generation.llm_finished_event
                        if llm_finished_event:
                            # Wait up to 1 second for the event (should already be set if llm_finished is True)
                            await asyncio.to_thread(llm_finished_event.wait, 1.0)
                    
                    # Additional wait to ensure ALL on_partial_assistant_text callbacks have been processed
                    # The callbacks might be queued in the event loop
                    await asyncio.sleep(0.5)
                    
                    # Force update assistant_answer from pipeline manager to ensure we have the complete text
                    if conn_state.pipeline_manager.running_generation:
                        complete_answer = conn_state.pipeline_manager.running_generation.quick_answer + conn_state.pipeline_manager.running_generation.final_answer
                        # Update the callback's assistant_answer with the complete text
                        if len(complete_answer) > len(callbacks.assistant_answer):
                            callbacks.assistant_answer = complete_answer
                            logger.info(f"🖥️✅ Updated assistant_answer to complete text from pipeline: '{complete_answer[:100]}...'")
                        else:
                            logger.info(f"🖥️✅ Callback assistant_answer already has complete text: '{callbacks.assistant_answer[:100]}...'")
                    
                    delivered_turn = callbacks.send_final_assistant_answer() # Callbacks method
                    conn_state.pipeline_manager.running_generation = None

                    callbacks.tts_chunk_sent = False # Reset via callbacks
                    callbacks.reset_state() # Reset connection state via callbacks

                    if delivered_turn and delivered_turn.should_auto_finish:
                        asyncio.create_task(
                            trigger_exam_finish(
                                conn_state,
                                callbacks,
                                conn_state.user_id,
                                conn_state.exam_id,
                                conn_state.attempt_id,
                                message_queue,
                                reason="question_limit_reached",
                            )
                        )
                    elif delivered_turn:
                        logger.info(
                            "🧭 Scheduling spoken recovery turn after silent controller transition: kind=%s question=%s",
                            delivered_turn.kind,
                            delivered_turn.question_number,
                        )
                        callbacks.prepare_assistant_turn(keep_microphone_blocked=delivered_turn.should_auto_finish)
                        conn_state.pipeline_manager.history = conn_state.conversation_history
                        conn_state.pipeline_manager.prepare_generation(
                            delivered_turn.control_prompt,
                            expects_control_block=delivered_turn.expects_control_block,
                            history_override=delivered_turn.history_override,
                        )

                log_status()
                await asyncio.sleep(0.001)  # Only sleep when waiting
                continue

            # Check if user interrupted before sending this chunk
            if callbacks.user_interrupted:
                logger.info(f"🖥️� User itnterrupted - stopping TTS chunk sending")
                # Clear any remaining chunks in the queue
                try:
                    while not conn_state.pipeline_manager.running_generation.audio_chunks.empty():
                        conn_state.pipeline_manager.running_generation.audio_chunks.get_nowait()
                except:
                    pass
                continue  # Skip sending this chunk
            
            # Process chunk immediately without sleeping
            base64_chunk = conn_state.upsampler.get_base64_chunk(chunk)
            logger.debug(f"🖥️🔊 sending tts_chunk b64_len={len(base64_chunk)}")
            message_queue.put_nowait({
                "type": "tts_chunk",
                "content": base64_chunk
            })
            last_chunk_sent = time.time()

            # Use connection-specific state via callbacks
            if not callbacks.tts_chunk_sent:
                # Use the async helper function instead of a thread
                asyncio.create_task(_reset_interrupt_flag_async(conn_state.audio_processor, callbacks))

            callbacks.tts_chunk_sent = True # Set via callbacks

    except asyncio.CancelledError:
        pass # Task cancellation is expected on disconnect
    except WebSocketDisconnect as e:
        logger.warning(f"🖥️⚠️ {Colors.apply('WARNING').red} disconnect in send_tts_chunks: {repr(e)}")
    except RuntimeError as e:
        logger.error(f"🖥️💥 {Colors.apply('RUNTIME_ERROR').red} in send_tts_chunks: {repr(e)}")
    except Exception as e:
        logger.exception(f"🖥️💥 {Colors.apply('EXCEPTION').red} in send_tts_chunks: {repr(e)}")


# --------------------------------------------------------------------
# Callback class to handle transcription events
# --------------------------------------------------------------------
class TranscriptionCallbacks:
    """
    Manages state and callbacks for a single WebSocket connection's transcription lifecycle.

    This class holds connection-specific state flags (like TTS status, user interruption)
    and implements callback methods triggered by the `AudioInputProcessor` and
    `SpeechPipelineManager`. It sends messages back to the client via the provided
    `message_queue` and manages interaction logic like interruptions and final answer delivery.
    It also includes a threaded worker to handle abort checks based on partial transcription.
    """
    def __init__(self, conn_state, message_queue: asyncio.Queue, user_id: str):
        """
        Initializes the TranscriptionCallbacks instance for a WebSocket connection.

        Args:
            conn_state: The connection-specific state object containing pipeline_manager and audio_processor.
            message_queue: An asyncio queue for sending messages back to the client.
            user_id: Short identifier for this user (for logging).
        """
        self.conn_state = conn_state
        self.message_queue = message_queue
        self.user_id = user_id
        self.loop = asyncio.get_running_loop()
        self.final_transcription = ""
        self.last_user_speech_time = 0  # Track when user last spoke
        self.user_speech_received = False  # Track if user spoke
        self.abort_text = ""
        self.last_abort_text = ""

        # Initialize connection-specific state flags here
        self.tts_to_client: bool = False
        self.user_interrupted: bool = False
        self.tts_chunk_sent: bool = False
        self.tts_client_playing: bool = False
        self.interruption_time: float = 0.0

        # These were already effectively instance variables or reset logic existed
        self.silence_active: bool = True
        self.is_hot: bool = False
        self.user_finished_turn: bool = False
        self.synthesis_started: bool = False
        self.assistant_answer: str = ""
        self.final_assistant_answer: str = ""
        self.is_processing_potential: bool = False
        self.is_processing_final: bool = False
        self.last_inferred_transcription: str = ""
        self.final_assistant_answer_sent: bool = False
        self.partial_transcription: str = "" # Added for clarity

        # NEW: Sentence-by-sentence tracking for separate bubbles
        self.sent_sentences: list = []  # Track sentences already sent to client
        self.sentence_counter: int = 0  # Counter for unique sentence IDs
        self.last_processed_length: int = 0  # Track how much text we've already processed
        self._last_stream_time: float = 0.0
        self._last_stream_length: int = 0
        self._last_logged_length: int = 0

        self.reset_state() # Call reset to ensure consistency

        self.abort_request_event = threading.Event()
        self.shutdown_event = threading.Event()
        self.abort_worker_thread = threading.Thread(target=self._abort_worker, name="AbortWorker", daemon=True)
        self.abort_worker_thread.start()


    def reset_state(self):
        """Resets connection-specific state flags and variables to their initial values."""
        # Reset all connection-specific state flags
        self.tts_to_client = False
        self.user_interrupted = False
        self.tts_chunk_sent = False
        # Don't reset tts_client_playing here, it reflects client state reports
        self.interruption_time = 0.0

        # Reset other state variables
        self.silence_active = True
        self.is_hot = False
        self.user_finished_turn = False
        self.synthesis_started = False
        self.assistant_answer = ""
        self.final_assistant_answer = ""
        self.is_processing_potential = False
        self.is_processing_final = False
        self.last_inferred_transcription = ""
        self.final_assistant_answer_sent = False
        self.partial_transcription = ""

        # Reset sentence tracking
        self.sent_sentences.clear()
        self.sentence_counter = 0
        self.last_processed_length = 0
        self._last_stream_time = 0.0
        self._last_stream_length = 0
        self._last_logged_length = 0

        # Keep the abort call related to the audio processor/pipeline manager
        self.conn_state.audio_processor.abort_generation()

    def prepare_assistant_turn(self, keep_microphone_blocked: bool = False):
        """
        Prepares the connection state for an assistant-led turn.
        """
        self.final_assistant_answer_sent = False
        self.user_interrupted = False
        self.tts_chunk_sent = False
        self.tts_to_client = True
        self.conn_state.lock_microphone_until_finish = keep_microphone_blocked
        self._last_stream_time = 0.0
        self._last_stream_length = 0
        self._last_logged_length = 0

        if not self.conn_state.audio_processor.interrupted:
            logger.info(f"{Colors.apply('🖥️🎙️ ⏸️ Microphone interrupted (assistant turn)').cyan}")
            self.conn_state.audio_processor.interrupted = True

        self.interruption_time = time.time()


    def send_progressive_text(self, text: str) -> None:
        """
        Sends progressive updates of the assistant's response text as it grows.
        Uses throttling to avoid sending too many updates (minimum interval or length change).
        The frontend will receive the full accumulated text and update the message bubble.
        
        Args:
            text: The current accumulated text from LLM
        """
        # Throttle updates: only send if significant change or time passed
        current_time = time.time()
        text_length = len(text)
        
        if text_length < self._last_stream_length:
            # New turns can start with shorter text than the previous turn.
            self._last_stream_time = 0.0
            self._last_stream_length = 0

        # Conditions for sending an update:
        # 1. At least 30 characters added since last send
        # 2. Or at least 0.3 seconds passed (for slow generation)
        time_since_last = current_time - self._last_stream_time
        chars_added = text_length - self._last_stream_length
        
        should_send = (
            chars_added >= 30 or  # Significant text added
            (time_since_last >= 0.3 and chars_added > 0)  # Time passed and some new text
        )
        
        if should_send and text.strip():
            payload = {
                "type": "assistant_partial",
                "content": text.strip(),
            }
            self.loop.call_soon_threadsafe(self.message_queue.put_nowait, payload)
            logger.debug(f"🖥️💬 Streamed {text_length} chars: {text[:60]}...")
            
            # Update throttle tracking
            self._last_stream_time = current_time
            self._last_stream_length = text_length

    def _abort_worker(self):
        """Background thread worker to check for abort conditions based on partial text."""
        while not self.shutdown_event.is_set():
            was_set = self.abort_request_event.wait(timeout=0.1) # Check every 100ms
            if was_set:
                self.abort_request_event.clear()
                if self.shutdown_event.is_set():
                    break
                # Only trigger abort check if the text actually changed
                if self.last_abort_text != self.abort_text:
                    self.last_abort_text = self.abort_text
                    logger.debug(f"🖥️🧠 Abort check triggered by partial: '{self.abort_text}'")
                    # Use connection-specific pipeline manager
                    self.conn_state.pipeline_manager.check_abort(self.abort_text, False, "on_partial")

    def shutdown(self) -> None:
        """Stops the per-connection abort worker thread."""
        self.shutdown_event.set()
        self.abort_request_event.set()
        if self.abort_worker_thread.is_alive():
            self.abort_worker_thread.join(timeout=1.0)

    def on_partial(self, txt: str):
        """
        Callback invoked when a partial transcription result is available.

        Updates internal state, sends the partial result to the client,
        and signals the abort worker thread to check for potential interruptions.

        Args:
            txt: The partial transcription text.
        """
        self.final_assistant_answer_sent = False # New user speech invalidates previous final answer sending state
        self.final_transcription = "" # Clear final transcription as this is partial
        self.partial_transcription = txt
        self.message_queue.put_nowait({"type": "partial_user_request", "content": txt})
        self.abort_text = txt # Update text used for abort check
        self.abort_request_event.set() # Signal the abort worker

    def safe_abort_running_syntheses(self, reason: str):
        """Placeholder for safely aborting syntheses (currently does nothing)."""
        # TODO: Implement actual abort logic if needed, potentially interacting with SpeechPipelineManager
        pass

    def on_tts_allowed_to_synthesize(self):
        """Callback invoked when the system determines TTS synthesis can proceed."""
        # Access connection-specific manager state
        if self.conn_state.pipeline_manager.running_generation and not self.conn_state.pipeline_manager.running_generation.abortion_started:
            self.conn_state.pipeline_manager.running_generation.tts_quick_allowed_event.set()

    def on_potential_sentence(self, txt: str):
        """
        Callback invoked when a potentially complete sentence is detected by the STT.

        Triggers the preparation of a speech generation based on this potential sentence.

        Args:
            txt: The potential sentence text.
        """
        logger.debug(f"🖥️🧠 Potential sentence: '{txt}'")
        if getattr(self.conn_state, "exam_controller", None):
            return
        # Access connection-specific manager state
        self.conn_state.pipeline_manager.prepare_generation(txt)

    def on_potential_final(self, txt: str):
        """
        Callback invoked when a potential *final* transcription is detected (hot state).

        Logs the potential final transcription.

        Args:
            txt: The potential final transcription text.
        """
        logger.info(f"{Colors.apply('🖥️🧠 HOT: ').magenta}{txt}")

    def on_potential_abort(self):
        """Callback invoked if the STT detects a potential need to abort based on user speech."""
        # Placeholder: Currently logs nothing, could trigger abort logic.
        pass

    def on_before_final(self, audio: bytes, txt: str):
        """
        Callback invoked just before the final STT result for a user turn is confirmed.

        Sets flags indicating user finished, allows TTS if pending, interrupts microphone input,
        releases TTS stream to client, sends final user request and any pending partial
        assistant answer to the client, and adds user request to history.

        Args:
            audio: The raw audio bytes corresponding to the final transcription. (Currently unused)
            txt: The transcription text (might be slightly refined in on_final).
        """
        # Get the user request content early to check if it's valid
        user_request_content = self.final_transcription if self.final_transcription else self.partial_transcription
        
        # CRITICAL: Check if user actually said something meaningful
        if not user_request_content or not user_request_content.strip():
            logger.info(f"{Colors.apply('🖥️⚠️ Ignoring empty user turn - no speech detected').yellow}")
            return  # Don't process empty turns
        
        # Additional check: Ensure minimum length (avoid single character noise)
        if len(user_request_content.strip()) < 2:
            logger.info(f"{Colors.apply('🖥️⚠️ Ignoring too short user turn: ').yellow}'{user_request_content}'")
            return
        
        logger.info(Colors.apply('🖥️🏁 =================== USER TURN END ===================').light_gray)
        self.user_finished_turn = True
        self.user_interrupted = False # Reset connection-specific flag (user finished, not interrupted)
        # Access connection-specific manager state
        if self.conn_state.pipeline_manager.is_valid_gen():
            logger.info(f"{Colors.apply('🖥️🔊 TTS ALLOWED (before final)').blue}")
            self.conn_state.pipeline_manager.running_generation.tts_quick_allowed_event.set()

        # first block further incoming audio (Audio processor's state)
        if not self.conn_state.audio_processor.interrupted:
            logger.info(f"{Colors.apply('🖥️🎙️ ⏸️ Microphone interrupted (end of turn)').cyan}")
            self.conn_state.audio_processor.interrupted = True
            self.interruption_time = time.time() # Set connection-specific flag

        logger.info(f"{Colors.apply('🖥️🔊 TTS STREAM RELEASED').blue}")
        self.tts_to_client = True # Set connection-specific flag

        # Send final user request
        self.message_queue.put_nowait({
            "type": "final_user_request",
            "content": user_request_content
        })

        # Access connection-specific manager state
        if self.conn_state.pipeline_manager.is_valid_gen():
            # Send partial assistant answer (if available) to the client
            # Use connection-specific user_interrupted flag
            if self.conn_state.pipeline_manager.running_generation.quick_answer and not self.user_interrupted:
                self.assistant_answer = self.conn_state.pipeline_manager.running_generation.quick_answer
                self.message_queue.put_nowait({
                    "type": "partial_assistant_answer",
                    "content": self.assistant_answer
                })

        logger.info(f"🖥️🧠 Adding user request to history: '{user_request_content}'")
        # Use connection-specific conversation history
        self.conn_state.conversation_history.append(_conversation_message("user", user_request_content))
        # Also update the shared pipeline manager's history for this request
        self.conn_state.pipeline_manager.history = self.conn_state.conversation_history

        # Voice verification: passively sample answer audio. The manager decides
        # whether to actually extract an embedding (always for the first answer,
        # then randomly for subsequent ones) so the student cannot predict which
        # turns will be checked. Runs in a background thread.
        verification_manager = getattr(self.conn_state, "voice_verification", None)
        if verification_manager is not None:
            try:
                transcriber = self.conn_state.audio_processor.transcriber
                answer_audio = transcriber.get_last_audio_copy() if transcriber else None
                if answer_audio is not None and getattr(answer_audio, "size", 0) > 0:
                    verification_manager.submit_answer_audio(
                        answer_audio,
                        transcript=user_request_content,
                    )
                else:
                    logger.debug("🗣️🔐 No buffered audio available for voice verification this turn")
            except Exception as exc:
                logger.warning("🗣️🔐 Failed to schedule voice verification for this turn: %s", exc)

        exam_controller = getattr(self.conn_state, "exam_controller", None)
        if exam_controller:
            exam_controller.queue_student_turn(user_request_content)
            asyncio.run_coroutine_threadsafe(
                trigger_orchestrated_exam_turn(
                    self.conn_state,
                    self,
                    self.message_queue,
                    reason="student_turn_completed",
                ),
                self.loop,
            )

    def on_final(self, txt: str):
        """
        Callback invoked when the final transcription result for a user turn is available.

        Logs the final transcription and stores it.

        Args:
            txt: The final transcription text.
        """
        # Only process if user actually said something
        if txt and txt.strip() and len(txt.strip()) >= 2:
            log_event("👤", f"[User {self.user_id}] Said: \"{txt}\"")
            self.last_user_speech_time = time.time()  # Track when user spoke
            self.user_speech_received = True  # Flag that user spoke
            
            if not self.final_transcription: # Store it if not already set by on_before_final logic
                self.final_transcription = txt
        else:
            logger.debug(f"🖥️⚠️ Ignoring empty final transcription from user {self.user_id}")

    def abort_generations(self, reason: str):
        """
        Triggers the abortion of any ongoing speech generation process.

        Logs the reason and calls the SpeechPipelineManager's abort method.

        Args:
            reason: A string describing why the abortion is triggered.
        """
        logger.info(f"{Colors.apply('🖥️🛑 Aborting generation:').blue} {reason}")
        # Access connection-specific manager state
        self.conn_state.pipeline_manager.abort_generation(reason=f"server.py abort_generations: {reason}")

    def on_silence_active(self, silence_active: bool):
        """
        Callback invoked when the silence detection state changes.

        Updates the internal silence_active flag.

        Args:
            silence_active: True if silence is currently detected, False otherwise.
        """
        # logger.debug(f"🖥️🎙️ Silence active: {silence_active}") # Optional: Can be noisy
        self.silence_active = silence_active

    def on_partial_assistant_text(self, txt: str):
        """
        Callback invoked when a partial text result from the assistant (LLM) is available.

        Updates the internal assistant answer state and streams the growing text to the client
        in progressive chunks, unless the user has interrupted.

        Args:
            txt: The partial assistant text (accumulates as LLM generates).
        """
        txt = _strip_control_leak(txt)
        # Always update assistant_answer with the latest text
        self.assistant_answer = txt
        
        # Only log when text changes significantly (not every token)
        if not hasattr(self, '_last_logged_length') or len(txt) - self._last_logged_length > 50:
            log_event("🤖", f"[User {self.user_id}] Assistant: {txt[:80]}{'...' if len(txt) > 80 else ''}")
            self._last_logged_length = len(txt)
            
            # Check if this is the first response after user speech
            if hasattr(self, 'user_speech_received') and self.user_speech_received and len(txt) > 20:
                response_time = time.time() - self.last_user_speech_time
                log_event("⏱️", f"[User {self.user_id}] Response started ({response_time:.1f}s after user spoke)")
                self.user_speech_received = False  # Reset flag
        
        # Use connection-specific user_interrupted flag
        if not self.user_interrupted:
            # Send progressive text updates (throttled to avoid flooding)
            self.send_progressive_text(txt)

    def on_recording_start(self):
        """
        Callback invoked when the audio input processor starts recording user speech.

        If client-side TTS is playing, it triggers an interruption: stops server-side
        TTS streaming, sends stop/interruption messages to the client, aborts ongoing
        generation, sends any final assistant answer generated so far, and resets relevant state.
        
        Note: Recording start means VAD detected speech, so we trust it and interrupt immediately.
        """
        if getattr(self.conn_state, "lock_microphone_until_finish", False):
            return

        log_event("🎤", f"[User {self.user_id}] Recording started - checking for interruption")
        
        # Only interrupt if TTS is playing
        # We trust the VAD - if recording started, there's likely speech
        if self.tts_client_playing:
            logger.info(f"{Colors.apply('🖥️❗ INTERRUPTING TTS due to user speech').blue}")
            
            # CRITICAL: Send interruption messages FIRST (before anything else)
            # This ensures client stops playing audio immediately
            logger.info("🖥️🛑 Sending tts_interruption to client (IMMEDIATE).")
            self.message_queue.put_nowait({
                "type": "tts_interruption",
                "content": ""
            })
            
            # Also send stop_tts for redundancy
            self.message_queue.put_nowait({
                "type": "stop_tts",
                "content": ""
            })
            
            # NOW stop server-side generation
            self.tts_to_client = False # Stop server sending TTS chunks
            self.user_interrupted = True # Mark connection as user interrupted
            
            # Abort the generation (stops LLM and TTS workers)
            logger.info(f"{Colors.apply('🖥️🛑 ABORTING GENERATION').red}")
            self.abort_generations("on_recording_start, user interrupts, TTS Playing")
            
            # Send final assistant answer *if* one was generated and not sent
            logger.info(Colors.apply("🖥️✅ Sending final assistant answer (forced on interruption)").pink)
            self.send_final_assistant_answer(forced=True)

            # Reset for interruption
            self.tts_chunk_sent = False # Reset chunk sending flag
            self.last_processed_length = 0  # Reset sentence tracking for new response

            # Reset state *after* performing actions based on the old state
            # Be careful what exactly needs reset vs persists (like tts_client_playing)
            # self.reset_state() # Might clear too much, like user_interrupted prematurely

    def send_final_assistant_answer(self, forced=False):
        """
        Sends the final (or best available) assistant answer to the client.

        Uses the complete text from self.assistant_answer which is updated by
        on_partial_assistant_text callback with the full LLM response.
        Falls back to pipeline manager's quick_answer + final_answer if needed.

        Args:
            forced: If True, attempts to send the last partial answer if no complete
                    final answer is available. Defaults to False.
        """
        final_answer = ""
        control_payload = None
        
        # FIRST: Try to get the most complete text from pipeline manager
        if self.conn_state.pipeline_manager.running_generation:
            control_payload = self.conn_state.pipeline_manager.running_generation.control_payload
            pipeline_answer = self.conn_state.pipeline_manager.running_generation.quick_answer + self.conn_state.pipeline_manager.running_generation.final_answer
            # Use whichever is longer (more complete)
            if len(pipeline_answer) > len(self.assistant_answer):
                final_answer = pipeline_answer
                logger.debug(f"🖥️✅ Using pipeline answer (longer): '{final_answer[:100]}...'")
            else:
                final_answer = self.assistant_answer
                logger.debug(f"🖥️✅ Using assistant_answer: '{final_answer[:100]}...'")
        # FALLBACK: Use self.assistant_answer if pipeline is not available
        elif self.assistant_answer:
            final_answer = self.assistant_answer
            logger.debug(f"🖥️✅ Using assistant_answer (no pipeline): '{final_answer[:100]}...'")

        if not final_answer: # Check if constructed answer is empty
            exam_controller = getattr(self.conn_state, "exam_controller", None)
            if exam_controller and control_payload and not forced:
                logger.info("🖥️🧭 Final assistant answer is empty, but an exam control payload is available. Applying silent transition.")
                return exam_controller.mark_assistant_turn_delivered("", control_payload, forced=forced)

            logger.warning(f"🖥️⚠️ Final assistant answer was empty, not sending.")
            return None # Nothing to send

        logger.info(f"🖥️✅ Attempting to send final answer (length: {len(final_answer)}): '{final_answer[:150]}...' (Sent previously: {self.final_assistant_answer_sent})")

        if not self.final_assistant_answer_sent and final_answer:
            import re
            # Strip any leaked tool-call style control blocks before sending
            final_answer = _strip_control_leak(final_answer)
            # Clean up the final answer text - single pass for efficiency
            # Replace all newlines and carriage returns with spaces
            cleaned_answer = final_answer.replace('\\n', ' ').replace('\\r', ' ')
            # Replace actual newlines and carriage returns
            cleaned_answer = re.sub(r'[\r\n]+', ' ', cleaned_answer)
            # Collapse multiple spaces into one and trim
            cleaned_answer = re.sub(r'\s+', ' ', cleaned_answer).strip()

            exam_controller = getattr(self.conn_state, "exam_controller", None)
            silenced_completed_exam_turn = False
            if (
                cleaned_answer
                and exam_controller
                and control_payload
                and exam_controller.should_silence_completed_exam_turn(control_payload, forced=forced)
            ):
                logger.info(
                    "🖥️🧭 Suppressing spoken assistant text because consuming this question completes the oral exam."
                )
                cleaned_answer = ""
                silenced_completed_exam_turn = True

            if cleaned_answer: # Ensure it's not empty after cleaning
                # Check if response took too long (potential issue)
                if hasattr(self, 'last_user_speech_time') and self.last_user_speech_time > 0:
                    response_time = time.time() - self.last_user_speech_time
                    if response_time > 10:
                        log_event("⚠️", f"[User {self.user_id}] Slow response ({response_time:.1f}s)", "warning")
                
                log_event("✅", f"[User {self.user_id}] Complete (len={len(cleaned_answer)}): \"{cleaned_answer[:100]}{'...' if len(cleaned_answer) > 100 else ''}\"")
                self.user_speech_received = False  # Reset flag after response
                self.message_queue.put_nowait({
                    "type": "final_assistant_answer",
                    "content": cleaned_answer
                })
                # Use connection-specific conversation history
                self.conn_state.conversation_history.append(_conversation_message("assistant", cleaned_answer))
                # Also update the shared pipeline manager's history
                self.conn_state.pipeline_manager.history = self.conn_state.conversation_history
                self.final_assistant_answer_sent = True
                self.final_assistant_answer = cleaned_answer # Store the sent answer

                if exam_controller:
                    return exam_controller.mark_assistant_turn_delivered(cleaned_answer, control_payload, forced=forced)
            else:
                if silenced_completed_exam_turn:
                    logger.info("🖥️🧭 Silent oral-exam finish applied; no spoken assistant text sent.")
                else:
                    logger.warning(f"🖥️⚠️ {Colors.YELLOW}Final assistant answer was empty after cleaning.{Colors.RESET}")
                self.final_assistant_answer_sent = False # Don't mark as sent
                self.final_assistant_answer = "" # Clear the stored answer
                if exam_controller and control_payload and not forced:
                    return exam_controller.mark_assistant_turn_delivered("", control_payload, forced=forced)
        elif forced and not final_answer: # Should not happen due to earlier check, but safety
             logger.warning(f"🖥️⚠️ {Colors.YELLOW}Forced send of final assistant answer, but it was empty.{Colors.RESET}")
             self.final_assistant_answer = "" # Clear the stored answer

        return None


async def handle_finish_exam_attempt(
    conn_state,
    user_id: str,
    exam_id: str,
    attempt_id: str,
    message_queue: asyncio.Queue,
):
    """
    Handle oral exam finish: persist transcript and mark the oral attempt as submitted.
    """
    try:
        log_event(
            "🏁",
            f"Finishing oral exam for user {user_id[-4:] if user_id else 'unknown'}, attempt {attempt_id[-4:] if attempt_id else 'unknown'}",
        )

        await message_queue.put({
            "type": "status",
            "status": "finishing",
            "message": "Finalizing your oral exam attempt..."
        })

        if not attempt_id:
            logger.warning("⚠️ No attempt_id provided, cannot finalize oral exam attempt")
            await message_queue.put({
                "type": "finish_complete",
                "success": False,
                "error": "No exam attempt ID"
            })
            return

        conversation_history = conn_state.conversation_history
        db_client = get_database_client()
        exam_attempt = db_client.get_exam_attempt(attempt_id)

        if not exam_attempt:
            await message_queue.put({
                "type": "finish_complete",
                "success": False,
                "error": "Exam attempt not found"
            })
            return

        resolved_exam_id = exam_id or exam_attempt.get("exam_id")

        now_utc = datetime.now(timezone.utc)
        started_at = _parse_datetime_utc(exam_attempt.get("started_at"))
        if started_at:
            duration_seconds = max(0, int((now_utc - started_at).total_seconds()))
        else:
            duration_seconds = max(0, int(exam_attempt.get("duration_seconds") or 0))
            logger.warning(
                "⚠️ Could not parse exam_attempt.started_at=%r. Falling back to stored duration_seconds=%s.",
                exam_attempt.get("started_at"),
                duration_seconds,
            )

        update_data = {
            "status": "submitted",
            "ended_at": now_utc.isoformat(),
            "submitted_at": now_utc.isoformat(),
            "duration_seconds": duration_seconds,
            "conversation_history": conversation_history,
        }

        verification_manager = getattr(conn_state, "voice_verification", None)
        if verification_manager is not None:
            try:
                update_data["voice_verification"] = verification_manager.build_summary()
            except Exception as exc:
                logger.warning("🗣️🔐 Could not include voice verification summary: %s", exc)

        if db_client.enabled and db_client.client:
            success = db_client.update_exam_attempt(attempt_id, update_data)
            if not success:
                raise RuntimeError("Failed to update exam attempt in database")

            conn_state.session_finished = True
            logger.info("🧭 Oral attempt submitted. Frontend client is responsible for triggering evaluator.")

            await message_queue.put({
                "type": "finish_complete",
                "success": True,
                "attempt_id": attempt_id,
                "exam_id": resolved_exam_id,
            })
            log_event("✅", f"Oral exam transcript saved and attempt submitted for {attempt_id[-4:]}")
        else:
            logger.warning("⚠️ Database not configured, cannot finalize oral exam attempt")
            await message_queue.put({
                "type": "finish_complete",
                "success": False,
                "error": "Database not configured"
            })
    except Exception as e:
        logger.error(f"❌ Error finishing oral exam attempt: {e}")
        import traceback
        traceback.print_exc()
        await message_queue.put({
            "type": "finish_complete",
            "success": False,
            "error": str(e)
        })

# --------------------------------------------------------------------
# Main WebSocket endpoint
# --------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    user_id: str = None,
    exam_id: str = None,
    attempt_id: str = None,
):
    """
    Handles the main WebSocket connection for real-time voice chat.

    Args:
        ws: The WebSocket connection instance provided by FastAPI.
        user_id: Optional user UUID from query parameters
        exam_id: Optional exam UUID from query parameters
        attempt_id: Optional exam attempt UUID from query parameters
    """
    await ws.accept()
    connection_id = id(ws)  # Unique ID for this connection
    # Create a short, readable display ID (last 4 digits of connection or user_id)
    display_id = user_id[-4:] if user_id else str(connection_id)[-4:]
    log_event(
        "🔌",
        f"[User {display_id}] Connected (mode=exam, user_id={user_id}, exam_id={exam_id}, attempt_id={attempt_id})"
    )

    message_queue = asyncio.Queue()
    audio_chunks = asyncio.Queue()
    runtime = None
    conn_state = None
    callbacks = None
    tasks = []
    
    # Send "initializing" status to client
    await ws.send_json({
        "type": "status",
        "status": "initializing",
        "message": "Setting up your oral exam session..."
    })
    
    # Load user context from database
    user_profile = None
    exam = None
    exam_attempt = None
    rubric_criteria = []
    personalized_prompt = None
    preloaded_history = []
    exam_controller = None
    
    if user_id or exam_id or attempt_id:
        log_event("📚", f"[User {display_id}] Loading user context from database...")
        db_client = get_database_client()

        if user_id:
            user_profile = db_client.get_app_profile(user_id)
            if user_profile:
                log_event("👤", f"[User {display_id}] Veridex profile loaded: {user_profile.get('full_name', 'Unknown')}")

        if attempt_id:
            exam_attempt = db_client.get_exam_attempt(attempt_id)
            if exam_attempt:
                exam_id = exam_attempt.get("exam_id") or exam_id
                preloaded_history = _normalize_conversation_history(exam_attempt.get("conversation_history"))
                log_event(
                    "🧾",
                    f"[User {display_id}] Attempt loaded: #{exam_attempt.get('attempt_number', '?')} with {len(preloaded_history)} stored messages"
                )

        if exam_id:
            exam = db_client.get_exam(exam_id)
            rubric_criteria = db_client.get_exam_rubric_criteria(exam_id)
            if exam:
                log_event("📘", f"[User {display_id}] Exam loaded: {exam.get('title', 'Unknown')} [{exam.get('subject', 'Unknown')}]")

        if user_profile or exam:
            personalized_prompt = SystemPromptBuilder.build_exam_prompt(user_profile, exam, exam_attempt, rubric_criteria)
            context_summary = SystemPromptBuilder.build_exam_context_summary(user_profile, exam, exam_attempt)
            log_event("📝", f"[User {display_id}] Personalized exam prompt: {context_summary}")

        if exam or exam_attempt:
            exam_controller = ExamSessionGraphController(exam, exam_attempt, preloaded_history)

    runtime_manager = app.state.RUNTIME_MANAGER
    if runtime_manager.at_capacity:
        await ws.send_json({
            "type": "status",
            "status": "waiting_for_runtime",
            "message": "Waiting for an available speech runtime..."
        })

    log_event("⚙️", f"[User {display_id}] Acquiring speech runtime...")
    try:
        runtime = await runtime_manager.acquire(timeout=app.state.RUNTIME_ACQUIRE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        log_event("⏳", f"[User {display_id}] Timed out waiting for a speech runtime", level="warning")
        await ws.send_json({
            "type": "status",
            "status": "busy",
            "message": "The oral exam backend is at capacity right now. Please retry in a moment."
        })
        await ws.close(code=1013)
        return
    except VoiceRuntimeCapacityError as exc:
        log_event("⛔", f"[User {display_id}] No additional runtime capacity is available: {exc}", level="warning")
        await ws.send_json({
            "type": "status",
            "status": "busy",
            "message": "The oral exam backend is at capacity right now. Please retry in a moment."
        })
        await ws.close(code=1013)
        return
    except Exception as exc:
        log_event("❌", f"[User {display_id}] Failed to acquire a speech runtime: {exc}", level="error")
        await ws.send_json({
            "type": "status",
            "status": "error",
            "message": "The oral exam backend could not prepare its speech runtime. Please retry in a moment."
        })
        await ws.close(code=1011)
        return

    log_event("✅", f"[User {display_id}] Speech runtime acquired")

    # Voice verification: load the student's permanent voice fingerprint from
    # their profile (enrolled once, reused for every attempt). Random sampling
    # during the exam compares answers against this reference.
    voice_verification_manager = None
    try:
        from voice_verification_manager import VoiceVerificationManager

        voice_verification_manager = VoiceVerificationManager(attempt_id)
        if user_id:
            voice_ref = get_database_client().get_user_voice_reference(user_id)
            if voice_ref:
                stored_threshold = voice_ref.get("threshold")
                if isinstance(stored_threshold, (int, float)):
                    voice_verification_manager.threshold = float(stored_threshold)
                voice_verification_manager.set_reference_from_embedding(
                    voice_ref["embedding"],
                    meta={
                        "enrolled_at": voice_ref.get("enrolled_at"),
                        "model": voice_ref.get("model"),
                    },
                )
                log_event("🗣️", f"[User {display_id}] Permanent voice reference loaded for verification")
            else:
                log_event(
                    "🗣️",
                    f"[User {display_id}] No voice enrollment found — verification disabled for this attempt",
                    level="warning",
                )
    except Exception as exc:
        logger.warning("🗣️🔐 Could not initialize voice verification manager: %s", exc)
        voice_verification_manager = None

    # Create connection state holder
    class ConnectionState:
        def __init__(self, leased_runtime):
            self.runtime = leased_runtime
            self.pipeline_manager = leased_runtime.pipeline_manager
            self.audio_processor = leased_runtime.audio_processor
            self.upsampler = app.state.Upsampler  # Shared (stateless)
            self.conversation_history = preloaded_history.copy() if preloaded_history else []  # Per-connection history
            self.session_finished = False  # Generic session finished flag
            self.finish_in_progress = False
            self.lock_microphone_until_finish = False
            self.exam_controller = exam_controller
            self.user_id = user_id
            self.exam_id = exam_id
            self.attempt_id = attempt_id
            self.voice_verification = voice_verification_manager

    conn_state = ConnectionState(runtime)

    # Set up callback manager with connection-specific state
    callbacks = TranscriptionCallbacks(conn_state, message_queue, display_id)
    try:
        runtime.prepare_session(
            conversation_history=conn_state.conversation_history,
            system_prompt=personalized_prompt,
            callbacks=callbacks,
        )
    except Exception as exc:
        log_event("❌", f"[User {display_id}] Failed to prepare the speech runtime: {exc}", level="error")
        callbacks.shutdown()
        await app.state.RUNTIME_MANAGER.release(runtime)
        runtime = None
        await ws.send_json({
            "type": "status",
            "status": "error",
            "message": "The oral exam backend could not prepare its speech runtime. Please retry in a moment."
        })
        await ws.close(code=1011)
        return

    try:
        log_event("🎧", f"[User {display_id}] Speech runtime ready")

        # Create tasks for handling different responsibilities
        tasks = [
            asyncio.create_task(
                process_incoming_data(
                    ws,
                    conn_state,
                    audio_chunks,
                    callbacks,
                    message_queue,
                    user_id,
                    exam_id,
                    attempt_id,
                )
            ),
            asyncio.create_task(conn_state.audio_processor.process_chunk_queue(audio_chunks)),
            asyncio.create_task(send_text_messages(ws, message_queue)),
            asyncio.create_task(send_tts_chunks(conn_state, message_queue, callbacks)),
        ]
        
        # NOW send "ready" status - everything is initialized and tasks are running
        await ws.send_json({
            "type": "status",
            "status": "ready",
            "message": "Oral exam session ready. Veridex is starting the exam."
        })
        log_event("🚀", f"[User {display_id}] Exam session ready")

        await trigger_orchestrated_exam_turn(
            conn_state,
            callbacks,
            message_queue,
            reason="session_ready",
        )

        # Wait for any task to complete (e.g., client disconnect)
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            if not task.done():
                task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    except Exception as e:
        logger.error(f"🖥️💥 {Colors.apply('ERROR').red} in WebSocket session {connection_id}: {repr(e)}")
    finally:
        log_event("👋", f"[User {display_id}] Disconnected")
        
        # Save conversation transcript if the oral exam has not already been finished and saved.
        if conn_state and attempt_id and len(conn_state.conversation_history) > 0 and not conn_state.session_finished:
            log_event("💾", f"[User {display_id}] Saving oral exam transcript ({len(conn_state.conversation_history)} messages)")
            db_client = get_database_client()
            success = db_client.update_attempt_transcript(attempt_id, conn_state.conversation_history)
            if success:
                log_event("✅", f"[User {display_id}] Oral exam transcript saved successfully")
            else:
                log_event("⚠️", f"[User {display_id}] Failed to save oral exam transcript", "warning")

            verification_manager = getattr(conn_state, "voice_verification", None)
            if verification_manager is not None:
                try:
                    db_client.update_voice_verification(attempt_id, verification_manager.build_summary())
                except Exception as exc:
                    logger.warning("🗣️🔐 Could not persist voice verification on disconnect: %s", exc)
        elif conn_state and conn_state.session_finished:
            log_event("ℹ️", f"[User {display_id}] Session already finished and saved, skipping transcript save")
        
        # Clear this connection's history
        if conn_state:
            conn_state.conversation_history = []
        
        # Cancel all tasks
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Clean up connection-specific resources
        try:
            if callbacks:
                callbacks.shutdown()

            if runtime:
                await app.state.RUNTIME_MANAGER.release(runtime)
                logger.info(f"🖥️✅ Returned speech runtime for connection {connection_id}")
        except Exception as e:
            logger.error(f"🖥️⚠️ Error during cleanup for connection {connection_id}: {e}")
        
        logger.info(f"🖥️❌ WebSocket session {connection_id} ended.")

# --------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------
if __name__ == "__main__":

    # Run the server without SSL
    if not USE_SSL:
        logger.info("🖥️▶️ Starting server without SSL.")
        uvicorn.run("server:app", host="0.0.0.0", port=8000, log_config=None)

    else:
        logger.info("🖥️🔒 Attempting to start server with SSL.")
        # Check if cert files exist
        cert_file = "127.0.0.1+1.pem"
        key_file = "127.0.0.1+1-key.pem"
        if not os.path.exists(cert_file) or not os.path.exists(key_file):
             logger.error(f"🖥️💥 SSL cert file ({cert_file}) or key file ({key_file}) not found.")
             logger.error("🖥️💥 Please generate them using mkcert:")
             logger.error("🖥️💥   choco install mkcert") # Assuming Windows based on earlier check, adjust if needed
             logger.error("🖥️💥   mkcert -install")
             logger.error("🖥️💥   mkcert 127.0.0.1 YOUR_LOCAL_IP") # Remind user to replace with actual IP if needed
             logger.error("🖥️💥 Exiting.")
             sys.exit(1)

        # Run the server with SSL
        logger.info(f"🖥️▶️ Starting server with SSL (cert: {cert_file}, key: {key_file}).")
        uvicorn.run(
            "server:app",
            host="0.0.0.0",
            port=8000,
            log_config=None,
            ssl_certfile=cert_file,
            ssl_keyfile=key_file,
        )
