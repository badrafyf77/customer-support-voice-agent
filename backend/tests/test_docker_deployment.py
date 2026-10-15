"""Validate the actual Compose render and readiness contract without a GPU daemon."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('docker'), 'Docker CLI/Compose is required')
class ComposeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        root = Path(cls.temporary.name)
        (root / 'asr').mkdir()
        (root / '.env').write_text('HF_TOKEN=test-runtime-token\nBACKEND_PORT=9090\n'
                                   f'ASR_EXPORT_DIR={root / "asr"}\n'
                                   'VLLM_GPU_MEMORY_UTILIZATION=0.35\n'
                                   'SILMA_VOICE_ID=voice1\nSILMA_CHECKPOINT_VARIANT=main\n')
        # Compose resolves env_file relative to the project directory. Use only
        # this test's fake .env, never inspect a user's real token/configuration.
        environment = os.environ.copy()
        for name in ('HF_TOKEN', 'BACKEND_PORT', 'ASR_EXPORT_DIR', 'VLLM_GPU_MEMORY_UTILIZATION'):
            environment.pop(name, None)
        result = subprocess.run(['docker', 'compose', '--project-directory', str(root),
                                 '--env-file', str(root / '.env'), '-f', str(BACKEND / 'docker-compose.yml'),
                                 'config', '--format', 'json'], env=environment,
                                capture_output=True, text=True)
        if result.returncode:
            raise AssertionError('Compose render failed: ' + result.stderr)
        cls.services = json.loads(result.stdout)['services']

    def test_only_backend_is_published_and_env_controls_port(self):
        self.assertEqual(set(self.services), {'prepare-models', 'vllm', 'silma', 'app'})
        self.assertEqual(self.services['app']['ports'][0]['published'], '9090')
        self.assertEqual(self.services['app']['ports'][0]['target'], 8080)
        for name in ('prepare-models', 'vllm', 'silma'):
            self.assertFalse(self.services[name].get('ports'))

    def test_runtime_token_and_budget_are_loaded_from_env_not_build_args(self):
        for service in self.services.values():
            self.assertEqual(service['environment']['HF_TOKEN'], 'test-runtime-token')
            self.assertFalse(service['build'].get('args'))
        self.assertEqual(self.services['vllm']['environment']['VLLM_GPU_MEMORY_UTILIZATION'], '0.35')
        self.assertEqual(self.services['app']['environment']['VLLM_BASE_URL'], 'http://vllm:8001/v1')
        self.assertEqual(self.services['app']['environment']['SILMA_TTS_BASE_URL'], 'http://silma:8002')

    def test_start_order_and_single_gpu_runtime(self):
        self.assertEqual(self.services['vllm']['depends_on']['prepare-models']['condition'], 'service_completed_successfully')
        self.assertEqual(self.services['silma']['depends_on']['vllm']['condition'], 'service_healthy')
        self.assertEqual(self.services['app']['depends_on']['silma']['condition'], 'service_healthy')
        for name in ('vllm', 'silma', 'app'):
            device = self.services[name]['deploy']['resources']['reservations']['devices'][0]
            self.assertEqual((device['driver'], device['count']), ('nvidia', 1))
            self.assertIn('gpu', device['capabilities'])
            self.assertEqual(self.services[name]['environment']['VOICE_RUNTIME_MAX_CONCURRENT'], '1')
        self.assertFalse(self.services['prepare-models'].get('deploy'))

    def test_models_are_persistent_and_readonly_outside_preparation(self):
        for name, service in self.services.items():
            mount = next(m for m in service['volumes'] if m['target'] == '/models')
            self.assertEqual(mount['type'], 'volume')
            self.assertEqual(mount.get('read_only', False), name != 'prepare-models')
        source = next(m for m in self.services['prepare-models']['volumes'] if m['target'] == '/asr-export')
        self.assertTrue(source['read_only'])
        self.assertFalse(source['bind']['create_host_path'])


class HealthTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('container_health', BACKEND / 'studio/container_health.py')
        self.health = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.health)

    def check(self, role, payload):
        import io
        class Reply(io.BytesIO):
            status = 200
        with patch.object(self.health, 'urlopen', return_value=Reply(b'' if payload is None else json.dumps(payload).encode())):
            self.health.check(role)

    def test_accepts_vllm_empty_body_and_ready_services(self):
        self.check('vllm', None)
        self.check('silma', {'ready': True})
        self.check('backend', {'status': 'ok', 'voice_profile': 'darija'})

    def test_rejects_unready_tts_or_wrong_backend_profile(self):
        for role, payload in [('silma', {'ready': False}), ('backend', {'status': 'ok', 'voice_profile': 'english'})]:
            with self.subTest(role=role), self.assertRaises(RuntimeError):
                self.check(role, payload)


if __name__ == '__main__':
    unittest.main()
