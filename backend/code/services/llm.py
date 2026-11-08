import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, Generator, List, Optional, Union

try:
    from openai import OpenAI, APIError, APITimeoutError, RateLimitError, APIConnectionError
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None

    class APIError(Exception):
        pass

    class APITimeoutError(APIError):
        pass

    class RateLimitError(APIError):
        pass

    class APIConnectionError(APIError):
        pass


log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
logger = logging.getLogger(__name__)
logger.setLevel(log_level)


try:
    import importlib.util

    dotenv_spec = importlib.util.find_spec("dotenv")
    if dotenv_spec:
        from dotenv import load_dotenv

        load_dotenv()
except Exception:
    logger.debug("🤖⚙️ Skipping optional .env load in services.llm.", exc_info=False)


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8000/v1")

# Reasoning models (GPT-5 family, o-series) reject sampling settings such as
# temperature and accept a reasoning_effort setting instead.
REASONING_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")
SAMPLING_KWARGS = ("temperature", "top_p", "frequency_penalty", "presence_penalty")


def is_reasoning_model(model: str) -> bool:
    name = (model or "").strip().lower().rsplit("/", 1)[-1]
    return name.startswith(REASONING_MODEL_PREFIXES)


def build_request_kwargs(
    backend: str,
    model: str,
    reasoning_effort: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Return the extra chat-completion settings that this model accepts."""
    request_kwargs = dict(kwargs)
    if is_reasoning_model(model):
        for key in SAMPLING_KWARGS:
            request_kwargs.pop(key, None)
        if "max_tokens" in request_kwargs:
            request_kwargs["max_completion_tokens"] = request_kwargs.pop("max_tokens")
        if reasoning_effort and "reasoning_effort" not in request_kwargs:
            request_kwargs["reasoning_effort"] = reasoning_effort
        return request_kwargs

    request_kwargs.pop("reasoning_effort", None)
    if "temperature" not in request_kwargs:
        request_kwargs["temperature"] = 0.8 if backend == "vllm" else 0.7
    if "frequency_penalty" not in request_kwargs:
        request_kwargs["frequency_penalty"] = 0.25
    if "presence_penalty" not in request_kwargs:
        request_kwargs["presence_penalty"] = 0.1
    return request_kwargs


@dataclass(frozen=True)
class TextDelta:
    """A piece of the answer text."""

    text: str


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON text, as the model wrote it

    def as_message(self) -> Dict[str, Any]:
        return {"id": self.id, "type": "function", "function": {"name": self.name, "arguments": self.arguments}}


@dataclass(frozen=True)
class ToolCalls:
    """The model wants these tools to run before it continues."""

    calls: List[ToolCall]


@dataclass(frozen=True)
class StreamEnd:
    finish_reason: Optional[str] = None
    usage: Dict[str, Any] = field(default_factory=dict)


ChatEvent = Union[TextDelta, ToolCalls, StreamEnd]


def _create_openai_client(api_key: str, base_url: Optional[str] = None) -> OpenAI:
    if not OPENAI_AVAILABLE:
        raise ImportError("openai library is required for LLM backends.")

    client_args = {
        "api_key": api_key,
        "timeout": 30.0,
        "max_retries": 2,
    }
    if base_url:
        client_args["base_url"] = base_url

    client = OpenAI(**client_args)
    logger.info("🤖🔌 Prepared OpenAI-compatible client (base_url=%s)", base_url or "default")
    return client


class LLM:
    """
    Unified LLM interface for the supported backends: openai and vllm.
    """

    SUPPORTED_BACKENDS = ["openai", "vllm"]

    def __init__(
        self,
        backend: str,
        model: str,
        system_prompt: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        no_think: bool = False,
        reasoning_effort: Optional[str] = None,
    ):
        self.backend = (backend or "").strip().lower()
        if self.backend not in self.SUPPORTED_BACKENDS:
            raise ValueError(
                f"Unsupported backend '{backend}'. Supported backends: {self.SUPPORTED_BACKENDS}."
            )

        if not OPENAI_AVAILABLE:
            raise ImportError("openai library is required for openai/vllm backends.")

        self.model = model
        self.no_think = no_think
        self.reasoning_effort = reasoning_effort or None
        self._provided_api_key = api_key
        self._provided_base_url = base_url

        if self.backend == "openai":
            self.effective_api_key = self._provided_api_key or OPENAI_API_KEY
            if not self.effective_api_key:
                raise ValueError("OPENAI_API_KEY is required when backend='openai'.")
            self.effective_base_url = self._provided_base_url
        else:
            self.effective_api_key = self._provided_api_key or "vllm-key"
            self.effective_base_url = self._provided_base_url or VLLM_BASE_URL

        self.system_prompt = system_prompt
        self.system_prompt_message = (
            {"role": "system", "content": system_prompt} if system_prompt else None
        )

        self.client: Optional[OpenAI] = None
        self._client_initialized = False
        self._client_init_lock = Lock()

        self._active_requests: Dict[str, Dict[str, Any]] = {}
        self._requests_lock = Lock()

        logger.info(
            "🤖⚙️ LLM initialized (backend=%s, model=%s, reasoning_effort=%s, base_url=%s)",
            self.backend,
            self.model,
            self.reasoning_effort or "default",
            self.effective_base_url or "default",
        )

    def set_system_prompt(self, system_prompt: Optional[str]) -> None:
        self.system_prompt = system_prompt
        self.system_prompt_message = (
            {"role": "system", "content": system_prompt} if system_prompt else None
        )
        logger.info("🤖💬 System prompt updated.")

    def _lazy_initialize_clients(self) -> bool:
        if self._client_initialized:
            return self.client is not None

        with self._client_init_lock:
            if self._client_initialized:
                return self.client is not None

            init_ok = False
            try:
                self.client = _create_openai_client(
                    api_key=self.effective_api_key,
                    base_url=self.effective_base_url,
                )
                init_ok = self.client is not None
            except Exception as exc:
                logger.exception("🤖💥 Failed to initialize %s client: %s", self.backend, exc)
                init_ok = False
            finally:
                self._client_initialized = True

            if init_ok:
                logger.info("🤖✅ %s client initialized.", self.backend)
            return init_ok

    def _register_request(self, request_id: str, request_type: str, stream_obj: Optional[Any]) -> None:
        with self._requests_lock:
            self._active_requests[request_id] = {
                "type": request_type,
                "stream": stream_obj,
                "start_time": time.time(),
            }

    def _cancel_single_request_unsafe(self, request_id: str) -> bool:
        req_data = self._active_requests.pop(request_id, None)
        if not req_data:
            return False

        stream_obj = req_data.get("stream")
        if stream_obj and hasattr(stream_obj, "close") and callable(stream_obj.close):
            try:
                stream_obj.close()
            except Exception as exc:
                logger.warning("🤖⚠️ Error closing stream for %s: %s", request_id, exc, exc_info=False)

        return True

    def cancel_generation(self, request_id: Optional[str] = None) -> bool:
        cancelled_any = False
        with self._requests_lock:
            if request_id is None:
                request_ids = list(self._active_requests.keys())
            else:
                request_ids = [request_id] if request_id in self._active_requests else []

            for req_id in request_ids:
                if self._cancel_single_request_unsafe(req_id):
                    cancelled_any = True

        return cancelled_any

    def cleanup_stale_requests(self, timeout_seconds: int = 300) -> int:
        now = time.time()
        with self._requests_lock:
            stale_ids = [
                req_id
                for req_id, req_data in self._active_requests.items()
                if (now - req_data.get("start_time", 0)) > timeout_seconds
            ]

        cleaned = 0
        for req_id in stale_ids:
            if self.cancel_generation(req_id):
                cleaned += 1
        return cleaned

    def _yield_openai_chunks(self, stream: Any, request_id: str) -> Generator[str, None, None]:
        try:
            for chunk in stream:
                with self._requests_lock:
                    if request_id not in self._active_requests:
                        break

                if not getattr(chunk, "choices", None):
                    continue

                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield content
        except APIConnectionError as exc:
            with self._requests_lock:
                was_cancelled = request_id not in self._active_requests
            if not was_cancelled:
                raise ConnectionError(f"Streaming connection error: {exc}") from exc
        finally:
            if stream and hasattr(stream, "close") and callable(stream.close):
                try:
                    stream.close()
                except Exception:
                    pass

    def generate(
        self,
        text: str,
        history: Optional[List[Dict[str, str]]] = None,
        use_system_prompt: bool = True,
        request_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Generator[str, None, None]:
        if not self._lazy_initialize_clients():
            raise RuntimeError(f"LLM backend '{self.backend}' client failed to initialize.")

        req_id = request_id if request_id else f"{self.backend}-{uuid.uuid4()}"

        messages: List[Dict[str, str]] = []
        if use_system_prompt and self.system_prompt_message:
            messages.append(self.system_prompt_message)
        if history:
            messages.extend(history)

        if not messages or messages[-1].get("role") != "user":
            user_text = f"{text}/nothink" if self.no_think else text
            messages.append({"role": "user", "content": user_text})

        kwargs = build_request_kwargs(self.backend, self.model, self.reasoning_effort, **kwargs)

        stream = None
        try:
            assert self.client is not None
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                **kwargs,
            )
            self._register_request(req_id, self.backend, stream)
            yield from self._yield_openai_chunks(stream, req_id)
        except (APIConnectionError, APITimeoutError, TimeoutError) as exc:
            raise ConnectionError(f"Communication error during generation: {exc}") from exc
        except (APIError, RateLimitError):
            raise
        finally:
            with self._requests_lock:
                if req_id in self._active_requests:
                    self._cancel_single_request_unsafe(req_id)

    def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        request_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Generator[ChatEvent, None, None]:
        """Stream one model reply that may ask for tools.

        Yields ``TextDelta`` events while the answer is written, then one
        ``ToolCalls`` event if the model asked for tools, then ``StreamEnd``.
        The caller gives the full message list, including the system prompt.
        """
        if not self._lazy_initialize_clients():
            raise RuntimeError(f"LLM backend '{self.backend}' client failed to initialize.")

        req_id = request_id if request_id else f"{self.backend}-chat-{uuid.uuid4()}"
        request_kwargs = build_request_kwargs(self.backend, self.model, self.reasoning_effort, **kwargs)
        if tools:
            request_kwargs["tools"] = tools

        stream = None
        partial_calls: Dict[int, Dict[str, str]] = {}
        finish_reason: Optional[str] = None
        usage: Dict[str, Any] = {}
        cancelled = False
        try:
            assert self.client is not None
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                stream_options={"include_usage": True},
                **request_kwargs,
            )
            self._register_request(req_id, self.backend, stream)
            for chunk in stream:
                with self._requests_lock:
                    if req_id not in self._active_requests:
                        cancelled = True
                        break
                if getattr(chunk, "usage", None):
                    usage = chunk.usage.model_dump() if hasattr(chunk.usage, "model_dump") else dict(chunk.usage)
                if not getattr(chunk, "choices", None):
                    continue
                choice = chunk.choices[0]
                finish_reason = choice.finish_reason or finish_reason
                delta = choice.delta
                if getattr(delta, "content", None):
                    yield TextDelta(delta.content)
                for piece in getattr(delta, "tool_calls", None) or []:
                    slot = partial_calls.setdefault(piece.index, {"id": "", "name": "", "arguments": ""})
                    if piece.id:
                        slot["id"] = piece.id
                    if piece.function is not None:
                        slot["name"] += piece.function.name or ""
                        slot["arguments"] += piece.function.arguments or ""
        except (APIConnectionError, APITimeoutError, TimeoutError) as exc:
            with self._requests_lock:
                was_cancelled = req_id not in self._active_requests
            if was_cancelled:
                return
            raise ConnectionError(f"Communication error during generation: {exc}") from exc
        finally:
            with self._requests_lock:
                if req_id in self._active_requests:
                    self._cancel_single_request_unsafe(req_id)
            if stream is not None and hasattr(stream, "close"):
                try:
                    stream.close()
                except Exception:
                    pass

        if cancelled:
            return
        if partial_calls:
            yield ToolCalls(
                [
                    ToolCall(slot["id"] or f"call_{index}", slot["name"], slot["arguments"] or "{}")
                    for index, slot in sorted(partial_calls.items())
                ]
            )
        yield StreamEnd(finish_reason=finish_reason, usage=usage)

    def prewarm(self, max_retries: int = 1) -> bool:
        if not self._lazy_initialize_clients():
            return False

        attempts = 0
        prompt = "Respond with only the word 'OK'."
        while attempts <= max_retries:
            generator = None
            try:
                generator = self.generate(
                    text=prompt,
                    history=None,
                    use_system_prompt=True,
                    request_id=f"prewarm-{self.backend}-{uuid.uuid4()}",
                    temperature=0.1,
                )
                for _ in generator:
                    pass
                return True
            except (ConnectionError, APITimeoutError, APIConnectionError) as exc:
                if attempts < max_retries:
                    attempts += 1
                    time.sleep(2 * attempts)
                    self._client_initialized = False
                    logger.warning("🤖🔥 Retry prewarm after connection error: %s", exc)
                    continue
                return False
            except Exception as exc:
                logger.error("🤖🔥 Prewarm failed: %s", exc, exc_info=False)
                return False
            finally:
                if generator and hasattr(generator, "close"):
                    try:
                        generator.close()
                    except Exception:
                        pass

        return False

    def measure_inference_time(self, num_tokens: int = 10, **kwargs: Any) -> Optional[float]:
        if num_tokens <= 0:
            return None

        if not self._lazy_initialize_clients():
            return None

        req_id = f"measure-{self.backend}-{uuid.uuid4()}"
        history = [
            {"role": "system", "content": "You are a precise assistant. Follow instructions exactly."},
            {
                "role": "user",
                "content": "Repeat this sequence exactly: one two three four five six seven eight nine ten eleven twelve",
            },
        ]

        generator = None
        token_count = 0
        start_time = None
        end_time = None

        try:
            generator = self.generate(
                text="",
                history=history,
                use_system_prompt=False,
                request_id=req_id,
                **kwargs,
            )
            start_time = time.time()
            for token in generator:
                if token:
                    token_count += 1
                if token_count >= num_tokens:
                    end_time = time.time()
                    break

            if end_time is None:
                end_time = time.time()
        except Exception as exc:
            logger.error("🤖⏱️ Inference-time measurement failed: %s", exc, exc_info=False)
            return None
        finally:
            if generator and hasattr(generator, "close"):
                try:
                    generator.close()
                except Exception:
                    pass

        if start_time is None or end_time is None or token_count == 0:
            return None

        return (end_time - start_time) * 1000


class LLMGenerationContext:
    def __init__(
        self,
        llm: LLM,
        prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        use_system_prompt: bool = True,
        **kwargs: Any,
    ):
        self.llm = llm
        self.prompt = prompt
        self.history = history
        self.use_system_prompt = use_system_prompt
        self.kwargs = kwargs
        self.request_id = f"ctx-{llm.backend}-{uuid.uuid4()}"
        self.generator: Optional[Generator[str, None, None]] = None
        self._entered = False

    def __enter__(self) -> Generator[str, None, None]:
        if self._entered:
            raise RuntimeError("LLMGenerationContext cannot be re-entered")
        self._entered = True
        self.generator = self.llm.generate(
            self.prompt,
            self.history,
            self.use_system_prompt,
            request_id=self.request_id,
            **self.kwargs,
        )
        return self.generator

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.llm.cancel_generation(self.request_id)
        if self.generator and hasattr(self.generator, "close"):
            try:
                self.generator.close()
            except Exception:
                pass
        self.generator = None
        self._entered = False
        return False
