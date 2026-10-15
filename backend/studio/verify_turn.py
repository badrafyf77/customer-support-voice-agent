"""Verify pinned Darija tokenizer/configuration offline, without loading weights."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"code"))
from core.darija_turn import validate_model_config, MAX_LENGTH, TEMPERATURE, THRESHOLD
from core.model_artifacts import LOCK_PATH


def verify(directory):
    from transformers import AutoTokenizer
    directory=Path(directory)
    spec=json.loads(LOCK_PATH.read_text())["models"]["turn"]
    for name, expected in spec["files"].items():
        if name=="model.safetensors":
            continue
        if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=expected["sha256"]:
            raise ValueError(f"Darija tokenizer/config hash mismatch: {name}")
    config=json.loads((directory/'config.json').read_text())
    validate_model_config(SimpleNamespace(**config))
    tokenizer=AutoTokenizer.from_pretrained(directory,local_files_only=True,trust_remote_code=False)
    tokenizer.truncation_side='left'
    text=' '.join(f'الطلب {number}' for number in range(100))+' Sara 0612345678'
    full=tokenizer(text,add_special_tokens=False)['input_ids']
    special=tokenizer.num_special_tokens_to_add(pair=False)
    expected=tokenizer.build_inputs_with_special_tokens(full[-(MAX_LENGTH-special):])
    actual=tokenizer(text,truncation=True,max_length=MAX_LENGTH)['input_ids']
    if actual!=expected or len(actual)!=MAX_LENGTH:
        raise ValueError('Darija turn tokenizer must retain the last 128 tokens including special tokens')
    return {"model_id":spec["repo_id"],"revision":spec["revision"],
            "metadata_hashes_verified":True,"normalization":config['turn_detection_normalization'],
            "policy":config['turn_detection_policy'],"temperature":TEMPERATURE,"threshold":THRESHOLD,
            "truncation_side":'left',"last_128_tokens_verified":True,"weights_loaded":False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir',required=True)
    parser.add_argument('--output')
    args=parser.parse_args()
    result=verify(args.model_dir)
    report=json.dumps(result,indent=2,ensure_ascii=False)+'\n'
    if args.output:
        Path(args.output).write_text(report)
    print(report)
