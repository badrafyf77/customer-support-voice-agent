"""Download exact snapshots and verify the previously exported Darija ASR."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from core.model_artifacts import LOCK_PATH, inspect_model_files, validate_prepared_models


def prepare(root: Path, asr_export: Path | None, roles: list[str] | None = None) -> None:
    from huggingface_hub import snapshot_download

    root = root.expanduser().resolve()
    if asr_export is not None:
        asr_export = asr_export.expanduser().resolve()
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    root.mkdir(parents=True, exist_ok=True)
    selected = roles or list(lock["models"])
    retained = {}
    receipt_path = root / "prepared.json"
    if receipt_path.is_file():
        old = json.loads(receipt_path.read_text(encoding="utf-8"))
        other_roles = [role for role in old.get("models", {}) if role not in selected]
        if other_roles:
            validate_prepared_models(root, roles=other_roles)
            retained = {role: old["models"][role] for role in other_roles}
    # Invalidate any earlier readiness receipt before changing artifacts.
    (root / "prepared.json").unlink(missing_ok=True)
    receipt = {"schema_version": 1, "models": retained}
    for role, spec in lock["models"].items():
        if role not in selected:
            continue
        print(f"Preparing {role}: {spec['repo_id']}@{spec['revision']}", flush=True)
        destination = root / spec["directory"]
        if role == "stt":
            if asr_export is None:
                raise ValueError("--asr-export is required when preparing STT.")
            # Check before copying, including the exact 1.6 GB model hash.
            inspect_model_files(asr_export.parent, {**spec, "directory": asr_export.name})
            if asr_export != destination:
                destination.mkdir(parents=True, exist_ok=True)
                for name in spec["files"]:
                    shutil.copy2(asr_export / name, destination / name)
        else:
            try:
                # HF_TOKEN is read by huggingface_hub, never put in CLI arguments.
                snapshot_download(
                    spec["repo_id"], revision=spec["revision"],
                    local_dir=destination, allow_patterns=list(spec["files"]),
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Cannot retrieve {spec['repo_id']}@{spec['revision']}. "
                    "Check connectivity and HF_TOKEN access to the private repository."
                ) from None
        receipt["models"][role] = {
            "repo_id": spec["repo_id"], "revision": spec["revision"],
            "files": inspect_model_files(root, spec),
        }
    temporary = root / "prepared.json.tmp"
    temporary.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    temporary.replace(root / "prepared.json")
    validate_prepared_models(root, roles=list(receipt["models"]))
    print(f"Prepared pinned roles {', '.join(receipt['models'])}: {root / 'prepared.json'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--asr-export", type=Path, help="Correct Modal CTranslate2 export")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--roles", nargs="+", choices=["stt", "turn", "llm", "tts", "vocoder"],
                        help="Prepare a subset; default is all models")
    args = parser.parse_args()
    try:
        if args.verify_only:
            for role, spec in validate_prepared_models(args.root, roles=args.roles).items():
                print(f"{role}: {spec['repo_id']}@{spec['revision']} verified")
        else:
            if args.asr_export is None and (args.roles is None or "stt" in args.roles):
                parser.error("--asr-export is required unless --verify-only is used")
            prepare(args.root, args.asr_export, args.roles)
    except (RuntimeError, OSError, ValueError) as exc:
        parser.exit(1, f"Model preparation failed: {exc}\n")


if __name__ == "__main__":
    main()
