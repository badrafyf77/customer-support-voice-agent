import logging
import os
import sys
import time
import uuid
from threading import Lock
from typing import Any, Dict, Generator, List, Optional

from services import atlas

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


def _create_openai_client(api_key: str, base_url: Optional[str] = None, max_retries: int = 2) -> OpenAI:
    if not OPENAI_AVAILABLE:
        raise ImportError("openai library is required for LLM backends.")

    client_args = {
        "api_key": api_key,
        "timeout": 30.0,
        "max_retries": max_retries,
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
        chat_format: str = "auto",
        max_tokens: Optional[int] = None,
        context_limit: Optional[int] = None,
    ):
        self.backend = (backend or "").strip().lower()
        if self.backend not in self.SUPPORTED_BACKENDS:
            raise ValueError(
                f"Unsupported backend '{backend}'. Supported backends: {self.SUPPORTED_BACKENDS}."
            )

        if not OPENAI_AVAILABLE:
            raise ImportError("openai library is required for openai/vllm backends.")

        self.model = model
        self.chat_format = ("atlas" if model == atlas.MODEL_ID else "standard") if chat_format == "auto" else chat_format
        if self.chat_format not in {"standard", "atlas"}:
            raise ValueError("Unsupported LLM chat format")
        self.max_tokens = max_tokens
        self.context_limit = context_limit
        if self.chat_format == "atlas":
            if self.backend != "vllm" or model != atlas.MODEL_ID or no_think:
                raise ValueError("Atlas requires its pinned vLLM served model without /nothink")
            atlas.generation_options({}, max_tokens if max_tokens is not None else atlas.RESPONSE_LIMIT)
            if context_limit not in (None, atlas.CONTEXT_LIMIT):
                raise ValueError("Atlas Studio context limit must be 4096")
            self.context_limit = atlas.CONTEXT_LIMIT
        self.no_think = no_think
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
        self._cancel_epoch = 0

        logger.info(
            "🤖⚙️ LLM initialized (backend=%s, model=%s, base_url=%s)",
            self.backend,
            self.model,
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
                    max_retries=0 if self.chat_format == "atlas" else 2,
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

    @staticmethod
    def _close_stream(stream) -> None:
        if stream is not None and callable(getattr(stream, "close", None)):
            try:
                stream.close()
            except Exception:
                logger.debug("Error closing LLM stream", exc_info=True)

    def cancel_generation(self, request_id: Optional[str] = None) -> bool:
        with self._requests_lock:
            if request_id is None:
                # Includes generators created but not yet advanced by a worker.
                self._cancel_epoch += 1
                requests = list(self._active_requests.values())
                self._active_requests.clear()
            else:
                request = self._active_requests.pop(request_id, None)
                requests = [request] if request is not None else []
        # Closing a transport can block; never hold the request registry lock.
        for request in requests:
            self._close_stream(request.get("stream"))
        return bool(requests)

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

    def _yield_openai_chunks(self, stream: Any, request_id: str, ticket: dict) -> Generator[str, None, None]:
        try:
            for chunk in stream:
                with self._requests_lock:
                    if self._active_requests.get(request_id) is not ticket:
                        break

                if not getattr(chunk, "choices", None):
                    continue

                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield content
        except APIConnectionError as exc:
            with self._requests_lock:
                was_cancelled = self._active_requests.get(request_id) is not ticket
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
        # Capture the cancellation epoch when the worker is given a generator,
        # before the first next() triggers network work.
        with self._requests_lock:
            epoch = self._cancel_epoch
        req_id = request_id or f"{self.backend}-{uuid.uuid4()}"
        return self._generate(text, history, use_system_prompt, req_id, epoch, kwargs)

    def _generate(self, text, history, use_system_prompt, req_id, epoch, kwargs):
        if not self._lazy_initialize_clients():
            raise RuntimeError(f"LLM backend '{self.backend}' client failed to initialize.")
        if self.chat_format == "atlas":
            messages = atlas.format_messages(
                text, history, self.system_prompt if use_system_prompt else None,
            )
            kwargs = atlas.generation_options(
                kwargs, self.max_tokens if self.max_tokens is not None else atlas.RESPONSE_LIMIT,
            )
        else:
            messages = []
            if use_system_prompt and self.system_prompt_message:
                messages.append(dict(self.system_prompt_message))
            if history:
                messages.extend(dict(message) for message in history)
            if not messages or messages[-1].get("role") != "user":
                user_text = f"{text}/nothink" if self.no_think else text
                messages.append({"role": "user", "content": user_text})
            if self.max_tokens is not None:
                kwargs.setdefault("max_tokens", self.max_tokens)
        kwargs.setdefault("temperature", 0.8 if self.backend == "vllm" else 0.7)
        kwargs.setdefault("frequency_penalty", 0.25)
        kwargs.setdefault("presence_penalty", 0.1)

        ticket = {"type": self.backend, "stream": None, "start_time": time.time()}
        with self._requests_lock:
            if epoch != self._cancel_epoch:
                return
            if req_id in self._active_requests:
                raise ValueError(f"Duplicate active LLM request ID: {req_id}")
            # Cancellation must see requests waiting for HTTP response headers.
            self._active_requests[req_id] = ticket
        stream = None
        try:
            assert self.client is not None
            stream = self.client.chat.completions.create(
                model=self.model, messages=messages, stream=True, **kwargs,
            )
            with self._requests_lock:
                active = self._active_requests.get(req_id) is ticket
                if active:
                    ticket["stream"] = stream
            if not active:
                return
            chunks = self._yield_openai_chunks(stream, req_id, ticket)
            yield from atlas.spoken_chunks(chunks) if self.chat_format == "atlas" else chunks
        except Exception as exc:
            with self._requests_lock:
                cancelled = self._active_requests.get(req_id) is not ticket
            if cancelled:
                return
            if isinstance(exc, (APIConnectionError, APITimeoutError, TimeoutError)):
                raise ConnectionError(f"Communication error during generation: {exc}") from exc
            raise
        finally:
            with self._requests_lock:
                if self._active_requests.get(req_id) is ticket:
                    self._active_requests.pop(req_id)
            self._close_stream(stream)

    def prewarm(self, max_retries: int = 1) -> bool:
        if not self._lazy_initialize_clients():
            return False

        attempts = 0
        prompt = "جاوب غير بكلمة واخا." if self.chat_format == "atlas" else "Respond with only the word 'OK'."
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

        if self.chat_format == "atlas":
            history = [{"role": "user", "content": "عاود هاد الكلمات: واحد جوج ثلاثة ربعة خمسة ستة سبعة تمانية تسعود عشرة."}]
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
