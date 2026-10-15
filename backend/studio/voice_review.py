"""Build a local listening page from paired generated or existing samples."""
import html
import json
from pathlib import Path
import shutil
import wave


def build_page(output: Path, samples: list[dict], note: str):
    pairs = {}
    for sample in samples:
        pairs.setdefault((sample["category"], sample["text"]), {})[
            (sample["voice_id"], sample["variant"])
        ] = sample["audio"]
    body = "<h1>Choose the Darija assistant voice</h1><p>" + html.escape(note) + "</p>"
    body += "<p>Compare clarity, accent, missing words, names, and numbers. Choose a voice and main or EMA weights.</p>"
    for (category, sentence), options in pairs.items():
        body += "<section><h2>" + html.escape(category) + "</h2><p dir='auto'>" + html.escape(sentence) + "</p><div class='grid'>"
        for voice in ("voice0", "voice1"):
            for variant in ("ema", "main"):
                path = options.get((voice, variant))
                body += "<div><b>" + voice + " · " + variant.upper() + "</b>"
                if path:
                    body += "<audio controls preload='none' src='" + html.escape(path, quote=True) + "'></audio>"
                else:
                    body += "<p>Pending generation on Studio</p>"
                body += "</div>"
        body += "</div></section>"
    body += "<p>Selected by the user: voice1 + main weights. New Studio listening tests remain deferred.</p>"
    page = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Darija voice comparison</title>
<style>body{font:17px system-ui;max-width:1100px;margin:36px auto;padding:0 24px;background:#f6f3ec;color:#25392f}
section{background:white;border-radius:12px;margin:24px 0;padding:24px}h2{font-size:18px}
[dir=auto]{font-size:24px;line-height:1.7}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}
audio{display:block;width:100%;margin-top:12px}b{font-size:15px}@media(max-width:650px){.grid{grid-template-columns:1fr}}</style>
""" + body + """<script>document.addEventListener('play',event=>{
document.querySelectorAll('audio').forEach(audio=>{if(audio!==event.target)audio.pause()})},true)</script></html>"""
    output.mkdir(parents=True, exist_ok=True)
    (output / "index.html").write_text(page, encoding="utf-8")


def existing_review(source: Path, output: Path):
    report = json.loads((source / "COMPLETE.json").read_text(encoding="utf-8"))
    categories = {"support_greeting", "question_words", "darija_negation", "spoken_numbers", "heldout_actual_1"}
    samples = []
    output.mkdir(parents=True, exist_ok=True)
    for row in report["samples"]:
        if row["category"] not in categories or row["variant"] not in {"pilot_main", "pilot_ema"}:
            continue
        voice = "voice0" if row["reference_group"] == "val_seen" else "voice1"
        variant = "main" if row["variant"] == "pilot_main" else "ema"
        name = row["audio_file"]
        if Path(name).name != name:
            raise ValueError("Unexpected sample filename")
        with wave.open(str(source / name)) as audio:
            if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (24000, 1, 2):
                raise ValueError("Listening sample must be mono 24 kHz PCM16")
        shutil.copyfile(source / name, output / name)
        samples.append({"category": row["category"], "text": row["target_text"],
                        "voice_id": voice, "variant": variant, "audio": name})
    samples.extend([
        {"category": "names — new test", "text": "يوسف وSalma، الطلب ديالكم واجد.",
         "voice_id": "voice0", "variant": "ema", "audio": None},
        {"category": "digit identifiers — new test", "text": "الطلب رقم 1234 غادي يوصل غدا.",
         "voice_id": "voice0", "variant": "ema", "audio": None},
    ])
    note = ("Existing final 25,000-update evaluation samples, same sentences/references/seeds "
            "across main and EMA. These were generated before this integration and use the "
            "previous evaluation's duration settings. New names/digit tests await Studio. "
            "This page does not claim the new service has passed a listening test.")
    build_page(output, samples, note)
    (output / "samples.json").write_text(json.dumps(samples, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    existing_review(args.existing, args.output)
    print(args.output.resolve() / "index.html")
