from services.llm import build_request_kwargs, is_reasoning_model


def test_gpt5_models_are_reasoning_models():
    assert is_reasoning_model("gpt-5.4-mini")
    assert is_reasoning_model("gpt-5.5")
    assert is_reasoning_model("openai/gpt-5-mini")
    assert not is_reasoning_model("gpt-4o-mini")
    assert not is_reasoning_model("Qwen/Qwen2.5-7B-Instruct")


def test_reasoning_model_drops_sampling_settings():
    kwargs = build_request_kwargs(
        "openai", "gpt-5.4-mini", "low", temperature=0.1, presence_penalty=0.2, max_tokens=50
    )
    assert kwargs == {"reasoning_effort": "low", "max_completion_tokens": 50}


def test_reasoning_model_without_effort_sends_nothing_extra():
    assert build_request_kwargs("openai", "gpt-5.5", None) == {}


def test_older_model_keeps_sampling_defaults():
    kwargs = build_request_kwargs("vllm", "Qwen/Qwen2.5-7B-Instruct", "low")
    assert kwargs == {"temperature": 0.8, "frequency_penalty": 0.25, "presence_penalty": 0.1}


def test_older_model_keeps_given_temperature():
    kwargs = build_request_kwargs("openai", "gpt-4o-mini", None, temperature=0.1)
    assert kwargs["temperature"] == 0.1
