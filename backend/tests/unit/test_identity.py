import pytest

from agents.support.identity import (
    ASK_PHONE,
    CONFIRM_NAME,
    FAILED,
    VERIFIED,
    IdentityCheck,
    spoken_digits,
    yes_or_no,
)
from core.trace import Tracer

SARA = {"found": True, "customer_id": "C001", "first_name": "Sara", "last_name": "Benali"}


def lookup(number):
    return SARA if number == "07700900101" else {"found": False}


@pytest.fixture
def check(tmp_path):
    return IdentityCheck(lookup, tracer=Tracer("id", tmp_path))


@pytest.mark.parametrize(
    "heard",
    [
        "07700900101",
        "0 7 7 0 0 9 0 0 1 0 1",
        "07700 900 101",
        "zero seven seven zero zero nine zero zero one zero one",
        "oh seven seven double oh nine double oh one oh one",
        "It's 07700, 900101.",
        "plus four four 7700 900101",
    ],
)
def test_spoken_digits(heard):
    assert spoken_digits(heard) == "07700900101"


@pytest.mark.parametrize(
    "heard, expected",
    [
        ("Yes.", True), ("yeah that's me", True), ("Yep", True), ("That's right.", True), ("Speaking.", True),
        ("No.", False), ("Nope, that's not me", False), ("wrong person", False), ("That isn't me", False),
        ("Hmm, sorry?", None), ("", None),
    ],
)
def test_yes_or_no(heard, expected):
    assert yes_or_no(heard) is expected


def test_happy_path(check):
    assert "phone number" in check.greeting()
    reply = check.handle("oh seven seven double oh nine double oh one oh one")
    assert reply.stage == CONFIRM_NAME
    assert reply.say == "Thank you. Am I speaking with Sara Benali?"

    reply = check.handle("yes that's me")
    assert reply.stage == VERIFIED
    assert reply.customer["customer_id"] == "C001"
    assert check.done


def test_unknown_number_three_times_fails(check):
    assert check.handle("01234 567890").stage == ASK_PHONE
    reply = check.handle("01234 567890")
    assert "couldn't find an account with 0 1 2 3 4" in reply.say
    reply = check.handle("01234 567890")
    assert reply.stage == FAILED
    assert "colleague" in reply.say
    assert check.done


def test_short_number_asks_again(check):
    reply = check.handle("0 7 7 0 0")
    assert reply.stage == ASK_PHONE
    assert reply.say.startswith("I only heard 0 7 7 0 0")


def test_wrong_person_goes_back_to_phone(check):
    check.handle("07700900101")
    reply = check.handle("no, that's not me")
    assert reply.stage == ASK_PHONE
    assert "phone number again" in reply.say
    assert check.candidate is None
    # It still works on the next try.
    check.handle("07700900101")
    assert check.handle("yes").stage == VERIFIED


def test_unclear_answer_asks_again_then_fails(check):
    check.handle("07700900101")
    assert check.handle("hmm").say.startswith("Sorry, was that a yes or a no?")
    assert check.handle("what?").stage == CONFIRM_NAME
    assert check.handle("pardon").stage == FAILED


def test_problem_before_phone_is_remembered(check):
    reply = check.handle("Oh, my parcel is late")
    assert reply.stage == ASK_PHONE
    assert "phone number on your account" in reply.say
    assert check.early_requests == ["Oh, my parcel is late"]


def test_every_step_is_traced(check):
    check.greeting()
    check.handle("07700900101")
    check.handle("yes")
    lines = check.tracer.read()
    assert [line["kind"] for line in lines] == ["identity_step"] * 3
    assert [line["stage"] for line in lines] == [ASK_PHONE, CONFIRM_NAME, VERIFIED]
    assert lines[-1]["customer_id"] == "C001"
    assert lines[1]["input"] == "07700900101"


def test_order_number_is_not_taken_for_a_phone_number(check):
    reply = check.handle("Hi, my parcel SE-1042 is late")
    assert "phone number on your account" in reply.say
    assert check.early_requests == ["Hi, my parcel SE-1042 is late"]
