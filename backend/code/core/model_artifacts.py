"""Offline artifact checks, shared by Studio preparation and app startup."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


LOCK_PATH = Path(__file__).resolve().parents[2] / "studio" / "models.lock.json"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_model_files(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    directory = root / spec["directory"]
    result = {}
    for name, expected in spec["files"].items():
        path = directory / name
        if not path.is_file():
            raise RuntimeError(
                f"Missing {spec['repo_id']}@{spec['revision']}: {path}. "
                "Run backend/studio/prepare_models.py with private-model access."
            )
        size = path.stat().st_size
        digest = file_sha256(path)
        if expected.get("bytes", size) != size or expected.get("sha256", digest) != digest:
            raise RuntimeError(
                f"Artifact provenance mismatch: {spec['repo_id']} / {name}. "
                "Retrieve the pinned artifact; the 125h ASR export is not accepted."
            )
        result[name] = {"bytes": size, "sha256": digest}
    return result


def validate_prepared_models(
    model_root: str | Path, lock_path: Path = LOCK_PATH, roles: list[str] | None = None,
) -> dict[str, Any]:
    root = Path(model_root).expanduser().resolve()
    receipt_path = root / "prepared.json"
    if not receipt_path.is_file():
        raise RuntimeError(
            f"Missing model preparation receipt: {receipt_path}. "
            "Run backend/studio/prepare_models.py; no fallback models will be loaded."
        )
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if roles is not None and set(roles) - set(lock["models"]):
        raise ValueError("Unknown model role requested for validation.")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    verified = {}
    for role, spec in lock["models"].items():
        if roles is not None and role not in roles:
            continue
        record = receipt.get("models", {}).get(role, {})
        if record.get("repo_id") != spec["repo_id"] or record.get("revision") != spec["revision"]:
            raise RuntimeError(f"Incorrect prepared model identity or revision for {role}.")
        hashes = inspect_model_files(root, spec)
        if hashes != record.get("files"):
            raise RuntimeError(f"Prepared artifact changed since download: {role}.")
        verified[role] = {**spec, "path": str(root / spec["directory"])}
    return verified
