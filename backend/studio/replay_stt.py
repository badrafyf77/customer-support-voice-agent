"""Deferred real-recorder Darija replay: verified ASR + calibrated dynamic pauses.

Manifest: JSON list of {name, wav, expected_text?, expected_complete?}. WAV paths
are relative to the manifest; audio must be mono 16 kHz PCM16 (the existing
browser transport's output format). No LLM/TTS or fixed endpoint schedule is used.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import threading
import time
import wave

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"code"))
from core.model_artifacts import validate_prepared_models
from core.nodes.stt.configuration import darija_recorder_config


def read_audio(path):
    with wave.open(str(path),'rb') as stream:
        if (stream.getframerate(),stream.getnchannels(),stream.getsampwidth(),stream.getcomptype())!=(16000,1,2,'NONE'):
            raise ValueError(f'{path}: expected mono 16 kHz PCM16 WAV')
        return stream.readframes(stream.getnframes())


def replay_case(case,manifest_dir,models,pipeline_latency,tail_seconds):
    from core.nodes.stt.faster_whisper import DEFAULT_RECORDER_CONFIG, FasterWhisperSTTProvider
    pcm=read_audio(manifest_dir/case['wav'])
    if not pcm:
        raise ValueError('Replay audio is empty')
    events,lock=[],threading.Lock()
    started=time.monotonic()
    def record(kind,**data):
        with lock:
            events.append({'type':kind,'seconds':time.monotonic()-started,**data})
    provider=FasterWhisperSTTProvider(
        'ar',profile='darija',turn_model_path=models['turn']['path'],
        recorder_config=darija_recorder_config(DEFAULT_RECORDER_CONFIG,models['stt']['path']),
        pipeline_latency=pipeline_latency,
        realtime_transcription_callback=lambda text:record('partial',text=text),
        full_transcription_callback=lambda text:record('final',text=text),
        potential_sentence_end=lambda text:record('potential_sentence',text=text),
        potential_full_transcription_callback=lambda text:record('potential_final',text=text),
        silence_active_callback=lambda active:record('vad_silence',active=active),
    )
    stop=threading.Event()
    original_waiting=provider.turn_detection.on_new_waiting_time
    def waiting(pause,text):
        original_waiting(pause,text)
        score=provider.turn_detection.last_decision
        record('turn_score',text=text,pause=pause,decision=score.diagnostics() if score else None)
    provider.turn_detection.on_new_waiting_time=waiting
    def transcribe():
        while not stop.is_set():
            try:
                provider.transcribe_loop()
            except Exception as exc:
                if not stop.is_set():
                    record('error',message=str(exc))
                return
    worker=threading.Thread(target=transcribe,daemon=True,name='ReplayFinalTranscriber')
    worker.start()
    # Feed the same 16 kHz PCM that follows browser resampling, in real time.
    def feed(data):
        for offset in range(0,len(data),1024):
            packet=data[offset:offset+1024]
            before=time.monotonic()
            provider.feed_audio(packet)
            time.sleep(max(0,len(packet)/32000-(time.monotonic()-before)))
    try:
        started=time.monotonic()
        feed(bytes(8000))  # 250 ms of input silence, not a runtime endpoint rule.
        feed(pcm)
        last_input=time.monotonic()-started
        record('input_end')
        feed(bytes(round(tail_seconds*32000)))
        with lock:
            snapshot=deepcopy(events)
        finals=[event for event in snapshot if event['type']=='final']
        return {**case,'events':snapshot,'input_end_seconds':last_input,
                'final_count':len(finals),
                'final_delay_after_last_input_frame':None if not finals else finals[-1]['seconds']-last_input,
                'early_finals_before_input_end':sum(event['seconds']<last_input for event in finals),
                'manual_review_required':True}
    finally:
        stop.set()
        provider.shutdown()
        worker.join(timeout=5)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    parser.add_argument('--manifest',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--pipeline-latency',type=float,default=0.5)
    parser.add_argument('--tail-seconds',type=float,default=8)
    args=parser.parse_args()
    if args.pipeline_latency<0 or not 1<=args.tail_seconds<=30:
        parser.error('Use nonnegative pipeline latency and 1–30 seconds of replay tail silence')
    models=validate_prepared_models(args.root,roles=['stt','turn'])
    cases=json.loads(args.manifest.read_text())
    report={'models':{role:{'repo_id':spec['repo_id'],'revision':spec['revision']} for role,spec in models.items()},
            'pipeline_latency':args.pipeline_latency,'timing':'existing dynamic pause and latency floor',
            'cases':[],'audible_playback_tested':False}
    try:
        for case in cases:
            report['cases'].append(replay_case(case,args.manifest.resolve().parent,models,
                                               args.pipeline_latency,args.tail_seconds))
    finally:
        args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(f'Saved {args.output}; review transcripts, scores and early/late final events.')


if __name__=='__main__':
    main()
