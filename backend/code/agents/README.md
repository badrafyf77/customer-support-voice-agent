# Agents

Agents decide what the assistant should say next. The shared voice runtime does
not know what kind of agent it is running; it only calls `BaseAgent.run_turn(...)`.

## Contract

Each agent should expose a builder from its `agent.py` file:

```python
def build_<name>_agent(context: dict) -> BaseAgent:
    ...
```

The returned `BaseAgent` must implement:

```python
async def run_turn(self, text: str, session: SessionContext) -> AgentResult:
    ...
```

`text` is the finished user turn, or `""` when the session starts. Return
`AgentResult.speak_stream(fn)` to speak the text a generator yields (the agent
runs its own model calls and tools inside it), `AgentResult.generate(prompt)`
to let the pipeline's own LLM answer, `AgentResult.ignore()` to stay silent, or
`AgentResult.finish()` to end the session.

`BaseAgent` also provides hooks an agent can override:

- `idle_turn(...)`: called often while nobody is speaking, so the agent can
  start a turn by itself (for example to give a background result).
- `close_session(...)`: called once when the call ends.
- `finish_session(...)` and `save_progress(...)`.

## Current Agents

| Agent | Folder | Purpose |
| --- | --- | --- |
| `support` | [`support`](./support) | ShopEasy supervisor. Talks to the customer. |
| `orders` | [`orders`](./orders) | Orders specialist, called by the supervisor in the background. |

`tool_loop.py` is the model -> tools -> model loop that both agents share.

## Adding Or Changing Agents

Keep agent-specific behavior in the agent folder:

- `agent.py` for orchestration
- `config.yaml` for per-agent settings
- `prompts.py` or `system_prompt.txt` for prompts
- `tools.py` for tools used only by that agent
- `README.md` for agent-specific setup and behavior notes

Register agent selection in [`../server.py`](../server.py). The current backend
uses `/ws` for `support`.
