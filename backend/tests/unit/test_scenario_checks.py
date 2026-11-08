"""The scenario checker itself, run on a fake conversation (no real AI)."""
import json
from datetime import date

from fakes import FakeLLM, call, say
from scenario_checks import check_turn, fill_dates
from test_scenarios import customer_lines, load_scenarios
from text_runner import run_conversation

TODAY = date(2026, 11, 8)


def orders_answer(status, message, order_ids=()):
    return say(json.dumps({"status": status, "message": message, "order_ids": list(order_ids)}))


def fake_track_conversation(tmp_path):
    llm = FakeLLM([
        call("ask_orders_agent", request="Where is order SE-1042?"),
        say("Let me check that for you."),
        say("Your headphones arrive on Tuesday 10 November."),
    ])
    orders_llm = FakeLLM([
        call("track_delivery", order_id="SE-1042"),
        orders_answer("done", "SE-1042 arrives Tuesday 10 November.", ["SE-1042"]),
    ])
    lines = ["07700900101", "yes", "Where is my order SE-1042?"]
    return run_conversation(lines, "check-test", trace_dir=tmp_path, today=TODAY, llm=llm, orders_llm=orders_llm)


TRACK_TURN = {
    "say": "Where is my order SE-1042?",
    "expect_calls": [
        {"supervisor": "ask_orders_agent", "args": {"request": "1042"}},
        {"orders": ["track_delivery", "get_order"], "args": {"order_id": "1042"}},
    ],
    "orders_result": "done",
    "must_not_call": ["transfer_to_human"],
    "answer_contains": [["{day+2}", "{date+2}"]],
}


def test_fill_dates():
    assert fill_dates("{day+2} / {date+2} / {day-1}", TODAY) == "Tuesday / 10 November / Saturday"


def test_runner_collects_the_background_answer(tmp_path):
    conversation = fake_track_conversation(tmp_path)
    turn = conversation.turns[2]
    assert turn.spoken == "Let me check that for you."
    assert turn.background == ["Your headphones arrive on Tuesday 10 November."]
    assert conversation.trace_path.exists()


def test_a_correct_turn_passes(tmp_path):
    run = fake_track_conversation(tmp_path).turns[2]
    assert check_turn(TRACK_TURN, run, TODAY) == []


def test_wrong_expectations_are_reported(tmp_path):
    run = fake_track_conversation(tmp_path).turns[2]
    wrong = {
        "expect_calls": [{"orders": "track_delivery"}, {"supervisor": "ask_orders_agent"}],  # wrong order
        "must_not_call": ["track_delivery"],
        "orders_result": "cannot",
        "answer_contains": ["Friday"],
        "expect_finished": True,
    }
    problems = check_turn(wrong, run, TODAY)
    assert len(problems) == 5
    assert "not found in order" in problems[0]


def test_wrong_arguments_fail(tmp_path):
    run = fake_track_conversation(tmp_path).turns[2]
    turn = {"expect_calls": [{"orders": "track_delivery", "args": {"order_id": "1051"}}]}
    assert check_turn(turn, run, TODAY)


def test_every_scenario_file_is_valid():
    scenarios = load_scenarios()
    assert len(scenarios) == 15
    names = [scenario["name"] for scenario in scenarios]
    assert len(set(names)) == len(names)
    allowed = {"say", "expect_calls", "must_not_call", "orders_result", "answer_contains", "expect_finished"}
    for scenario in scenarios:
        lines, turns = customer_lines(scenario)
        assert lines and all(isinstance(line, str) for line in lines)
        for turn in turns:
            assert set(turn) <= allowed, (scenario["name"], set(turn) - allowed)
            for expected in turn.get("expect_calls") or []:
                assert ("supervisor" in expected) != ("orders" in expected)
