"""Scenario tests: real conversations with the real OpenAI models, checked against the trace.

Run with:  pytest -m llm            (each scenario 3 times)
           SCENARIO_RUNS=1 pytest -m llm -k track_single_order
"""
from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

import pytest
import yaml

from core.config import CODE_ROOT
from scenario_checks import check_turn
from text_runner import run_conversation

SCENARIO_DIR = Path(__file__).with_name("scenarios")
RUNS = int(os.getenv("SCENARIO_RUNS", "3"))
RESULTS: dict[str, list[bool]] = {}


def load_scenarios() -> list[dict]:
    return [yaml.safe_load(path.read_text(encoding="utf-8")) for path in sorted(SCENARIO_DIR.glob("*.yaml"))]


def customer_lines(scenario: dict) -> tuple[list[str], list[dict]]:
    """The lines the customer says, with the identity turns added when ``phone`` is set."""
    turns = list(scenario["turns"])
    if scenario.get("phone"):
        turns = [{"say": scenario["phone"]}, {"say": "Yes, that's me."}] + turns
    return [turn["say"] for turn in turns], turns


@pytest.fixture(scope="session", autouse=True)
def openai_key():
    try:
        from dotenv import load_dotenv

        load_dotenv(CODE_ROOT.parent / ".env")
    except ImportError:
        pass
    if not os.getenv("OPENAI_API_KEY", "").startswith("sk-"):
        pytest.skip("OPENAI_API_KEY is missing or not an OpenAI key (set it in backend/.env)")


@pytest.mark.llm
@pytest.mark.parametrize("run_number", range(1, RUNS + 1), ids=lambda n: f"run{n}")
@pytest.mark.parametrize("scenario", load_scenarios(), ids=lambda s: s["name"])
def test_scenario(scenario, run_number):
    today = date.today()
    lines, turns = customer_lines(scenario)
    session_id = f"{scenario['name']}-run{run_number}-{datetime.now().strftime('%H%M%S')}"
    conversation = run_conversation(lines, session_id, today=today)

    problems = []
    if len(conversation.turns) < len(turns):
        problems.append(f"the call ended after {len(conversation.turns)} of {len(turns)} customer turns")
    for index, (turn, run) in enumerate(zip(turns, conversation.turns), start=1):
        problems += [f"turn {index} ({turn['say']!r}): {problem}" for problem in check_turn(turn, run, today)]

    RESULTS.setdefault(scenario["name"], []).append(not problems)
    assert not problems, "\n".join(problems + [f"trace: {conversation.trace_path}"])
