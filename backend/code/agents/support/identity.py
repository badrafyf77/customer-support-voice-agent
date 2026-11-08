"""Steps 1 and 2 of a call, in plain code: find the customer, then confirm it's them.

No AI runs here. The customer says their phone number, code turns the words
into digits and looks it up, then asks "Am I speaking with <name>?". Each stage
allows 3 tries; after that the call goes to a human.

Stages:  ask_phone -> confirm_name -> verified
                  \\-> failed (too many tries)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from core.trace import Tracer

ASK_PHONE = "ask_phone"
CONFIRM_NAME = "confirm_name"
VERIFIED = "verified"
FAILED = "failed"

GREETING = "Hello, thanks for calling ShopEasy. To find your account, could you tell me your phone number, please?"

DIGIT_WORDS = {
    "zero": "0", "oh": "0", "o": "0", "nought": "0",
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9",
}
REPEAT_WORDS = {"double": 2, "triple": 3}

NO_PATTERNS = [r"\bno\b", r"\bnope\b", r"\bnah\b", r"\bnot\b", r"\bwrong\b", r"\bincorrect\b", r"\bisn'?t\b"]
YES_PATTERNS = [
    r"\byes\b", r"\byeah\b", r"\byep\b", r"\byup\b", r"\bya\b", r"\bcorrect\b", r"\bright\b",
    r"\bthat'?s me\b", r"\bit'?s me\b", r"\bit is\b", r"\bsure\b", r"\bspeaking\b", r"\bindeed\b",
]


def spoken_digits(text: str) -> str:
    """Turn "oh seven seven double oh 900 one oh one" into "07700900101"."""
    digits: list[str] = []
    repeat = 1
    for token in re.findall(r"[a-z]+|\d+", (text or "").lower()):
        if token in REPEAT_WORDS:
            repeat = REPEAT_WORDS[token]
            continue
        if token.isdigit():
            digits.append(token[0] * repeat + token[1:])
        elif token in DIGIT_WORDS:
            digits.append(DIGIT_WORDS[token] * repeat)
        repeat = 1
    number = "".join(digits)
    # "+44 7700 900101" is the same number as "07700 900101".
    if number.startswith("44") and len(number) == 12:
        number = "0" + number[2:]
    return number


def yes_or_no(text: str) -> bool | None:
    """True for yes, False for no, None when it isn't clear."""
    lowered = (text or "").lower()
    if any(re.search(pattern, lowered) for pattern in NO_PATTERNS):
        return False
    if any(re.search(pattern, lowered) for pattern in YES_PATTERNS):
        return True
    return None


def say_digits(number: str) -> str:
    """Read a number back one digit at a time: "0 7 7 0 0 …"."""
    return " ".join(number)


@dataclass
class IdentityReply:
    say: str
    stage: str
    customer: dict[str, Any] | None = None


class IdentityCheck:
    def __init__(
        self,
        lookup: Callable[[str], dict[str, Any]],
        tracer: Tracer | None = None,
        max_attempts: int = 3,
    ):
        self.lookup = lookup
        self.tracer = tracer
        self.max_attempts = max_attempts
        self.stage = ASK_PHONE
        self.phone_attempts = 0
        self.confirm_attempts = 0
        self.candidate: dict[str, Any] | None = None
        self.customer: dict[str, Any] | None = None
        # What the customer said before giving a number, e.g. "my parcel is late".
        # The supervisor answers it once the identity is verified.
        self.early_requests: list[str] = []

    @property
    def done(self) -> bool:
        return self.stage in {VERIFIED, FAILED}

    def greeting(self) -> str:
        self._trace("greeting", GREETING)
        return GREETING

    def handle(self, text: str) -> IdentityReply:
        if self.stage == ASK_PHONE:
            reply = self._handle_phone(text)
        elif self.stage == CONFIRM_NAME:
            reply = self._handle_confirm(text)
        else:
            reply = IdentityReply("", self.stage, self.customer)
        self._trace(text, reply.say)
        return reply

    def _handle_phone(self, text: str) -> IdentityReply:
        number = spoken_digits(text)
        if len(number) < 5:
            # "Oh, my parcel is late" or "order SE-1042 is late" is not a phone number.
            number = ""
        self.phone_attempts += 1

        if not number:
            if text.strip():
                self.early_requests.append(text.strip())
            if self._out_of_attempts(self.phone_attempts):
                return self._fail()
            return IdentityReply("I can help with that. First, could you tell me the phone number on your account?", ASK_PHONE)

        if len(number) < 10:
            if self._out_of_attempts(self.phone_attempts):
                return self._fail()
            return IdentityReply(
                f"I only heard {say_digits(number)}. Could you say the whole phone number, please?", ASK_PHONE
            )

        found = self.lookup(number)
        if not found.get("found"):
            if self._out_of_attempts(self.phone_attempts):
                return self._fail()
            return IdentityReply(
                f"I couldn't find an account with {say_digits(number)}. Could you say the number again, please?",
                ASK_PHONE,
            )

        self.candidate = found
        self.stage = CONFIRM_NAME
        self.confirm_attempts = 0
        return IdentityReply(f"Thank you. Am I speaking with {self._full_name(found)}?", CONFIRM_NAME)

    def _handle_confirm(self, text: str) -> IdentityReply:
        answer = yes_or_no(text)
        assert self.candidate is not None

        if answer is True:
            self.customer = self.candidate
            self.stage = VERIFIED
            return IdentityReply(f"Thanks, {self.customer['first_name']}.", VERIFIED, self.customer)

        if answer is False:
            # Wrong account: go back to the phone number, which uses a phone try.
            self.candidate = None
            self.stage = ASK_PHONE
            if self._out_of_attempts(self.phone_attempts):
                return self._fail()
            return IdentityReply("Sorry about that. Could you tell me your phone number again, please?", ASK_PHONE)

        self.confirm_attempts += 1
        if self._out_of_attempts(self.confirm_attempts):
            return self._fail()
        return IdentityReply(
            f"Sorry, was that a yes or a no? Am I speaking with {self._full_name(self.candidate)}?", CONFIRM_NAME
        )

    def _out_of_attempts(self, attempts: int) -> bool:
        return attempts >= self.max_attempts

    def _fail(self) -> IdentityReply:
        self.stage = FAILED
        return IdentityReply(
            "I'm sorry, I couldn't confirm your account. I'll pass you to a colleague who can help.", FAILED
        )

    @staticmethod
    def _full_name(customer: dict[str, Any]) -> str:
        return f"{customer['first_name']} {customer['last_name']}"

    def _trace(self, heard: str, said: str) -> None:
        if self.tracer:
            self.tracer.event(
                "identity_step",
                "code",
                input=heard,
                output=said,
                model_or_tool="identity",
                stage=self.stage,
                phone_attempts=self.phone_attempts,
                confirm_attempts=self.confirm_attempts,
                customer_id=(self.customer or {}).get("customer_id"),
            )
