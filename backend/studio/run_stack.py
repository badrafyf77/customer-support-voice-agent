"""Foreground Studio supervisor. Ctrl-C stops only the processes it created."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

STUDIO = Path(__file__).resolve().parent


def wait_ready(process, url, timeout, companions=()):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Service exited with code {process.returncode}: {url}")
        if any(child.poll() is not None for child in companions):
            raise RuntimeError("An earlier service or GPU monitor exited; inspect logs")
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (URLError, OSError):
            pass
        time.sleep(1)
    raise RuntimeError(f"Readiness timeout: {url}")


def stop_children(children, grace=30):
    # Signal process groups: vLLM/RealtimeSTT also create worker processes.
    for child in reversed(children):
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + grace
    # Wait/reap direct children before probing residual worker groups. In
    # particular, do not race killpg(..., 0) against a terminating parent.
    for child in reversed(children):
        try:
            child.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    pending = list(children)
    while pending and time.monotonic() < deadline:
        for child in list(pending):
            child.poll()  # Reap an exited parent before testing its group.
            try:
                os.killpg(child.pid, 0)
            except ProcessLookupError:
                pending.remove(child)
            except PermissionError:
                # Some hosts report EPERM while an exited child is being
                # reaped. Never signal an inaccessible group after its parent
                # is gone; an active owned child still requires a real error.
                if child.poll() is not None:
                    pending.remove(child)
                else:
                    raise
        if pending:
            time.sleep(.1)
    for child in pending:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for child in children:
        child.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="New directory for service logs, GPU samples and run metadata")
    parser.add_argument("--startup-timeout", type=float, default=1200)
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("Run this supervisor on the Linux NVIDIA Studio")
    if os.environ.get("VOICE_PROFILE") != "darija" or os.environ.get("VOICE_AGENT") != "chat":
        parser.error("Source backend/.env.studio first (VOICE_AGENT=chat, VOICE_PROFILE=darija)")
    for name in ("DARIJA_STATE_ROOT", "DARIJA_MODEL_ROOT"):
        if not os.environ.get(name):
            parser.error(f"Set {name} before launching")
    if (os.environ.get("SILMA_VOICE_ID", "voice1"), os.environ.get("SILMA_CHECKPOINT_VARIANT", "main")) != ("voice1", "main"):
        parser.error("This release uses the selected voice1 + main checkpoint")
    try:
        budget = float(os.environ.get("VLLM_GPU_MEMORY_UTILIZATION", "0"))
    except ValueError:
        parser.error("VLLM_GPU_MEMORY_UTILIZATION must be a number")
    if not 0 < budget < 1:
        parser.error("Set an explicit VLLM_GPU_MEMORY_UTILIZATION between 0 and 1")
    if any(os.environ.get(name, "1") != "1" for name in ("VOICE_RUNTIME_MIN_WARM", "VOICE_RUNTIME_MAX_CONCURRENT")):
        parser.error("This release requires one warmed runtime and one concurrent conversation")
    for port in (8001, 8002, 8080):
        with socket.socket() as check:
            if check.connect_ex(("127.0.0.1", port)) == 0:
                parser.error(f"Port {port} is already in use; stop that service before launching")
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    state = Path(os.environ["DARIJA_STATE_ROOT"])
    metadata = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=STUDIO, text=True).strip(),
        "vllm_gpu_memory_utilization": budget,
        "budget_status": "candidate_requires_combined_load_and_listening_review",
        "voice": "voice1", "variant": "main", "steps": 32,
        "live_acceptance": "pending", "status": "starting",
    }
    # No environment dump: runtime secrets must never be copied into reports.
    (args.output / "models.lock.json").write_bytes((STUDIO / "models.lock.json").read_bytes())
    children, logs = [], []
    def launch(command, name):
        log = (args.output / f"{name}.log").open("wb")
        logs.append(log)
        child = subprocess.Popen(command, cwd=STUDIO.parents[1], stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        children.append(child)
        return child
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    result = 0
    try:
        launch([str(state / "backend/bin/python"), str(STUDIO / "measure.py"), "monitor",
                "--output", str(args.output / "gpu.jsonl")], "monitor")
        # vLLM profiles memory before the other GPU stacks load. Budget is a
        # fraction of total device memory, so it must leave measured headroom.
        for name, url in (("vllm", "http://127.0.0.1:8001/health"),
                          ("silma", "http://127.0.0.1:8002/health"),
                          ("backend", "http://127.0.0.1:8080/")):
            print(f"Starting {name}; logs: {args.output / (name + '.log')}", flush=True)
            child = launch(["bash", str(STUDIO / f"start_{name}.sh")], name)
            wait_ready(child, url, args.startup_timeout, children[:-1])
            if any(other.poll() is not None for other in children):
                raise RuntimeError("An earlier service or GPU monitor exited; inspect logs")
        metadata["status"] = "ready"
        (args.output / "run.json").write_text(json.dumps(metadata, indent=2) + "\n")
        print("All services ready. Connect the local SSH tunnel. Ctrl-C stops this stack.", flush=True)
        while True:
            if any(child.poll() is not None for child in children):
                raise RuntimeError("A service or GPU monitor exited; inspect logs")
            time.sleep(1)
    except KeyboardInterrupt:
        metadata["status"] = "stopped"
    except Exception as exc:
        metadata["status"] = "failed"
        metadata["error"] = str(exc)
        print(f"Stack failed: {exc}. Logs: {args.output}", file=sys.stderr)
        result = 1
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        stop_children(children)
        for log in logs:
            log.close()
        metadata["ended_utc"] = datetime.now(timezone.utc).isoformat()
        (args.output / "run.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return result


if __name__ == "__main__":
    sys.exit(main())
