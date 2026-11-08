# Chat Agent

The chat agent is the default general voice assistant. It has no database,
tools, or authentication behavior.

## When It Runs

`code/server.py` selects this agent for every WebSocket session:

```text
/ws
```

## Files

| File | Purpose |
| --- | --- |
| `agent.py` | Implements `ChatAgent` and `build_chat_agent(...)`. |
| `config.yaml` | Chat-specific runtime settings layered over global config. |

## Behavior

- Turns the finalized user transcript into one `AgentResult` for the shared pipeline.
- Stays silent when the session starts and waits for the user to speak.
- Uses a short system prompt for concise spoken answers.

## How To Change It

- Edit `SYSTEM_PROMPT` in `agent.py` to change the assistant personality.
- Edit `config.yaml` to adjust per-agent runtime settings.
- Keep any chat-only tools or prompt helpers in this folder.
