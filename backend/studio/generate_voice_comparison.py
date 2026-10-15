"""Generate fresh paired main/EMA speech through the new cached inference runtime."""
import argparse
import gc
import json
from pathlib import Path
import sys
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from core.nodes.tts.silma_runtime import SilmaRuntime
from core.nodes.tts.silma_text import iter_phrases
from voice_review import build_page

CASES = {
    "greetings": "سلام، كيفاش نقدر نعاونك اليوم؟",
    "questions": "فين ساكن دابا، وفاش بغيتي يجي عندك الطلب؟",
    "negation": "ماعرفتش علاش ماخدامش، ولكن غادي نشوف ليك الحل دابا.",
    "names": "يوسف وSalma، الطلب ديالكم واجد.",
    "numbers": "الطلب رقم 1234، والثمن هو 250 درهم.",
    "longer replies": "واخا، غادي نراجع معاك المعلومات ديال الطلب. عافاك عطيني السمية ديالك ورقم الطلب، وغادي نشوف فين وصل دابا. إلا كانت شي حاجة ناقصة، غادي نشرح ليك شنو خاصنا باش نكملو الطلب.",
}


def generate(root: Path, output: Path):
    import torch
    output.mkdir(parents=True, exist_ok=True)
    samples = []
    for voice_id in ("voice0", "voice1"):
        for variant in ("ema", "main"):
            runtime = SilmaRuntime(root, voice_id=voice_id, variant=variant)
            for number, (category, text) in enumerate(CASES.items()):
                chunks = []
                for index, phrase in enumerate(iter_phrases(text.splitlines(keepends=True),
                                                           max_bytes=min(400, runtime.max_phrase_bytes))):
                    torch.manual_seed(20261013 + number * 100 + index)
                    torch.cuda.manual_seed_all(20261013 + number * 100 + index)
                    chunks.append(runtime.synthesize(phrase))
                filename = f"{voice_id}-{variant}-{number}.wav"
                with wave.open(str(output / filename), "wb") as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(24000)
                    audio.writeframes(b"".join(chunks))
                samples.append({"category": category, "text": text, "voice_id": voice_id,
                                "variant": variant, "audio": filename, "metadata": runtime.metadata})
            del runtime
            gc.collect()
            torch.cuda.empty_cache()
    (output / "samples.json").write_text(json.dumps(samples, ensure_ascii=False, indent=2) + "\n")
    build_page(output, samples, "Fresh service-runtime inference at 32 steps, CFG 2, sway -1. "
               "Reference-rate duration estimates and paired seeds. Review all four choices.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.root.expanduser().resolve(), args.output)
