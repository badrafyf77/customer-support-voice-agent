"""Container-local readiness checks without loading model weights again."""
import json
import sys
from urllib.request import urlopen


def check(role):
    port = {"vllm": 8001, "silma": 8002, "backend": 8080}[role]
    route = "/" if role == "backend" else "/health"
    with urlopen(f"http://127.0.0.1:{port}{route}", timeout=3) as response:
        if response.status != 200:
            raise RuntimeError("Service is not ready")
        if role == "vllm":
            return
        data = json.load(response)
    if role == "silma":
        if not data.get("ready"):
            raise RuntimeError("SILMA is not ready")
    elif (data.get("status"), data.get("voice_profile")) != ("ok", "darija"):
        raise RuntimeError("Expected the ready Darija backend")


if __name__ == "__main__":
    check(sys.argv[1])
