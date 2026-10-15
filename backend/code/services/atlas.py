"""Atlas's native Gemma conversation contract at the API boundary."""
from __future__ import annotations

MODEL_ID = "MBZUAI-Paris/Atlas-Chat-2B"
REVISION = "a6244a4c50bc32b65c6c8dc4dc1dab218b580088"
EOS_IDS = [1, 107]
CONTEXT_LIMIT = 4096
RESPONSE_LIMIT = 256
MARKERS = ("<bos>", "<eos>", "<start_of_turn>", "<end_of_turn>", "<pad>")


def format_messages(text, history=None, system_prompt=None):
    """Copy history; fold instructions and coalesce unanswered/interrupted turns.

    The transcript remains untouched. No synthetic assistant turn is inserted.
    """
    instructions = [system_prompt] if system_prompt else []
    turns = []
    for message in history or []:
        role, content = message.get("role"), message.get("content")
        if not isinstance(content, str):
            raise ValueError("Atlas requires text message content")
        if role == "system":
            instructions.append(content)
        elif role in {"user", "assistant"}:
            turns.append({"role": role, "content": content})
        else:
            raise ValueError(f"Unsupported Atlas role: {role}")
    if text and (not turns or turns[-1] != {"role": "user", "content": text}):
        turns.append({"role": "user", "content": text})
    merged = []
    for turn in turns:
        if merged and merged[-1]["role"] == turn["role"]:
            merged[-1]["content"] += "\n\n" + turn["content"]
        else:
            merged.append(dict(turn))
    if not merged or merged[0]["role"] != "user" or merged[-1]["role"] != "user":
        raise ValueError("Atlas generation requires a conversation starting and ending with a user")
    if instructions:
        merged[0]["content"] = "\n\n".join(instructions + [merged[0]["content"]])
    return merged


def generation_options(options, response_limit=RESPONSE_LIMIT):
    """Bound the response and preserve both pinned EOS IDs in vLLM sampling."""
    options = dict(options)
    cap = options.pop("max_tokens", response_limit)
    completion_cap = options.pop("max_completion_tokens", cap)
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 1
           for v in (response_limit, cap, completion_cap)):
        raise ValueError("Atlas response caps must be positive integers")
    if options.get("n", 1) != 1:
        raise ValueError("Atlas voice chat permits one response per turn")
    options["n"] = 1
    options["max_tokens"] = min(cap, completion_cap, response_limit, RESPONSE_LIMIT)
    extra = dict(options.get("extra_body") or {})
    # extra_body is merged into the request by the SDK; never allow it to replace
    # messages, the native template, or the response/context contract.
    forbidden = {"model", "messages", "stream", "max_tokens", "max_completion_tokens",
                 "chat_template", "chat_template_kwargs", "add_generation_prompt",
                 "continue_final_message", "truncate_prompt_tokens", "min_tokens", "n", "best_of"}
    if forbidden.intersection(extra):
        raise ValueError("Atlas extra_body cannot override its conversation contract")
    extra.update(stop_token_ids=list(EOS_IDS), ignore_eos=False,
                 skip_special_tokens=True, include_stop_str_in_output=False)
    options["extra_body"] = extra
    return options


def spoken_chunks(chunks):
    """Withhold split role tokens; stop before any model turn marker is spoken."""
    pending = ""
    for chunk in chunks:
        pending += chunk
        indices = [pending.find(marker) for marker in MARKERS if marker in pending]
        if indices:
            prefix = pending[:min(indices)]
            if prefix:
                yield prefix
            return
        overlap = max((size for marker in MARKERS
                       for size in range(1, min(len(marker), len(pending) + 1))
                       if pending.endswith(marker[:size])), default=0)
        ready = pending[:-overlap] if overlap else pending
        pending = pending[-overlap:] if overlap else ""
        if ready:
            yield ready
    # A dangling marker prefix is withheld; all other text has already streamed.
