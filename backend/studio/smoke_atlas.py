"""Deferred Studio conversation/cancellation check, using the production LLM client."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from agents.chat.agent import DARIJA_SYSTEM_PROMPT
from services.atlas import MODEL_ID, MARKERS
from services.llm import LLM


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    base_url = os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8001/v1").rstrip("/")
    with urlopen(base_url + "/models", timeout=10) as response:
        models = json.load(response)["data"]
    served = next((m for m in models if m["id"] == MODEL_ID), None)
    if not served or served.get("max_model_len") != 4096:
        raise RuntimeError("Expected Atlas served model with max_model_len=4096")
    llm = LLM("vllm", MODEL_ID, system_prompt=DARIJA_SYSTEM_PROMPT, base_url=base_url,
              chat_format="atlas", max_tokens=256, context_limit=4096)
    report = {"model": MODEL_ID, "context_limit": 4096, "response_cap": 256,
              "cases": [], "human_quality_review_required": True}
    try:
        cases = json.loads(Path(__file__).with_name("atlas_cases.json").read_text())
        for case in cases:
            history, turns = [], []
            for text in case["turns"]:
                history.append({"role": "user", "content": text})
                started, first, chunks = time.monotonic(), None, []
                for value in llm.generate(text, history=history, temperature=0.3):
                    if first is None:
                        first = time.monotonic()
                    chunks.append(value)
                answer = "".join(chunks)
                history.append({"role": "assistant", "content": answer})
                turns.append({"user": text, "assistant": answer, "chunks": len(chunks),
                              "first_text_seconds": None if first is None else first-started,
                              "total_seconds": time.monotonic()-started,
                              "role_marker_detected": any(m in answer for m in MARKERS)})
            report["cases"].append({"name": case["name"], "review": case["review"], "turns": turns})
        generator = llm.generate("شرح ليا كيفاش كيخدم الإنترنت، بالتفصيل.", request_id="interrupt-check")
        try:
            first = next(generator)
            started = time.monotonic()
            cancelled = llm.cancel_generation("interrupt-check")
            after_stop = list(generator)
            report["interruption"] = {"first_chunk": first, "cancelled": cancelled,
                                      "chunks_after_stop": after_stop,
                                      "close_seconds": time.monotonic()-started}
            if not cancelled or after_stop:
                raise RuntimeError("Atlas client interruption check failed")
        finally:
            generator.close()
    finally:
        llm.cancel_generation()
        Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n")
    print(f"Saved {args.output}; review the replies and use chat_preview for audio/interruption checks.")


if __name__ == "__main__":
    run()
