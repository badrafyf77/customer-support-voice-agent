import threading

import pytest

from core.trace import Tracer


def test_event_line_has_all_fields(tmp_path):
    tracer = Tracer("call-1", tmp_path)
    tracer.new_turn()
    tracer.event("user_said", "code", input="hello", extra_field=3)

    [line] = tracer.read()
    assert tracer.path == tmp_path / "call-1.jsonl"
    assert line["session_id"] == "call-1"
    assert line["turn_id"] == 1
    assert line["kind"] == "user_said"
    assert line["agent"] == "code"
    assert line["input"] == "hello"
    assert line["parent_id"] is None
    assert line["extra_field"] == 3
    for field in ("ts", "event_id", "output", "model_or_tool", "duration_ms"):
        assert field in line


def test_nested_spans_link_to_their_parent(tmp_path):
    tracer = Tracer("call-2", tmp_path)
    with tracer.span("agent_call", "supervisor", input="where is my order") as outer:
        with tracer.span("tool_call", "orders", model_or_tool="track_delivery") as inner:
            inner.output = {"status": "in_transit"}
            tracer.event("llm_call", "orders")
        outer.output = "done"

    lines = {line["kind"]: line for line in tracer.read()}
    assert lines["agent_call"]["parent_id"] is None
    assert lines["tool_call"]["parent_id"] == outer.event_id
    assert lines["llm_call"]["parent_id"] == inner.event_id
    assert lines["tool_call"]["output"] == {"status": "in_transit"}
    assert lines["agent_call"]["duration_ms"] >= 0


def test_explicit_parent_crosses_threads(tmp_path):
    tracer = Tracer("call-3", tmp_path)
    with tracer.span("agent_call", "supervisor") as parent:
        def job():
            tracer.event("tool_call", "orders", parent_id=parent.event_id)

        worker = threading.Thread(target=job)
        worker.start()
        worker.join()

    tool_line = next(line for line in tracer.read() if line["kind"] == "tool_call")
    assert tool_line["parent_id"] == parent.event_id


def test_failed_span_records_the_error(tmp_path):
    tracer = Tracer("call-4", tmp_path)
    with pytest.raises(RuntimeError):
        with tracer.span("tool_call", "orders"):
            raise RuntimeError("database locked")

    [line] = tracer.read()
    assert line["error"] == "RuntimeError: database locked"


def test_unknown_kind_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        Tracer("call-5", tmp_path).event("made_up", "code")


def test_many_threads_write_valid_lines(tmp_path):
    tracer = Tracer("call-6", tmp_path)

    def write_many():
        for i in range(50):
            tracer.event("spoken", "supervisor", output="x" * 200 + str(i))

    threads = [threading.Thread(target=write_many) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(tracer.read()) == 400
