"""Local test app: actual session/runtime/pipeline; deterministic STT, LLM and PCM.

The source bodies are compiled without GPU/auth imports. No alternative session
implementation or production test route is installed. Run only on loopback.
"""
from __future__ import annotations
import ast
import asyncio
import anyio
import base64
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
import json
import logging
from pathlib import Path
from queue import Empty
import re
import struct
import sys
import threading
import time
from types import SimpleNamespace
from typing import Any, Optional, Deque
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'code'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from agents.chat.agent import build_chat_agent, DARIJA_SYSTEM_PROMPT
from core.colors import Colors
from core.models import AgentResult, SessionContext, conversation_message
from core.pipeline import SpeechPipelineManager, _strip_control_leak
from test_atlas import make_llm, Stream

CODE=Path(__file__).resolve().parents[2]/'code'


def load_session():
    names={'log_event','parse_json_message','format_timestamp_ns','_build_session_context','_run_agent_turn',
           'trigger_orchestrated_exam_turn','trigger_exam_finish','process_incoming_data','send_text_messages',
           '_reset_interrupt_flag_async','send_tts_chunks','TranscriptionCallbacks','run_session'}
    source=ast.parse((CODE/'core/session.py').read_text())
    selected=[node for node in source.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and node.name in names]
    namespace={**globals(),'logger':logging.getLogger('session-test'),'_conversation_message':conversation_message,
               'MAX_AUDIO_QUEUE_SIZE':50,'TTS_FINAL_TIMEOUT':1,'VoiceRuntimeCapacityError':RuntimeError}
    async def no_verification(*args):
        return None
    namespace['_build_voice_verification_manager']=no_verification
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(CODE/'core/session.py'),'exec'),namespace)
    return SimpleNamespace(**namespace)


class Audio:
    tts_inference_time=1
    def __init__(self):
        self.on_first_audio_chunk_synthesize=None
        self.metadata={'voice_id':'voice1','variant':'main'}
        self.spoken=[]
        self.started=threading.Event()
        self.release=threading.Event();self.release.set()
        self.cancelled=threading.Event()
        self.cancelled_generations=set()
        self.last_generation=None
        self.pcm=b'\x10\x00\xf0\xff'*2400
    def synthesize(self,text,queue,stop,generation_string=''):
        self.last_generation=generation_string
        self.started.set()
        while not self.release.wait(.005):
            if stop.is_set() or generation_string in self.cancelled_generations:return False
        if stop.is_set() or generation_string in self.cancelled_generations:return False
        self.spoken.append(text)
        queue.put(self.pcm)
        if self.on_first_audio_chunk_synthesize:self.on_first_audio_chunk_synthesize()
        return True
    def synthesize_generator(self,chunks,queue,stop,generation_string=''):
        for text in chunks:
            if text.strip() and not self.synthesize(text,queue,stop,generation_string):return False
        return not stop.is_set()
    def stop_playback(self):
        self.cancelled.set()
        if self.last_generation:self.cancelled_generations.add(self.last_generation)
    def reset_session_state(self):self.cancelled.clear();self.cancelled_generations.clear()
    def shutdown(self):self.cancelled.set();self.release.set()


class Input:
    instances=[]
    def __init__(self,*args,**kwargs):
        self.interrupted=False
        self.realtime_callback=None
        self.recording_start_callback=None
        self.silence_active_callback=None
        self.packets=[]
        self.transcriber=SimpleNamespace(reset_session_state=self.clear_transcriber,
                                         get_last_audio_copy=lambda:None)
        self.clear_transcriber(clear_callbacks=True)
        self.instances.append(self)
    def clear_transcriber(self,clear_callbacks=False):
        if not clear_callbacks:return
        for name in ('potential_sentence_end','on_tts_allowed_to_synthesize','potential_full_transcription_callback',
                     'potential_full_transcription_abort_callback','full_transcription_callback','before_final_sentence'):
            setattr(self.transcriber,name,None)
    def abort_generation(self):pass
    def reset_session_state(self,clear_callbacks=False):
        self.interrupted=False
        self.clear_transcriber(clear_callbacks=True)
        self.realtime_callback=None;self.recording_start_callback=None;self.silence_active_callback=None
    def shutdown(self):pass
    async def process_chunk_queue(self,queue):
        while True:
            packet=await queue.get()
            self.packets.append(packet)
    def user_turn(self,text,partial=None,final_only=False):
        if self.recording_start_callback:self.recording_start_callback()
        if self.realtime_callback and not final_only:self.realtime_callback(partial or text)
        if self.transcriber.before_final_sentence:self.transcriber.before_final_sentence(None,partial or text)
        if self.transcriber.full_transcription_callback:self.transcriber.full_transcription_callback(text)


