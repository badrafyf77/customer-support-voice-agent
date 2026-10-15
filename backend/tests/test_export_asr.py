"""Publishing/caching CPU-built ASR exports must preserve pinned artifacts."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

STUDIO = Path(__file__).resolve().parents[1] / 'studio'
module_spec = importlib.util.spec_from_file_location('export_asr', STUDIO / 'export_asr.py')
export = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(export)


class ExportTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.data = {'model.bin': b'correct-merged-adapter', 'tokenizer.json': b'correct-tokenizer'}
        self.spec = {'directory': 'asr', 'repo_id': 'chosen-darija', 'revision': 'pinned-adapter',
                     'base_model': 'chosen-base', 'base_revision': 'pinned-base',
                     'files': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                               for name, data in self.data.items()}}

    def builder(self, workspace, spec, threads):
        self.assertEqual((spec['revision'], spec['base_revision']), ('pinned-adapter', 'pinned-base'))
        destination = workspace / 'ctranslate2'
        destination.mkdir()
        for name, data in self.data.items():
            (destination / name).write_bytes(data)
        return {'training_performed': False, 'quantization': 'float16'}

    def test_only_verified_output_is_published_and_reused_without_rebuilding(self):
        result = export.prepare_export(self.root, self.spec, builder=self.builder)
        self.assertEqual((result / 'model.bin').read_bytes(), self.data['model.bin'])
        report = json.loads((self.root / 'asr-export.json').read_text())
        self.assertEqual(report['revision'], 'pinned-adapter')
        self.assertFalse(report['training_performed'])
        def forbidden(*args):
            self.fail('A verified export must not redownload or merge again')
        export.prepare_export(self.root, self.spec, builder=forbidden)

    def test_wrong_export_cannot_replace_previous_files(self):
        target = self.root / 'asr'
        target.mkdir()
        (target / 'model.bin').write_bytes(b'previous')
        def wrong(workspace, spec, threads):
            details = self.builder(workspace, spec, threads)
            (workspace / 'ctranslate2/model.bin').write_bytes(b'wrong-export')
            return details
        with self.assertRaisesRegex(export.ExportError, 'provenance mismatch'):
            export.prepare_export(self.root, self.spec, builder=wrong)
        self.assertEqual((target / 'model.bin').read_bytes(), b'previous')
        self.assertFalse((self.root / 'asr-export.json').exists())
        self.assertFalse(list(self.root.glob('.asr-build-*')))

    def test_download_or_merge_failure_does_not_leave_ready_files(self):
        def failed(workspace, spec, threads):
            (workspace / 'merged').mkdir()
            raise ConnectionError('HF download interrupted')
        with self.assertRaises(ConnectionError):
            export.prepare_export(self.root, self.spec, builder=failed)
        self.assertFalse((self.root / 'asr').exists())
        self.assertFalse(list(self.root.glob('.asr-build-*')))

    def test_tokenizer_merge_format_changes_preserve_ids_and_reject_id_changes(self):
        path = self.root / 'tokenizer.json'
        path.write_text(json.dumps({'model': {'merges': [['a', 'b']], 'ignore_merges': False}}))
        class Tokenizer:
            @staticmethod
            def from_file(_path):
                return SimpleNamespace(encode=lambda text: SimpleNamespace(ids=list(text.encode())))
            @staticmethod
            def from_str(text):
                data = json.loads(text)
                self.assertEqual(data['model']['merges'], ['a b'])
                self.assertNotIn('ignore_merges', data['model'])
                return Tokenizer.from_file(None)
        export.normalize_fast_tokenizer(path, Tokenizer)
        original = path.read_bytes()
        class Changed(Tokenizer):
            @staticmethod
            def from_str(text):
                return SimpleNamespace(encode=lambda text: SimpleNamespace(ids=[999]))
        with self.assertRaisesRegex(export.ExportError, 'token IDs'):
            export.normalize_fast_tokenizer(path, Changed)
        self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
