# L4 measurement and acceptance record

Status: **NOT YET RUN ON STUDIO**. Copy this template beside the generated
reports and fill it after the live run. Do not treat local deterministic tests as
model, acoustic, Linux-install or L4-performance evidence.

| Deployment | Recorded value |
| --- | --- |
| Date, Studio hardware/driver/CUDA toolkit | Pending |
| Git commit (`git rev-parse HEAD`) | Pending |
| Dependency installation from all three locks | Pending |
| All model revisions and hashes verified | Pending |
| Atlas BF16 / context 4096 / output 256 / concurrency 1 | Pending confirmation |
| SILMA voice1 + main / 32 steps / 24 kHz PCM16 | Pending confirmation |
| Candidate vLLM allocation | 0.40, unvalidated |
| Tested/adopted vLLM allocation and reason | Pending |
| Other GPU processes present | Pending |
| Browser, audio device, headphones/speakers | Pending |
| Warmup completion and first-turn treatment | Pending |
| Test duration / completed turns / interruptions | Pending |

For each metric, record the count, median, p95, maximum, unit and source file.
Use comparable repeated cases and separate cold/warm measurements.

| Metric | Result | Source / limitation |
| --- | --- | --- |
| Endpointing after last input frame | Pending | `replay_stt.py` output; independent recorder replay with stack stopped |
| User-marked endpoint to finalized STT | Pending | Browser trace; manual timing error included |
| Atlas first spoken text, sequential / overlapping TTS | Pending | Service probes; adapter-filtered first text, not raw tokenizer TTFT |
| SILMA first PCM, sequential / overlapping Atlas | Pending | Service probes; entire phrase is synthesized before PCM becomes available |
| SILMA synthesis time / real-time factor / phrase length | Pending | Service probes and saved WAVs |
| User-marked endpoint to browser render start | Pending | Trace; not a physical speaker measurement |
| Within-response rendering gaps | Pending | Trace; intentional turn boundaries excluded |
| User-marked interruption to render stop | Pending | Trace; not physical acoustic cancellation latency |
| Physical first-audible / interruption latency | Pending | Record an acoustic loopback test, or explicitly leave unmeasured |
| Peak device memory / minimum free memory | Pending | GPU JSONL; sampled every 0.5s, short peaks may be missed |
| Warmed idle memory before / after sustained test | Pending | Compare equivalent resident/idle states, not cold vs warm totals |
| English-to-Darija latency difference | Unmeasured | User accepted English behavior; no fresh English baseline was collected |

Human acceptance (record evidence/failures, not only check marks):

- Correct native Darija recognition across complete, incomplete, hesitant and number-heavy utterances.
- Natural Darija-only replies when input includes French/English terms.
- Voice1/main intelligibility, negation, questions, foreign names, IDs and numbers.
- Ordered quick/final phrases with no repetition, truncated tail or wrong generation.
- Audible interruption before first audio, during playback and between phrases;
  immediate next turn succeeds and no canceled tail returns.
- Reset, disconnect/reconnect, runtime reuse and service failure recovery.
- Second session receives capacity feedback and does not create another GPU runtime.
- Sustained single-session run without OOM or unexplained warmed-idle memory growth.
- Speaker echo behavior with the intended audio hardware.

Adopted changes and evidence: **None yet**. Keep 32 TTS steps and current VAD/
dynamic endpointing until a reproducible case and paired before/after evidence
justify a change. Report remaining limitations and any failed acceptance checks.
