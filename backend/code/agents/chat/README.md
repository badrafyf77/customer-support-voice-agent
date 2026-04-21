# Chat Agent

The chat agent is the default general voice assistant. It has no database,
grading, exam, rubric, or authentication behavior.

## When It Runs

`code/server.py` selects this agent for plain WebSocket sessions:

```text
/ws
```

If exam query params are present, the backend selects the exam agent instead.

## Files

| File | Purpose |
| --- | --- |
| `agent.py` | Implements `ChatAgentBrain` and `build_chat_agent(...)`. |
| `config.yaml` | Chat-specific runtime settings layered over global config. |

## Behavior

- Queues the finalized user transcript.
- Returns one `AgentResult` for the shared pipeline.
- Uses a short system prompt for concise spoken answers.
- Does not call Supabase or any exam-specific service.

## How To Change It

- Edit `SYSTEM_PROMPT` in `agent.py` to change the assistant personality.
- Edit `config.yaml` to adjust per-agent runtime settings.
- Keep any chat-only tools or prompt helpers in this folder.

## How To Make It The Only Agent

In `code/server.py::ws_endpoint`, always build `build_chat_agent({})` and load
`load_agent_config("chat")` before calling `run_session(...)`.
