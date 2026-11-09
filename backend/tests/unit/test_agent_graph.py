import json

from langchain_core.messages import HumanMessage
from langgraph.graph import START, StateGraph

from agents.graph import AgentState, TraceHandler, add_tool_agent
from core.trace import Tracer
from fakes import FakeChatModel, call, calls, say

TOOLS = [{"type": "function", "function": {"name": "track_delivery", "parameters": {"type": "object", "properties": {}}}}]


def build(model, tracer=None, max_tool_calls=5, results=None):
    ran = []

    def run_tool(tool_call, state):
        ran.append((tool_call["name"], tool_call["args"]))
        return (results or {}).get(tool_call["name"], {"ok": True})

    graph = StateGraph(AgentState)
    add_tool_agent(
        graph,
        agent="orders",
        model=model,
        tools=TOOLS,
        run_tool=run_tool,
        system_prompt=lambda state: "You are a test.",
        max_tool_calls=max_tool_calls,
        tracer=lambda: tracer,
    )
    graph.add_edge(START, "model")
    return graph.compile(), ran


def invoke(app, tracer=None, text="hi"):
    config = {"metadata": {"agent": "orders"}}
    if tracer:
        config["callbacks"] = [TraceHandler(tracer, "orders")]
    return app.invoke({"messages": [HumanMessage(text)], "tool_calls_made": 0}, config)


def test_text_only_reply():
    app, ran = build(FakeChatModel(replies=[say("Hello ", "there.")]))
    final = invoke(app)
    assert final["messages"][-1].text == "Hello there."
    assert ran == []


def test_system_prompt_comes_first():
    model = FakeChatModel(replies=[say("ok")])
    app, _ = build(model)
    invoke(app)
    first = model.requests[0]["messages"]
    assert first[0].type == "system" and first[0].text == "You are a test."
    assert first[1].text == "hi"


def test_one_tool_then_answer():
    model = FakeChatModel(replies=[call("track_delivery", "c1", order_id="SE-1042"), say("It arrives Tuesday.")])
    app, ran = build(model, results={"track_delivery": {"status": "in_transit"}})
    final = invoke(app)

    assert ran == [("track_delivery", {"order_id": "SE-1042"})]
    tool_message = final["messages"][2]
    assert tool_message.type == "tool" and tool_message.tool_call_id == "c1"
    assert json.loads(tool_message.content) == {"status": "in_transit"}
    assert final["messages"][-1].text == "It arrives Tuesday."
    assert final["tool_calls_made"] == 1


def test_several_tools_in_one_reply():
    model = FakeChatModel(replies=[calls(("track_delivery", "a", {"order_id": "1"}), ("track_delivery", "b", {"order_id": "2"})), say("Both found.")])
    app, ran = build(model)
    assert invoke(app)["tool_calls_made"] == 2
    assert [args["order_id"] for _, args in ran] == ["1", "2"]


def test_limit_switches_tools_off(tmp_path):
    tracer = Tracer("limit", tmp_path)
    model = FakeChatModel(replies=[call("track_delivery", order_id=str(i)) for i in range(3)] + [say("Sorry, I couldn't find it.")])
    app, ran = build(model, tracer=tracer, max_tool_calls=3)
    final = invoke(app)

    assert final["messages"][-1].text == "Sorry, I couldn't find it."
    assert len(ran) == 3
    assert [r["tool_choice"] for r in model.requests] == ["auto", "auto", "auto", "none"]
    assert [line["kind"] for line in tracer.read()].count("limit_hit") == 1


def test_calls_over_the_limit_get_an_error_result():
    model = FakeChatModel(replies=[calls(*[("track_delivery", f"c{i}", {"order_id": str(i)}) for i in range(3)]), say("ok")])
    app, ran = build(model, max_tool_calls=2)
    final = invoke(app)
    assert len(ran) == 2
    assert "limit reached" in final["messages"][-2].content  # the third tool message


def test_model_calls_are_traced(tmp_path):
    tracer = Tracer("trace", tmp_path)
    app, _ = build(FakeChatModel(replies=[call("track_delivery", order_id="1"), say("ok")]), tracer=tracer)
    invoke(app, tracer)

    llm_lines = [line for line in tracer.read() if line["kind"] == "llm_call"]
    assert len(llm_lines) == 2
    assert llm_lines[0]["agent"] == "orders"
    assert llm_lines[0]["output"]["tool_calls"] == [{"name": "track_delivery", "arguments": {"order_id": "1"}}]
    assert llm_lines[0]["usage"]["total_tokens"] == 10
    assert llm_lines[1]["output"]["text"] == "ok"
    assert llm_lines[0]["duration_ms"] >= 0


def test_trace_handler_skips_other_agents(tmp_path):
    tracer = Tracer("other", tmp_path)
    app, _ = build(FakeChatModel(replies=[say("ok")]))
    app.invoke(
        {"messages": [HumanMessage("hi")], "tool_calls_made": 0},
        {"metadata": {"agent": "orders"}, "callbacks": [TraceHandler(tracer, "supervisor")]},
    )
    assert tracer.read() == []
