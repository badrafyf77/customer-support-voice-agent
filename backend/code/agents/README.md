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
`AgentResult.generate(prompt)` to speak, `AgentResult.ignore()` to stay silent,
or `AgentResult.finish()` to end the session.

`BaseAgent` also provides default `finish_session(...)` and `save_progress(...)`
hooks that an agent can override.

## Current Agents

| Agent | Folder | Purpose |
| --- | --- | --- |
| `chat` | [`chat`](./chat) | General conversational voice assistant. |

## Adding Or Changing Agents

Keep agent-specific behavior in the agent folder:

- `agent.py` for orchestration
- `config.yaml` for per-agent settings
- `prompts.py` or `system_prompt.txt` for prompts
- `tools.py` for tools used only by that agent
- `README.md` for agent-specific setup and behavior notes

Register agent selection in [`../server.py`](../server.py). The current backend
uses `/ws` for `chat`.
