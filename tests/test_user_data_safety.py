"""Protect QX user-edited prices/settings from destructive read/write failures."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from core import storage


class TestUserDataRecovery(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='qx_storage_')
        self.home=Path(self.temp.name)
        self.patchers=[patch.object(storage,'DATA_DIR',self.home),
                       patch.object(storage,'PRICES_FILE',self.home/'qx_prices.json'),
                       patch.object(storage,'SETTINGS_FILE',self.home/'settings.json'),
                       patch.object(storage,'ROOT',self.home/'package')]
        for p in self.patchers:p.start()

    def tearDown(self):
        for p in reversed(self.patchers):p.stop()
        self.temp.cleanup()

    def test_price_update_roundtrip(self):
        storage.save_prices({'cpu':{'price':7000}})
        self.assertEqual(storage._read_or_create(storage.PRICES_FILE,{})['cpu']['price'],7000)
        self.assertFalse(list(self.home.glob('*.tmp')))

    def test_invalid_price_file_preserved_not_destroyed(self):
        raw=b'{"user_price":123, invalid json here'
        storage.PRICES_FILE.write_bytes(raw)
        result=storage._read_or_create(storage.PRICES_FILE,{'fallback':True})
        self.assertEqual(result,{'fallback':True})
        copies=list(self.home.glob('qx_prices.json.corrupt-*'))
        self.assertEqual(len(copies),1)
        self.assertEqual(copies[0].read_bytes(),raw)
        self.assertTrue((self.home/'QX_DATA_RECOVERY.log').exists())

    def test_wrong_json_type_preserved(self):
        storage.SETTINGS_FILE.write_text('["lost settings"]',encoding='utf-8')
        self.assertEqual(storage._read_or_create(storage.SETTINGS_FILE,{'ui_theme':'light'}),{'ui_theme':'light'})
        copies=list(self.home.glob('settings.json.corrupt-*'))
        self.assertEqual(len(copies),1)
        self.assertIn('lost settings',copies[0].read_text(encoding='utf-8'))

    def test_failed_backup_does_not_destroy_original(self):
        path=storage.PRICES_FILE
        path.write_text('{ invalid',encoding='utf-8')
        with patch.object(storage.os,'replace',side_effect=PermissionError('access denied')):
            with self.assertRaises(RuntimeError):storage._read_or_create(path,{'price':1})
        self.assertEqual(path.read_text(encoding='utf-8'),'{ invalid')

if __name__=='__main__':unittest.main()
