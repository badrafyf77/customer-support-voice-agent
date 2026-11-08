import json
import time
from types import SimpleNamespace

from agents.tool_loop import ToolLoop
from core.trace import Tracer
from fakes import FakeLLM, call, calls, say
from services.llm import LLM, StreamEnd, TextDelta, ToolCalls

TOOLS = [{"type": "function", "function": {"name": "track_delivery", "parameters": {"type": "object"}}}]


def make_loop(llm, tracer=None, results=None, **kwargs):
    ran = []

    def run_tool(tool_call):
        ran.append((tool_call.name, json.loads(tool_call.arguments)))
        if results and tool_call.name in results:
            value = results[tool_call.name]
            return value() if callable(value) else value
        return {"ok": True}

    return ToolLoop(llm, "orders", TOOLS, run_tool, tracer=tracer, **kwargs), ran


def test_text_only_reply():
    llm = FakeLLM([say("Hello ", "there.")])
    loop, ran = make_loop(llm)
    messages = [{"role": "user", "content": "hi"}]

    assert "".join(loop.run(messages)) == "Hello there."
    assert ran == []
    assert loop.final_text == "Hello there."
    assert messages[-1] == {"role": "assistant", "content": "Hello there."}


def test_one_tool_then_answer():
    llm = FakeLLM([call("track_delivery", "c1", order_id="SE-1042"), say("It arrives Tuesday.")])
    loop, ran = make_loop(llm, results={"track_delivery": {"status": "in_transit"}})
    messages = [{"role": "user", "content": "where is SE-1042"}]

    assert "".join(loop.run(messages)) == "It arrives Tuesday."
    assert ran == [("track_delivery", {"order_id": "SE-1042"})]
    assert messages[1]["tool_calls"][0]["function"]["name"] == "track_delivery"
    assert messages[2] == {"role": "tool", "tool_call_id": "c1", "content": '{"status": "in_transit"}'}
    # The second request sees the tool result.
    assert llm.requests[1]["messages"][-1]["role"] == "tool"


def test_text_before_a_tool_is_spoken_first():
    llm = FakeLLM([call("track_delivery", text="Let me check. ", order_id="SE-1042"), say("Done.")])
    loop, _ = make_loop(llm)
    assert list(loop.run([{"role": "user", "content": "x"}])) == ["Let me check. ", "Done."]


def test_several_tools_in_one_reply():
    llm = FakeLLM([calls(("track_delivery", "a", {"order_id": "1"}), ("track_delivery", "b", {"order_id": "2"})), say("Both found.")])
    loop, ran = make_loop(llm)
    "".join(loop.run([{"role": "user", "content": "x"}]))
    assert [args["order_id"] for _, args in ran] == ["1", "2"]
    assert loop.tool_calls_made == 2


def test_limit_switches_tools_off(tmp_path):
    tracer = Tracer("limit", tmp_path)
    llm = FakeLLM([call("track_delivery", order_id=str(i)) for i in range(3)] + [say("Sorry, I couldn't find it.")])
    loop, ran = make_loop(llm, tracer=tracer, max_tool_calls=3)

    assert "".join(loop.run([{"role": "user", "content": "x"}])) == "Sorry, I couldn't find it."
    assert len(ran) == 3
    assert [r["tool_choice"] for r in llm.requests] == ["auto", "auto", "auto", "none"]
    assert [line["kind"] for line in tracer.read()].count("limit_hit") == 1


def test_calls_over_the_limit_get_an_error_result():
    llm = FakeLLM([calls(*[("track_delivery", f"c{i}", {"order_id": str(i)}) for i in range(3)]), say("ok")])
    loop, ran = make_loop(llm, max_tool_calls=2)
    messages = [{"role": "user", "content": "x"}]
    "".join(loop.run(messages))
    assert len(ran) == 2
    assert "limit reached" in messages[-2]["content"]  # the third tool message


