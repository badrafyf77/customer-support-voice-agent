"""Actual /ws session, lease and pipeline tests with deterministic model boundaries."""
import asyncio
import faulthandler
import struct
import sys
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import Mock

from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parent/'support'))
from session_harness import Harness


def ready(ws):
    while True:
        event=ws.receive_json()
        if event['type']=='status' and event['status']=='ready':return


def until(ws,kind):
    events=[]
    while True:
        event=ws.receive_json();events.append(event)
        if event['type']==kind:return events


class SessionTests(unittest.TestCase):
    def test_second_session_gets_capacity_without_another_runtime(self):
        harness=Harness()
        with TestClient(harness.create_app()) as client:
            with client.websocket_connect('/ws') as first:
                ready(first)
                with client.websocket_connect('/ws') as second:
                    events=[]
                    while True:
                        event=second.receive_json();events.append(event)
                        if event.get('status')=='busy':break
                    self.assertIn('capacity',events[-1]['message'])
                    self.assertEqual(harness.manager.total_count,1)
                    self.assertEqual(harness.manager.busy_count,1)
                client.post('/test/turn',json={'text':'واش باقي كتسمعني؟'})
                self.assertTrue(until(first,'final_assistant_answer'))

    def setUp(self):
        faulthandler.dump_traceback_later(25,exit=True)
        self.addCleanup(faulthandler.cancel_dump_traceback_later)

    def test_final_stt_is_used_and_quick_tail_transcript_and_pcm_stay_ordered(self):
        harness=Harness()
        with TestClient(harness.create_app()) as client:
            with client.websocket_connect('/ws') as ws:
                ready(ws)
                ws.send_bytes(struct.pack('!II',1234,1)+bytes(4096))
                client.post('/test/turn',json={'text':'Sara، الطلب AB-1203 والثمن 12.50', 'partial':'نص مؤقت'})
                events=until(ws,'final_assistant_answer')
                user=next(e for e in events if e['type']=='final_user_request')
                self.assertEqual(user['content'],'Sara، الطلب AB-1203 والثمن 12.50')
                final=events[-1]
                self.assertEqual(final['content'],'سلام Sara، الطلب AB-1203 واجد. الثمن 12.50 درهم.')
                chunks=[e for e in events if e['type']=='tts_chunk']
                self.assertGreaterEqual(len(chunks),2)
                self.assertTrue(all(e['generation_id']==final['generation_id'] for e in chunks))
                self.assertEqual(harness.requests[0]['messages'][0]['role'],'user')
                self.assertIn('Sara، الطلب AB-1203 والثمن 12.50',harness.requests[0]['messages'][0]['content'])
                self.assertNotIn('نص مؤقت',harness.requests[0]['messages'][0]['content'])
                runtime=next(iter(harness.manager._runtimes.values()))
                self.assertEqual(runtime.audio_processor.packets[0]['client_sent_ms'],1234)
                self.assertTrue(runtime.audio_processor.packets[0]['isTTSPlaying'])
                self.assertEqual(len(runtime.audio_processor.packets[0]['pcm']),4096)

    def test_interruption_during_synthesis_before_browser_playback(self):
        harness=Harness();harness.audio.release.clear()
        with TestClient(harness.create_app()) as client:
            with client.websocket_connect('/ws') as ws:
                ready(ws)
                client.post('/test/turn',json={'text':'السؤال الأول'})
                self.assertTrue(harness.audio.started.wait(1))
                # New VAD speech must interrupt even with no client tts_start.
                client.post('/test/turn',json={'text':'السؤال الثاني'})
                stopped=until(ws,'stop_tts')
                old_id=stopped[-1]['generation_id']
                harness.audio.cancelled.clear();harness.audio.release.set()
                events=until(ws,'final_assistant_answer')
                # A forced old transcript may precede the replacement final.
                if events[-1].get('generation_id')==old_id:
                    events+=until(ws,'final_assistant_answer')
                self.assertTrue(all(e['generation_id']>old_id for e in events if e['type']=='tts_chunk'))

    def test_error_is_visible_before_close_and_next_lease_has_clean_history(self):
        harness=Harness();harness.fail=True
        with TestClient(harness.create_app()) as client:
            with client.websocket_connect('/ws') as ws:
                ready(ws)
                old_callback=next(iter(harness.manager._runtimes.values())).audio_processor.transcriber.full_transcription_callback
                client.post('/test/turn',json={'text':'قديم AB-1203'})
                events=until(ws,'stop_tts')
                status=ws.receive_json()
                self.assertEqual((status['type'],status['status']),('status','error'))
            harness.fail=False;harness.audio.cancelled.clear()
            with client.websocket_connect('/ws') as ws:
                ready(ws)
                old_callback('نص من الجلسة القديمة')
                client.post('/test/turn',json={'text':'جلسة جديدة'})
                until(ws,'final_assistant_answer')
                messages=harness.requests[-1]['messages']
                self.assertEqual(len(messages),1)
                self.assertNotIn('قديم AB-1203',messages[0]['content'])
                self.assertNotIn('نص من الجلسة القديمة',messages[0]['content'])

    def test_clear_history_clears_the_session_transcript_and_stops_output(self):
        harness=Harness()
        with TestClient(harness.create_app()) as client:
            with client.websocket_connect('/ws') as ws:
                ready(ws)
                client.post('/test/turn',json={'text':'قديم'})
                until(ws,'final_assistant_answer')
                ws.send_json({'type':'clear_history'})
                until(ws,'stop_tts')
                harness.audio.cancelled.clear()
                client.post('/test/turn',json={'text':'جديد'})
                until(ws,'final_assistant_answer')
                self.assertEqual(len(harness.requests[-1]['messages']),1)
                self.assertNotIn('قديم',harness.requests[-1]['messages'][0]['content'])


    def test_playback_interruption_after_generation_finishes_still_scopes_stop(self):
        harness=Harness()
        with TestClient(harness.create_app()) as client:
            with client.websocket_connect('/ws') as ws:
                ready(ws)
                client.post('/test/turn',json={'text':'الأول'})
                old_id=until(ws,'final_assistant_answer')[-1]['generation_id']
                ws.send_json({'type':'tts_start'})
                callback=harness.pipeline.on_partial_assistant_text.__self__
                deadline=time.monotonic()+1
                while not callback.tts_client_playing and time.monotonic()<deadline:time.sleep(.005)
                self.assertTrue(callback.tts_client_playing)
                client.post('/test/turn',json={'text':'الثاني'})
                stopped=until(ws,'stop_tts')[-1]
                self.assertEqual(stopped['generation_id'],old_id)
                self.assertGreater(until(ws,'final_assistant_answer')[-1]['generation_id'],old_id)

    def test_final_only_recognition_is_committed_on_each_turn(self):
        harness=Harness()
        with TestClient(harness.create_app()) as client:
            with client.websocket_connect('/ws') as ws:
                ready(ws)
                for text in ('الأول Sara','الثاني 0612345678'):
                    client.post('/test/turn',json={'text':text,'final_only':True})
                    events=until(ws,'final_assistant_answer')
                    self.assertEqual(next(e for e in events if e['type']=='final_user_request')['content'],text)

    def test_reset_discards_a_prepare_request_created_before_cancellation(self):
        harness=Harness()
        with TestClient(harness.create_app()):
            pipeline=harness.pipeline
            old={'text':'قديم','_request_epoch':pipeline._request_epoch}
            pipeline.reset_session_state()
            pipeline.process_prepare_generation(old)
            self.assertIsNone(pipeline.running_generation)
            self.assertEqual(harness.requests,[])
            self.assertIsNone(pipeline.previous_request)

    def test_stopped_stt_worker_and_unstopped_speech_workers_are_retired(self):
        for failed in ('stt','speech'):
            harness=Harness()
            with TestClient(harness.create_app()) as client:
                with client.websocket_connect('/ws') as ws:
                    ready(ws)
                    runtime=next(iter(harness.manager._runtimes.values()))
                    old_id=runtime.runtime_id
                    if failed=='stt':runtime.audio_processor._transcription_failed=True
                    else:runtime.pipeline_manager._unsafe_to_reuse=True
                with client.websocket_connect('/ws') as ws:
                    ready(ws)
                    self.assertNotEqual(next(iter(harness.manager._runtimes)),old_id)
                    client.post('/test/turn',json={'text':'جديد'})
                    until(ws,'final_assistant_answer')


    def test_tts_and_midstream_llm_failure_clear_playback_without_final_success(self):
        from test_atlas import Stream, chunk
        for service in ('tts','midstream_llm'):
            harness=Harness()
            if service=='tts':
                def fail(*args,**kwargs):raise RuntimeError('Fake SILMA unavailable')
                harness.audio.synthesize=fail
            else:
                class BrokenStream(Stream):
                    def __iter__(self):
                        yield chunk('سلام Sara، كيفاش نعاونك؟ ')
                        raise RuntimeError('Fake Atlas disconnected midstream')
                harness.llm.client.chat.completions.create=lambda **kwargs:BrokenStream([])
            with TestClient(harness.create_app()) as client:
                with client.websocket_connect('/ws') as ws:
                    ready(ws)
                    client.post('/test/turn',json={'text':'السؤال'})
                    events=until(ws,'stop_tts')
                    self.assertFalse(any(e['type']=='final_assistant_answer' for e in events))
                    self.assertEqual(ws.receive_json()['status'],'error')


    def test_late_text_callback_cannot_mutate_or_stamp_a_replacement_generation(self):
        from core.pipeline import RunningGeneration
        harness=Harness()
        with TestClient(harness.create_app()) as client:
            with client.websocket_connect('/ws') as ws:
                ready(ws)
                callback=harness.pipeline.on_partial_assistant_text.__self__
                old=callback.bind_generation_text(1)
                harness.pipeline.running_generation=RunningGeneration(2)
                callback.assistant_answer='جواب جديد'
                old('جواب قديم من عامل تأخر')
                self.assertEqual(callback.assistant_answer,'جواب جديد')
                harness.pipeline.running_generation=None


if __name__=='__main__':unittest.main()
