"""Measurement calculations and supervisor lifecycle, without live GPU claims."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

STUDIO = Path(__file__).resolve().parents[1] / 'studio'


def load(name):
    spec = importlib.util.spec_from_file_location(name, STUDIO / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


measure = load('measure')
stack = load('run_stack')


class MeasurementTests(unittest.TestCase):
    def test_empty_and_nearest_rank_distributions(self):
        self.assertIsNone(measure.distribution([])['p95'])
        self.assertEqual(measure.distribution([4, None, 1, 2, 3]),
                         {'count': 4, 'p50': 2, 'p95': 4, 'max': 4})

    def test_browser_turn_boundaries_exclude_between_turn_gaps(self):
        names = [('mark:utterance_end', 10), ('server:final_user_request', 110),
                 ('server:tts_chunk', 200), ('playback:ttsPlaybackStarted', 220),
                 ('playback:ttsPlaybackStopped', 400), ('server:tts_chunk', 450),
                 ('playback:ttsPlaybackStarted', 470), ('server:final_assistant_answer', 480),
                 ('playback:ttsPlaybackStopped', 800), ('mark:utterance_end', 3000),
                 ('server:final_user_request', 3100), ('server:tts_chunk', 3200),
                 ('playback:ttsPlaybackStarted', 3220), ('mark:interrupt_start', 3300),
                 ('server:stop_tts', 3350), ('playback:ttsPlaybackStopped', 3360)]
        metrics = measure.browser_metrics([{'event': name, 'browser_ms': stamp} for name, stamp in names])
        self.assertEqual(metrics['render_gaps_ms']['count'], 1)
        self.assertEqual(metrics['render_gaps_ms']['max'], 70)
        self.assertEqual(metrics['marked_endpoint_to_final_stt_ms']['p50'], 100)
        self.assertEqual(metrics['marked_endpoint_to_render_start_ms']['count'], 2)
        self.assertEqual(metrics['marked_interrupt_to_render_stop_ms']['max'], 60)

    def test_gpu_samples_are_device_wide_and_do_not_claim_acceptance(self):
        with patch.object(subprocess, 'check_output', return_value='0, NVIDIA L4, 23034, 18000, 5034, 80\n'):
            sample = measure.gpu_sample()
        self.assertEqual(sample['devices'][0]['free_mib'], 5034)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'gpu.jsonl').write_text(json.dumps(sample) + '\n')
            from types import SimpleNamespace
            measure.summarize(SimpleNamespace(gpu=root / 'gpu.jsonl', browser=None, services=None,
                                              output=root / 'report.json'))
            report = json.loads((root / 'report.json').read_text())
            self.assertEqual(report['gpu']['0']['peak_used_mib'], 18000)
            self.assertEqual(report['live_acceptance'], 'pending_human_review')

    def test_readiness_rejects_an_exited_child(self):
        from unittest.mock import Mock
        child = Mock(returncode=9)
        child.poll.return_value = 9
        with self.assertRaisesRegex(RuntimeError, 'exited with code 9'):
            stack.wait_ready(child, 'http://127.0.0.1:1', 1)

    @unittest.skipIf(sys.platform == 'win32', 'POSIX process groups')
    def test_shutdown_only_owned_process_group(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
        try:
            stack.stop_children([child], grace=1)
            self.assertIsNotNone(child.poll())
        finally:
            if child.poll() is None:
                child.kill(); child.wait()


if __name__ == '__main__':
    unittest.main()
