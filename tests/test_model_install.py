"""No real downloads: verify exact bytes, safe resume and opt-in semantics."""
import hashlib
import io
import os
import threading
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.request import Request

from modern import model_install as installer

MODEL_DATA = b'GGUF' + bytes(range(65))

class FakeDownload(io.BytesIO):
    def __init__(self, data, status=200, headers=None, url=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}
        self.url = url or installer.MODEL_URL
    def geturl(self):
        return self.url


class ModelDownloadTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory(prefix='qx_model_install_')
        self.addCleanup(self.home.cleanup)
        self.env = patch.dict(os.environ, {'QX_AI_MODEL_DIR': self.home.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.stubs = [
            patch.object(installer, 'MODEL_BYTES', len(MODEL_DATA)),
            patch.object(installer, 'MODEL_SHA256', hashlib.sha256(MODEL_DATA).hexdigest()),
            patch.object(installer, 'gguf_runtime_available', return_value=True),
        ]
        for stub in self.stubs:
            stub.start()
            self.addCleanup(stub.stop)
        installer._CANCEL.clear()
        installer._update(state='idle', downloaded=0, verified=False, error='')

    def completed(self):
        for _ in range(250):
            state = installer.model_install_status()
            if state['state'] != 'downloading':
                return state
            time.sleep(.01)
        self.fail('Background download did not finish')

    def test_pinned_official_upstream(self):
        self.assertEqual(installer.MODEL_REPO, 'Qwen/Qwen2.5-1.5B-Instruct-GGUF')
        self.assertIn('resolve/'+installer.MODEL_REVISION, installer.MODEL_URL)
        self.assertEqual(installer.MODEL_SHA256, hashlib.sha256(MODEL_DATA).hexdigest())
        status = installer.model_install_status()
        self.assertFalse(status['file_present'])
        self.assertEqual(status['license'], 'Apache-2.0')
        self.assertEqual(status['state'], 'idle')

    def test_no_implicit_http_on_status(self):
        with patch.object(installer, '_open_model_source', side_effect=AssertionError('No network on status')):
            installer.model_install_status()

    def test_only_https_approved_hosts(self):
        for url in ('http://huggingface.co/model',
                    'https://huggingface.co.evil.example/model',
                    'https://127.0.0.1/model',
                    'https://evil.example/model',
                    'file:///etc/passwd'):
            self.assertFalse(installer._approved_url(url), url)
        self.assertTrue(installer._approved_url(installer.MODEL_URL))
        self.assertTrue(installer._approved_url('https://cas-bridge.xethub.hf.co/x'))
        with self.assertRaises(ValueError):
            installer._RestrictedRedirect().redirect_request(
                Request(installer.MODEL_URL), None, 302, 'redirect', {}, 'http://evil.example/file')

    def test_verified_download_is_atomically_committed(self):
        with patch.object(installer, '_open_model_source', return_value=FakeDownload(MODEL_DATA)) as open_source:
            self.assertEqual(installer.start_model_install()['state'], 'downloading')
            status = self.completed()
        self.assertEqual(status['state'], 'installed')
        self.assertTrue(status['verified'])
        self.assertEqual((Path(self.home.name)/installer.MODEL_NAME).read_bytes(), MODEL_DATA)
        self.assertFalse((Path(self.home.name)/(installer.MODEL_NAME+'.part')).exists())
        self.assertEqual(open_source.call_count, 1)

    def test_corrupted_model_cannot_be_installed(self):
        bad = b'GGUF' + bytes(reversed(range(65)))
        with patch.object(installer, '_open_model_source', return_value=FakeDownload(bad)):
            installer.start_model_install()
            status = self.completed()
        self.assertEqual(status['state'], 'failed')
        self.assertFalse(status['verified'])
        self.assertFalse((Path(self.home.name)/installer.MODEL_NAME).exists())
        self.assertIn('сумма',status['error'])

    def test_resume_uses_content_range_and_same_final_hash(self):
        prefix = MODEL_DATA[:17]
        (Path(self.home.name)/(installer.MODEL_NAME+'.part')).write_bytes(prefix)
        def download(request):
            self.assertEqual(request.get_header('Range'), 'bytes=17-')
            return FakeDownload(MODEL_DATA[17:], status=206,
                headers={'Content-Range':f'bytes 17-{len(MODEL_DATA)-1}/{len(MODEL_DATA)}'})
        with patch.object(installer, '_open_model_source', side_effect=download):
            installer.start_model_install()
            status = self.completed()
        self.assertEqual(status['state'], 'installed')
        self.assertEqual((Path(self.home.name)/installer.MODEL_NAME).read_bytes(), MODEL_DATA)

    def test_ignored_range_restarts_instead_of_appending(self):
        (Path(self.home.name)/(installer.MODEL_NAME+'.part')).write_bytes(b'GGUFx')
        with patch.object(installer, '_open_model_source', return_value=FakeDownload(MODEL_DATA, status=200)):
            installer.start_model_install()
            status = self.completed()
        self.assertEqual(status['state'], 'installed')
        self.assertEqual((Path(self.home.name)/installer.MODEL_NAME).read_bytes(), MODEL_DATA)

    def test_bad_content_range_is_rejected(self):
        (Path(self.home.name)/(installer.MODEL_NAME+'.part')).write_bytes(MODEL_DATA[:10])
        with patch.object(installer, '_open_model_source', return_value=FakeDownload(
            MODEL_DATA[10:],status=206, headers={'Content-Range':'bytes 10-68/999'})):
            installer.start_model_install()
            status = self.completed()
        self.assertEqual(status['state'], 'failed')
        self.assertFalse((Path(self.home.name)/installer.MODEL_NAME).exists())

    def test_model_wrong_location_or_symlink_rejected(self):
        target=Path(self.home.name)/installer.MODEL_NAME
        outer=Path(self.home.name)/'outside.bin'
        outer.write_bytes(MODEL_DATA)
        try:
            target.symlink_to(outer)
        except (OSError,NotImplementedError):
            self.skipTest('Platform does not support symlinks')
        with patch.object(installer, '_open_model_source',side_effect=AssertionError('No network')):
            installer.start_model_install()
            status=self.completed()
        self.assertEqual(status['state'], 'failed')
        self.assertIn('ссылкой',status['error'])

    def test_second_click_does_not_start_duplicate_download(self):
        release=threading.Event()
        entered=threading.Event()
        class SlowDownload(FakeDownload):
            def read(self, size=-1):
                entered.set()
                release.wait(2)
                return super().read(size)
        with patch.object(installer,'_open_model_source',return_value=SlowDownload(MODEL_DATA)) as source:
            installer.start_model_install()
            self.assertTrue(entered.wait(2))
            current=installer.start_model_install()
            self.assertEqual(current['state'],'downloading')
            self.assertEqual(current['bytes_total'],len(MODEL_DATA))
            self.assertEqual(source.call_count,1)
            release.set()
            result=self.completed()
        self.assertEqual(result['state'],'installed')

    def test_cancelled_download_preserves_partial_data_for_retry(self):
        entered=threading.Event()
        release=threading.Event()
        class SlowDownload(FakeDownload):
            def read(self, size=-1):
                if self.tell() == 0:
                    return super().read(12)
                entered.set()
                release.wait(2)
                return super().read(12)
        with patch.object(installer,'_open_model_source',return_value=SlowDownload(MODEL_DATA)):
            installer.start_model_install()
            self.assertTrue(entered.wait(2))
            installer.cancel_model_install()
            release.set()
            result=self.completed()
        self.assertEqual(result['state'],'cancelled')
        partial=(Path(self.home.name)/(installer.MODEL_NAME+'.part'))
        self.assertTrue(partial.is_file())
        self.assertFalse((Path(self.home.name)/installer.MODEL_NAME).exists())
        prefix=partial.read_bytes()
        def resume(request):
            length=len(prefix)
            self.assertEqual(request.get_header('Range'),f'bytes={length}-')
            return FakeDownload(MODEL_DATA[length:],status=206,
                headers={'Content-Range':f'bytes {length}-{len(MODEL_DATA)-1}/{len(MODEL_DATA)}'})
        with patch.object(installer,'_open_model_source',side_effect=resume):
            installer.start_model_install()
            result=self.completed()
        self.assertEqual(result['state'],'installed')
        self.assertEqual((Path(self.home.name)/installer.MODEL_NAME).read_bytes(),MODEL_DATA)

    def test_runtime_missing_does_not_download(self):
        with patch.object(installer, 'gguf_runtime_available',return_value=False), \
             patch.object(installer, '_open_model_source',side_effect=AssertionError('No network')):
            with self.assertRaises(ValueError):
                installer.start_model_install()
        self.assertEqual(installer.model_install_status()['state'],'idle')

    def test_existing_verified_model_requires_no_download(self):
        (Path(self.home.name)/installer.MODEL_NAME).write_bytes(MODEL_DATA)
        with patch.object(installer, '_open_model_source',side_effect=AssertionError('No network')):
            installer.start_model_install()
            status=self.completed()
        self.assertEqual(status['state'],'installed')
        self.assertTrue(status['verified'])


if __name__=='__main__':
    unittest.main()
