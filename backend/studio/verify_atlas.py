"""Offline verification of the pinned tokenizer, native template and both EOS IDs.

No weights are loaded. Requires the prepared Atlas tokenizer and Transformers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from services.atlas import MODEL_ID, REVISION, EOS_IDS, format_messages

HERE = Path(__file__).resolve().parent


def verify(directory):
    from transformers import AutoTokenizer

    directory = Path(directory)
    contract = json.loads((HERE / "atlas_contract.json").read_text())
    lock = json.loads((HERE / "models.lock.json").read_text())["models"]["llm"]
    if (contract["model_id"], contract["revision"]) != (MODEL_ID, REVISION):
        raise ValueError("Atlas contract identity mismatch")
    for name, record in lock["files"].items():
        if not record.get("sha256") or name.endswith(".safetensors"):
            continue
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError(f"Atlas metadata hash mismatch: {name}")
    tokenizer = AutoTokenizer.from_pretrained(str(directory), local_files_only=True)
    if tokenizer.chat_template != contract["chat_template"]:
        raise ValueError("Atlas native template changed")
    for token, expected in contract["special_token_ids"].items():
        if tokenizer.convert_tokens_to_ids(token) != expected:
            raise ValueError(f"Unexpected Atlas token ID: {token}")
    for name in ("config.json", "generation_config.json"):
        if json.loads((directory / name).read_text())["eos_token_id"] != EOS_IDS:
            raise ValueError(f"Atlas EOS configuration mismatch: {name}")
    history = [{"role": "user", "content": "سلام، أنا Sara. الطلب AB-1203."},
               {"role": "assistant", "content": "سلام Sara، كيفاش نعاونك؟"},
               {"role": "user", "content": "رقمي 0612345678، والثمن 12.50."}]
    messages = format_messages("", history, "جاوب بالدارجة المغربية.")
    rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    expected = "<bos>" + "".join(
        f"<start_of_turn>{'model' if m['role'] == 'assistant' else 'user'}\n{m['content'].strip()}<end_of_turn>\n"
        for m in messages
    ) + "<start_of_turn>model\n"
    if rendered != expected:
        raise ValueError("Unexpected Atlas history/generation prompt rendering")
    ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
    if ids[0] != 2 or ids.count(107) != len(messages):
        raise ValueError("Atlas turn tokenization mismatch")
    for invalid in ([{"role": "system", "content": "test"}],
                    [{"role": "user", "content": "one"}, {"role": "user", "content": "two"}]):
        try:
            tokenizer.apply_chat_template(invalid, tokenize=False, add_generation_prompt=True)
        except Exception:
            pass
        else:
            raise ValueError("Native template unexpectedly accepted invalid roles")
    return {"model_id": MODEL_ID, "revision": REVISION, "eos_token_ids": EOS_IDS,
            "special_token_ids": contract["special_token_ids"], "native_template_verified": True,
            "multi_turn_generation_prompt_verified": True, "identifiers_preserved": True,
            "sample_prompt_tokens": len(ids), "weights_loaded": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    report = verify(args.model_dir)
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
