# Exam Agent

The exam agent runs a structured oral exam. This is the only place where
Veridex, examiner wording, exam prompts, question tracking, and exam progress
belong.

## When It Runs

`code/server.py` selects this agent when the WebSocket connection includes exam
context query params:

```text
/ws?user_id=...&exam_id=...&attempt_id=...
```

The backend loads context from Supabase before building the agent.

## Files

| File | Purpose |
| --- | --- |
| `agent.py` | Orchestrates exam state, LangGraph planning, control payloads, and progress saving. |
| `prompts.py` | Builds personalized oral-exam prompts from loaded context. |
| `system_prompt.txt` | Static exam prompt asset kept with this agent. |
| `tools.py` | Reserved for tools that belong only to the exam agent. |
| `config.yaml` | Exam-specific runtime settings layered over global config. |

## Required Configuration

Exam sessions need Supabase context:

```bash
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
```

They also need the normal LLM/STT/TTS backend configuration described in the
backend README.

## Behavior

- Starts the oral exam from teacher-created exam context.
- Streams natural spoken examiner text to the shared TTS pipeline.
- Appends a machine-readable control suffix when needed.
- Lets `core/pipeline.py` strip the control suffix before TTS.
- Saves exam progress and completion through `services/database.py`.

Oral-attempt evaluation is not triggered here. This backend submits and saves
the oral attempt; evaluation should be handled by the evaluation system.

## How To Change It

- Put prompt changes in `prompts.py` or `system_prompt.txt`.
- Put orchestration and state-machine changes in `agent.py`.
- Put exam-only tools in `tools.py`.
- Keep generic STT, TTS, WebSocket, and pipeline behavior outside this folder.
