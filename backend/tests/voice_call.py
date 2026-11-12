"""A spoken test call against a running voice backend, without a browser.

It turns each customer line into speech with macOS ``say``, streams it over the
WebSocket like the frontend's microphone (48 kHz, 16-bit mono, 2048-sample
packets with the 8-byte header), and prints what the agent hears and says.
It also acts like the browser's speaker: it reports ``tts_start`` / ``tts_stop``
while the agent's audio would be playing.

    .venv/bin/python tests/voice_call.py https://<your-modal-address>
    .venv/bin/python tests/voice_call.py http://localhost:8080      # docker compose

Needs macOS (for ``say`` and ``afconvert``) and ``pip install websockets``.
This uses the real OpenAI models, so a call costs a little.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import struct
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import websockets

RATE_IN = 48_000  # what the browser microphone sends
RATE_OUT = 24_000  # what the server's speech comes back as
BATCH = 2048  # samples per packet, like the frontend
QUIET_SECONDS = 4.0  # the agent counts as done after this long without new speech (or playback)
MAX_CALL_SECONDS = 300  # give up on a call that hangs, so it can't keep a GPU busy

DEFAULT_LINES = [
    "Oh seven seven oh oh, nine oh oh, one oh one.",
    "Yes, that's me.",
    "Where is my order S E one oh four two?",
    "When are you open?",
    "Can I talk to a real person, please?",
]


def speech_pcm(text: str, workdir: Path) -> bytes:
    """Speak ``text`` with macOS ``say`` and return 48 kHz 16-bit mono PCM."""
    aiff, wav = workdir / "line.aiff", workdir / "line.wav"
    subprocess.run(["say", "-o", str(aiff), text], check=True)
    subprocess.run(["afconvert", "-f", "WAVE", "-d", f"LEI16@{RATE_IN}", "-c", "1", str(aiff), str(wav)], check=True)
    with wave.open(str(wav)) as f:
        return f.readframes(f.getnframes())


class Call:
    def __init__(self, url: str):
        base = url.rstrip("/")
        self.ws_url = base.replace("https://", "wss://").replace("http://", "ws://") + "/ws"
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.playing_until = 0.0  # when the agent's audio would stop playing
        self.playing = False
        self.last_activity = time.monotonic()
        self.speech_sent_at: float | None = None
        self.first_audio_after_speech: list[float] = []
        self.answers: list[str] = []
        self.heard: list[str] = []
        self.finished = False
        self.ready = asyncio.Event()

    def log(self, who: str, text: str) -> None:
        print(f"[{time.strftime('%H:%M:%S')}] {who:<9} {text}", flush=True)

    async def receive(self, ws) -> None:
        async for raw in ws:
            message = json.loads(raw)
            kind = message.get("type")
            now = time.monotonic()
            if kind == "status":
                self.log("status", f"{message.get('status')}: {message.get('message', '')}")
                if message.get("status") == "ready":
                    self.last_activity = now
                    self.ready.set()
            elif kind == "final_user_request":
                self.heard.append(message.get("content", ""))
                self.log("heard", repr(message.get("content")))
                self.last_activity = now
            elif kind == "tts_chunk":
                samples = len(base64.b64decode(message["content"])) // 2
                start = max(now, self.playing_until)
                self.playing_until = start + samples / RATE_OUT
                if self.speech_sent_at is not None:
                    self.first_audio_after_speech.append(now - self.speech_sent_at)
                    self.log("timing", f"first agent audio {now - self.speech_sent_at:.2f}s after the customer stopped talking")
                    self.speech_sent_at = None
                if not self.playing:
                    self.playing = True
                    await ws.send(json.dumps({"type": "tts_start"}))
                self.last_activity = now
            elif kind == "final_assistant_answer":
                self.answers.append(message.get("content", ""))
                self.log("agent", message.get("content", ""))
                self.last_activity = now
            elif kind in {"tts_interruption", "stop_tts"}:
                self.playing_until = now
            elif kind == "finish_complete":
                self.log("status", "call finished by the agent")
                self.finished = True

    async def speaker(self, ws) -> None:
        """Pretend to play the audio: tell the server when playback stops."""
        while True:
            await asyncio.sleep(0.05)
            if self.playing and time.monotonic() >= self.playing_until:
                self.playing = False
                self.last_activity = time.monotonic()
                await ws.send(json.dumps({"type": "tts_stop"}))

    async def microphone(self, ws) -> None:
        """Stream audio non-stop like a real microphone: speech when queued, silence otherwise."""
        silence = b"\x00\x00" * BATCH
        pending = b""
        next_send = time.monotonic()
        while True:
            if not pending and not self.queue.empty():
                pending = await self.queue.get()
            is_speech = bool(pending)
            if is_speech:
                chunk, pending = pending[: BATCH * 2].ljust(BATCH * 2, b"\x00"), pending[BATCH * 2 :]
            else:
                chunk = silence
            header = struct.pack("!II", int(time.time() * 1000) & 0xFFFFFFFF, 1 if self.playing else 0)
            await ws.send(header + chunk)
            if is_speech and not pending:
                self.speech_sent_at = time.monotonic()  # the customer just stopped talking
            next_send += BATCH / RATE_IN
            await asyncio.sleep(max(0.0, next_send - time.monotonic()))

    async def wait_until_quiet(self, timeout: float = 90.0) -> None:
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            await asyncio.sleep(0.2)
            idle = time.monotonic() - self.last_activity
            if not self.playing and idle >= QUIET_SECONDS:
                return
            if self.finished:
                return
        self.log("warning", "the agent never went quiet")

    async def conversation(self, lines: list[str], speech: list[bytes]) -> None:
        await asyncio.wait_for(self.ready.wait(), timeout=600)
        while not self.answers:  # wait for the greeting before speaking
            await asyncio.sleep(0.1)
        await self.wait_until_quiet()
        for line, pcm in zip(lines, speech):
            if self.finished:
                break
            self.log("customer", line)
            heard_before = len(self.heard)
            await self.queue.put(pcm)
            # Wait until the server has heard this line (its turn ended), then
            # until the agent has finished answering.
            deadline = time.monotonic() + len(pcm) / 2 / RATE_IN + 20
            while len(self.heard) == heard_before and time.monotonic() < deadline and not self.finished:
                await asyncio.sleep(0.1)
            if len(self.heard) == heard_before:
                self.log("warning", "the server never ended this turn; stopping the call")
                return
            await self.wait_until_quiet()

    async def run(self, lines: list[str]) -> int:
        workdir = Path(tempfile.mkdtemp())
        speech = [speech_pcm(line, workdir) for line in lines]
        self.log("connect", self.ws_url)
        async with websockets.connect(self.ws_url, max_size=None, open_timeout=600, ping_interval=20) as ws:
            tasks = [asyncio.create_task(c(ws), name=c.__name__) for c in (self.receive, self.speaker, self.microphone)]
            script = asyncio.create_task(self.conversation(lines, speech), name="conversation")
            try:
                # Stop at the first problem: a crashed helper must not leave the call hanging.
                done, _ = await asyncio.wait([script, *tasks], timeout=MAX_CALL_SECONDS, return_when=asyncio.FIRST_COMPLETED)
                if not done:
                    self.log("warning", f"the call took longer than {MAX_CALL_SECONDS}s, hanging up")
                for task in done:
                    if task is not script and not task.cancelled() and task.exception():
                        self.log("error", f"{task.get_name()} crashed: {task.exception()!r}")
                    elif task is not script:
                        self.log("warning", f"{task.get_name()} stopped (the server closed the connection?)")
            finally:
                for task in [script, *tasks]:
                    task.cancel()

        print()
        if self.first_audio_after_speech:
            times = sorted(self.first_audio_after_speech)
            print(f"first agent audio after the customer stopped: median {times[len(times) // 2]:.2f}s, max {times[-1]:.2f}s")
        print(f"agent answers: {len(self.answers)}, call finished by agent: {self.finished}")
        return 0 if self.answers else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", help="backend address, e.g. https://...modal.run or http://localhost:8080")
    parser.add_argument("--line", action="append", help="a customer line (repeat); default: a short test call")
    args = parser.parse_args()
    return asyncio.run(Call(args.url).run(args.line or DEFAULT_LINES))


if __name__ == "__main__":
    sys.exit(main())