def test_slow_tool_speaks_a_filler(tmp_path):
    tracer = Tracer("slow", tmp_path)

    def slow():
        time.sleep(0.3)
        return {"status": "ok"}

    llm = FakeLLM([call("track_delivery", order_id="1"), say("Here it is.")])
    loop, _ = make_loop(llm, tracer=tracer, results={"track_delivery": slow}, slow_tool_seconds=0.05)

    spoken = "".join(loop.run([{"role": "user", "content": "x"}]))
    assert "it'll take a few seconds" in spoken
    assert spoken.endswith("Here it is.")
    assert "filler" in [line["kind"] for line in tracer.read()]


def test_fast_tool_has_no_filler():
    llm = FakeLLM([call("track_delivery", order_id="1"), say("Here it is.")])
    loop, _ = make_loop(llm, slow_tool_seconds=1.0)
    assert "".join(loop.run([{"role": "user", "content": "x"}])) == "Here it is."


def test_model_calls_are_traced(tmp_path):
    tracer = Tracer("trace", tmp_path)
    llm = FakeLLM([call("track_delivery", order_id="1"), say("ok")])
    loop, _ = make_loop(llm, tracer=tracer)
    "".join(loop.run([{"role": "user", "content": "x"}]))

    llm_lines = [line for line in tracer.read() if line["kind"] == "llm_call"]
    assert len(llm_lines) == 2
    assert llm_lines[0]["output"]["tool_calls"][0]["name"] == "track_delivery"
    assert llm_lines[0]["usage"] == {"total_tokens": 10}
    assert llm_lines[1]["output"]["text"] == "ok"


# --- LLM.stream_chat with a fake OpenAI stream -------------------------------------


def chunk(content=None, tool_calls=None, finish_reason=None, usage=None):
    if usage is not None:
        return SimpleNamespace(choices=[], usage=SimpleNamespace(model_dump=lambda: usage))
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)], usage=None)


def tool_piece(index, id=None, name=None, arguments=None):
    return SimpleNamespace(index=index, id=id, function=SimpleNamespace(name=name, arguments=arguments))


def fake_openai_llm(chunks, captured):
    llm = LLM("openai", "gpt-5.4-mini", api_key="test", reasoning_effort="low")

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return iter(chunks)

    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    llm._client_initialized = True
    return llm


def test_stream_chat_puts_tool_call_pieces_together():
    captured = {}
    chunks = [
        chunk(content="One moment. "),
        chunk(tool_calls=[tool_piece(0, id="call_1", name="track_", arguments='{"order')]),
        chunk(tool_calls=[tool_piece(0, name="delivery", arguments='_id": "SE-1042"}')]),
        chunk(finish_reason="tool_calls"),
        chunk(usage={"total_tokens": 42}),
    ]
    llm = fake_openai_llm(chunks, captured)
    events = list(llm.stream_chat([{"role": "user", "content": "x"}], tools=TOOLS))

    assert events[0] == TextDelta("One moment. ")
    assert isinstance(events[1], ToolCalls)
    [tool_call] = events[1].calls
    assert (tool_call.id, tool_call.name, json.loads(tool_call.arguments)) == ("call_1", "track_delivery", {"order_id": "SE-1042"})
    assert events[2] == StreamEnd(finish_reason="tool_calls", usage={"total_tokens": 42})

    assert captured["tools"] == TOOLS
    assert captured["reasoning_effort"] == "low"
    assert "temperature" not in captured


def test_stream_chat_text_only():
    llm = fake_openai_llm([chunk(content="Hi"), chunk(finish_reason="stop")], {})
    events = list(llm.stream_chat([{"role": "user", "content": "x"}]))
    assert events == [TextDelta("Hi"), StreamEnd(finish_reason="stop", usage={})]


def test_interrupt_is_traced(tmp_path):
    tracer = Tracer("interrupt", tmp_path)
    llm = FakeLLM([say("First part. ", "Second part.")])
    loop, _ = make_loop(llm, tracer=tracer)
    stream = loop.run([{"role": "user", "content": "x"}])
    assert next(stream) == "First part. "
    stream.close()  # the customer started talking

    [line] = tracer.read()
    assert line["interrupted"] is True
    assert line["output"]["text"] == "First part. "
