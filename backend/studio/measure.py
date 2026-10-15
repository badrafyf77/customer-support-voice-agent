"""Studio measurement tools; never infer live acceptance from synthetic checks."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from urllib.request import Request, urlopen
import uuid
import wave

STUDIO = Path(__file__).resolve().parent


def distribution(values):
    values = sorted(value for value in values if value is not None)
    if not values:
        return {"count": 0, "p50": None, "p95": None, "max": None}
    return {"count": len(values), "p50": values[math.ceil(.5 * len(values)) - 1],
            "p95": values[math.ceil(.95 * len(values)) - 1], "max": values[-1]}


def gpu_sample():
    output = subprocess.check_output([
        "nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu",
        "--format=csv,noheader,nounits",
    ], text=True, timeout=10)
    devices = []
    for row in output.strip().splitlines():
        index, name, total, used, free, utilization = (part.strip() for part in row.split(","))
        devices.append({"index": int(index), "name": name, "total_mib": float(total),
                        "used_mib": float(used), "free_mib": float(free),
                        "utilization_percent": float(utilization)})
    if not devices:
        raise RuntimeError("nvidia-smi returned no devices")
    return {"utc": datetime.now(timezone.utc).isoformat(),
            "monotonic_seconds": time.monotonic(), "devices": devices}


def monitor(args):
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        while not stop.is_set():
            stream.write(json.dumps(gpu_sample()) + "\n")
            stream.flush()
            stop.wait(args.interval)


def fetch_json(url):
    with urlopen(url, timeout=10) as response:
        return json.load(response)


def tts_probe(base, text, destination):
    generation = "benchmark-" + uuid.uuid4().hex
    request = Request(base + "/synthesize", method="POST",
                      data=json.dumps({"generation_id": generation, "text": text}).encode(),
                      headers={"Content-Type": "application/json"})
    started = time.perf_counter()
    with urlopen(request, timeout=120) as response:
        first = response.read(2)
        first_ms = (time.perf_counter() - started) * 1000
        pcm = first + response.read()
        headers = response.headers
    total_ms = (time.perf_counter() - started) * 1000
    if (headers.get("X-Sample-Rate") != "24000" or headers.get("X-Channels") != "1"
            or headers.get("X-Audio-Format") != "pcm_s16le" or not pcm or len(pcm) % 2):
        raise RuntimeError("Invalid SILMA benchmark response")
    with wave.open(str(destination), "wb") as output:
        output.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        output.writeframes(pcm)
    duration = len(pcm) / 48000
    return {"first_pcm_ms": first_ms, "total_ms": total_ms,
            "service_synthesis_ms": float(headers["X-Synthesis-Ms"]),
            "audio_seconds": duration, "real_time_factor": total_ms / 1000 / duration,
            "wav": destination.name}


def benchmark(args):
    # All three GPU stacks must already be resident. Do not open a browser
    # conversation while issuing these direct sequential/concurrent probes.
    sys.path.insert(0, str(STUDIO.parent / "code"))
    from agents.chat.agent import DARIJA_SYSTEM_PROMPT
    from services.llm import LLM
    from services.atlas import MODEL_ID
    backend = fetch_json("http://127.0.0.1:8080/")
    if (backend.get("status"), backend.get("voice_profile"), backend.get("runtime", {}).get("total"),
            backend.get("runtime", {}).get("busy")) != ("ok", "darija", 1, 0):
        raise RuntimeError("Start the warmed backend before combined-residency measurements")
    silma = os.environ.get("SILMA_TTS_BASE_URL", "http://127.0.0.1:8002").rstrip("/")
    health = fetch_json(silma + "/health")
    if (health.get("ready"), health.get("voice_id"), health.get("variant"), health.get("steps")) != (True, "voice1", "main", 32):
        raise RuntimeError("Establish voice1/main/32-step quality baseline before tuning")
    args.output.mkdir(parents=True, exist_ok=False)
    llm = LLM("vllm", MODEL_ID, system_prompt=DARIJA_SYSTEM_PROMPT,
              base_url=os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8001/v1"),
              chat_format="atlas", max_tokens=256, context_limit=4096)
    report = {"kind": "resident_stack_service_probes", "silma": health,
              "cases": [], "status": "running", "human_listening_review": "pending",
              "end_to_end_browser_acceptance": "pending"}
    phrases = ["سلام، كيفاش نقدر نعاونك؟", "واخا Sara، الطلب AB-1203 واجد.",
               "إلى بغيتي تبدل الموعد، عطيني النهار والوقت اللي مناسب ليك ونشوفو شنو ممكن نديرو."]
    def atlas_probe():
        started, first, count = time.perf_counter(), None, 0
        generator = llm.generate("شرح ليا بالدارجة كيفاش ننظم الوقت ديالي فثلاثة نصائح قصيرة.", temperature=.3)
        try:
            for text in generator:
                if text.strip() and first is None:
                    first = (time.perf_counter() - started) * 1000
                count += 1
        finally:
            generator.close()
        if first is None:
            raise RuntimeError("Atlas returned no spoken text")
        return {"first_spoken_text_ms": first, "total_ms": (time.perf_counter() - started) * 1000,
                "chunks": count}
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            for repeat in range(args.repeats):
                for index, phrase in enumerate(phrases):
                    for overlap in (False, True):
                        name = f"r{repeat + 1}-phrase{index + 1}-{'overlap' if overlap else 'sequential'}"
                        entry = {"name": name, "overlap": overlap, "gpu_before": gpu_sample()}
                        if overlap:
                            future = executor.submit(atlas_probe)
                            entry["tts"] = tts_probe(silma, phrase, args.output / f"{name}.wav")
                            entry["atlas"] = future.result()
                        else:
                            entry["atlas"] = atlas_probe()
                            entry["tts"] = tts_probe(silma, phrase, args.output / f"{name}.wav")
                        entry["gpu_after"] = gpu_sample()
                        report["cases"].append(entry)
                        print(name, flush=True)
        report["status"] = "completed_probes_require_review"
    except Exception as exc:
        report["status"] = "failed"
        report["error_type"] = type(exc).__name__
        raise
    finally:
        llm.cancel_generation()
        (args.output / "services.json").write_text(json.dumps(report, indent=2) + "\n")


def browser_metrics(events):
    # Every duration uses one browser's performance clock; never subtract the
    # remote server's clock. Manual marks approximate acoustic user boundaries.
    result = {name: [] for name in ("marked_endpoint_to_final_stt_ms",
              "marked_endpoint_to_render_start_ms", "marked_interrupt_to_render_stop_ms",
              "render_gaps_ms", "first_pcm_to_render_start_ms")}
    endpoint = interrupt = first_pcm = stopped = None
    active = response_done = False
    for event in events:
        name, stamp = event["event"], event["browser_ms"]
        if name == "mark:utterance_end":
            endpoint = stamp
            stopped = None
        elif name == "mark:interrupt_start":
            interrupt = stamp
        elif name == "server:final_user_request":
            stopped = None
            response_done = False
            if endpoint is not None:
                result["marked_endpoint_to_final_stt_ms"].append(max(0, stamp - endpoint))
        elif name == "server:final_assistant_answer":
            response_done = True
            stopped = None
        elif name == "server:tts_chunk" and first_pcm is None and not active:
            first_pcm = stamp
        elif name == "playback:ttsPlaybackStarted":
            if not active and endpoint is not None:
                result["marked_endpoint_to_render_start_ms"].append(max(0, stamp - endpoint))
                endpoint = None
            if first_pcm is not None:
                result["first_pcm_to_render_start_ms"].append(max(0, stamp - first_pcm))
                first_pcm = None
            if stopped is not None:
                result["render_gaps_ms"].append(max(0, stamp - stopped))
                stopped = None
            active = True
        elif name == "playback:ttsPlaybackStopped":
            active = False
            stopped = None if response_done else stamp
            first_pcm = None
            if interrupt is not None:
                result["marked_interrupt_to_render_stop_ms"].append(max(0, stamp - interrupt))
                interrupt = None
        elif name in ("server:stop_tts", "server:tts_interruption", "client:clear_history", "socket:close"):
            first_pcm = None
            stopped = None
            response_done = True
    return {key: distribution(values) for key, values in result.items()}


def summarize(args):
    report = {"live_acceptance": "pending_human_review", "gpu": {}, "browser": {}, "services": {},
              "limits": ["GPU peak is a sampled device-wide peak; sub-interval spikes can be missed.",
                         "Render callbacks approximate playback; they do not measure physical speaker output.",
                         "Manual marks include human timing error. Phrase gaps exclude intentional turn boundaries.",
                         "No English latency comparison is available; identical latency is not established."]}
    if args.gpu:
        devices = {}
        for line in args.gpu.read_text().splitlines():
            if line.strip():
                for device in json.loads(line)["devices"]:
                    devices.setdefault(device["index"], []).append(device)
        for index, samples in devices.items():
            report["gpu"][index] = {"name": samples[0]["name"], "samples": len(samples),
                "peak_used_mib": max(s["used_mib"] for s in samples),
                "minimum_free_mib": min(s["free_mib"] for s in samples),
                "first_used_mib": samples[0]["used_mib"], "last_used_mib": samples[-1]["used_mib"]}
    if args.browser:
        data = json.loads(args.browser.read_text())
        report["browser"] = browser_metrics(data if isinstance(data, list) else data["events"])
    if args.services:
        data = json.loads(args.services.read_text())
        report["service_probe_status"] = data["status"]
        for overlap in (False, True):
            cases = [case for case in data["cases"] if case["overlap"] == overlap]
            report["services"]["overlap" if overlap else "sequential"] = {
                "atlas_first_spoken_text_ms": distribution([case["atlas"]["first_spoken_text_ms"] for case in cases]),
                "tts_first_pcm_ms": distribution([case["tts"]["first_pcm_ms"] for case in cases]),
                "tts_real_time_factor": distribution([case["tts"]["real_time_factor"] for case in cases])}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Saved {args.output}; complete the manual acceptance report before adopting settings.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("monitor")
    collect.add_argument("--output", type=Path, required=True)
    collect.add_argument("--interval", type=float, default=.5)
    probe = commands.add_parser("benchmark")
    probe.add_argument("--output", type=Path, required=True)
    probe.add_argument("--repeats", type=int, default=3)
    summary = commands.add_parser("report")
    for name in ("gpu", "browser", "services"):
        summary.add_argument("--" + name, type=Path)
    summary.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "monitor" and args.interval < .1:
        parser.error("--interval must be at least 0.1 seconds")
    if args.command == "benchmark" and args.repeats < 1:
        parser.error("--repeats must be positive")
    {"monitor": monitor, "benchmark": benchmark, "report": summarize}[args.command](args)


if __name__ == "__main__":
    main()
