# Support Agent (Supervisor)

The ShopEasy supervisor. It is the only agent that talks to the customer.

## How a call works

1. **Identity steps, plain code** (`identity.py`): ask for the phone number,
   turn the spoken words into digits, find the customer, then ask "Am I speaking
   with <name>?". Three tries per stage, then a transfer to a human. The AI does
   nothing before this.
2. **Supervisor AI** (`supervisor.py`, model `gpt-5.4-mini`): answers with its
   tools, at most 5 tool calls per answer.
   - `search_faq`, `get_return_policy`, `create_ticket`, `transfer_to_human`
     run right away (they take milliseconds).
   - `ask_orders_agent` starts the [orders agent](../orders) in a background
     thread and returns "started" at once. The supervisor keeps talking. The
     result waits in a queue, and the voice runtime asks for it when nobody is
     speaking.
3. **Limits:** 5 tool calls per answer, 20 seconds before "this is taking
   longer than usual", and 15 minutes per call (warning at 14).

## Files

| File | Purpose |
| --- | --- |
| `agent.py` | `SupportAgent`: plugs the supervisor into the voice runtime. |
| `supervisor.py` | The supervisor: identity first, then the tool loop and background jobs. Knows nothing about audio. |
| `identity.py` | Steps 1 and 2 in plain code. |
| `prompt.md` | The supervisor's instructions. |
| `config.yaml` | Model, reasoning effort, limits, speech settings. |

## Changing it

- Behaviour: edit `prompt.md`, then run the scenarios (`pytest -m llm`).
- Model: `llm_model` and `reasoning_effort` in `config.yaml`.
