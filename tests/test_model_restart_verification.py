"""On the next launch an existing Qwen GGUF is verified without network or UI stalls."""
import hashlib
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from modern import model_install as installer

SOURCE=b'GGUF' + b'A'*500000


class TestModelRestartVerification(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='qx_model_restart_')
        self.addCleanup(self.temp.cleanup)
        self.env=patch.dict('os.environ',{'QX_AI_MODEL_DIR':self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        patches=[patch.object(installer,'MODEL_BYTES',len(SOURCE)),
                 patch.object(installer,'MODEL_SHA256',hashlib.sha256(SOURCE).hexdigest())]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        installer._update(state='idle', downloaded=0, error='', verified=False)
        self.path=Path(self.temp.name)/installer.MODEL_NAME

    def wait_status(self):
        for _ in range(300):
            info=installer.model_install_status()
            if info['state']!='verifying': return info
            time.sleep(.01)
        self.fail('Local SHA verification did not finish')

    def test_verified_model_is_detected_after_restart_without_download(self):
        self.path.write_bytes(SOURCE)
        with patch.object(installer,'_open_model_source',side_effect=AssertionError('No network')):
            first=installer.model_install_status()
            self.assertIn(first['state'],('verifying','installed'))
            result=self.wait_status()
        self.assertEqual(result['state'],'installed')
        self.assertTrue(result['verified'])
        self.assertEqual(result['downloaded'],len(SOURCE))

    def test_modified_model_is_not_trusted_after_restart(self):
        self.path.write_bytes(SOURCE[:-1]+b'B')
        with patch.object(installer,'_open_model_source',side_effect=AssertionError('No network')):
            result=self.wait_status()
        self.assertEqual(result['state'],'failed')
        self.assertFalse(result['verified'])
        self.assertIn('SHA-256',result['error'])

    def test_status_does_not_hash_synchronously(self):
        self.path.write_bytes(SOURCE)
        import threading
        started=threading.Event()
        release=threading.Event()
        actual_hash=installer._hash_existing
        def slowed(path):
            started.set()
            release.wait(2)
            return actual_hash(path)
        with patch.object(installer,'_hash_existing',side_effect=slowed):
            before=time.monotonic()
            first=installer.model_install_status()
            elapsed=time.monotonic()-before
            self.assertLess(elapsed,.5)
            self.assertEqual(first['state'],'verifying')
            self.assertTrue(started.wait(1))
            release.set()
            self.assertEqual(self.wait_status()['state'],'installed')


if __name__ == '__main__':
    unittest.main()