class Harness:
    def __init__(self):
        self.session=load_session()
        self.streams=[]
        self.requests=[]
        self.inputs=[]
        self.pipeline=None
        self.next_chunks=['سلام Sara، الطلب AB-1203 واجد. ','الثمن 12.50 درهم.']
        self.block_stream=False
        self.fail=False
        self.audio=Audio()
        self.llm,self.create=make_llm(None,create=self.request)
        self.manager=self.make_manager()
    def request(self,**kwargs):
        self.requests.append(kwargs)
        if self.fail:raise RuntimeError('Fake model service unavailable')
        stream=Stream(self.next_chunks,pause_after_first=self.block_stream)
        self.streams.append(stream)
        return stream
    def make_manager(self):
        def pipeline_factory(**config):
            with patch('core.pipeline.LLM',return_value=self.llm),patch('core.pipeline.create_tts_provider',return_value=self.audio):
                self.pipeline=SpeechPipelineManager(tts_engine='silma',llm_model='MBZUAI-Paris/Atlas-Chat-2B',
                                                    system_prompt=DARIJA_SYSTEM_PROMPT,skip_prewarm=True)
            return self.pipeline
        source=ast.parse((CODE/'core/voice_runtime_pool.py').read_text())
        classes=[node for node in source.body if isinstance(node,ast.ClassDef)]
        namespace={**globals(),'logger':logging.getLogger('runtime-test'),'SpeechPipelineManager':pipeline_factory,'AudioInputProcessor':Input}
        exec(compile(ast.Module(body=classes,type_ignores=[]),str(CODE/'core/voice_runtime_pool.py'),'exec'),namespace)
        self.session.VoiceRuntimeCapacityError=namespace['VoiceRuntimeCapacityError']
        # The executed functions share their original namespace.
        self.session.run_session.__globals__['VoiceRuntimeCapacityError']=namespace['VoiceRuntimeCapacityError']
        return namespace['VoiceRuntimeManager'](1,1,300,{},'ar','silma')
    def create_app(self):
        @asynccontextmanager
        async def lifespan(app):
            await self.manager.startup()
            yield
            await self.manager.shutdown()
        app=FastAPI(lifespan=lifespan)
        @app.websocket('/ws')
        async def websocket(ws:WebSocket):
            brain,_=build_chat_agent({'profile':'darija'})
            state=SimpleNamespace(RUNTIME_MANAGER=self.manager,RUNTIME_ACQUIRE_TIMEOUT_SECONDS=.1,VOICE_PROFILE='darija',
                                  Upsampler=SimpleNamespace(get_base64_chunk=lambda pcm:base64.b64encode(pcm).decode()))
            await self.session.run_session(ws,brain,{'agent_name':'chat'},state)
        @app.post('/test/turn')
        async def turn(payload:dict):
            runtime=next(iter(self.manager._runtimes.values()))
            await asyncio.to_thread(runtime.audio_processor.user_turn,payload['text'],payload.get('partial'),payload.get('final_only',False))
            return {'ok':True}
        @app.post('/test/config')
        async def configure(payload:dict):
            self.fail=bool(payload.get('fail',False))
            self.block_stream=bool(payload.get('block_stream',False))
            if 'chunks' in payload:self.next_chunks=payload['chunks']
            if payload.get('release'):
                for stream in self.streams:stream.release.set()
                self.audio.release.set()
            if payload.get('block_audio'):self.audio.started.clear();self.audio.release.clear()
            return {'ok':True}
        @app.get('/test/state')
        async def state():
            return {'requests':self.requests,'spoken':self.audio.spoken,'available':self.manager.available_count,
                    'packets':sum(len(r.audio_processor.packets) for r in self.manager._runtimes.values())}
        return app


harness=Harness()
app=harness.create_app()
