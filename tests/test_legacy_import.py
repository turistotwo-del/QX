"""Tests opt-in QX 3.3.7 profile transfer; live data must remain safe."""
from contextlib import ExitStack
from io import BytesIO
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient
from core import storage
from modern import legacy_import as importer
from modern import tender_store
from modern.server import app


def makezip(files, prefix='QX_Подборщик_3.3_MODERN/'):
    buf=BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():
            z.writestr(prefix+name, data)
    return buf.getvalue()


class LegacyImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='qx_legacy_import_')
        self.addCleanup(self.tmp.cleanup)
        home=Path(self.tmp.name)
        self.patches=ExitStack()
        self.addCleanup(self.patches.close)
        for obj,attr,value in (
            (storage,'DATA_DIR',home/'target'),
            (storage,'PRICES_FILE',home/'target'/'qx_prices.json'),
            (storage,'SETTINGS_FILE',home/'target'/'settings.json'),
            (tender_store,'APP_DATA',home/'user'),
        ):
            self.patches.enter_context(patch.object(obj,attr,value))
        storage.DATA_DIR.mkdir(parents=True,exist_ok=True)
        storage.PRICES_FILE.write_text('{"legacy_existing": true}',encoding='utf8')
        storage.SETTINGS_FILE.write_text('{"sidebar_width": 444}',encoding='utf8')
        self.previous_prices=storage.PRICES_FILE.read_bytes()
        self.previous_settings=storage.SETTINGS_FILE.read_bytes()
        self.client=TestClient(app)
        key=next(iter(storage.DEFAULT_QX_PRICES))
        self.prices={key:{'name':'QX test','price':12678.12}}
        self.settings={'ui_theme':'light','sidebar_width':390,'unknown_secret_key':'not imported'}
        self.zip=makezip({'data/qx_prices.json':json.dumps(self.prices).encode(),
                           'data/settings.json':json.dumps(self.settings).encode()})

    def test_preview_never_changes_live_data(self):
        r=self.client.post('/api/legacy/preview',content=self.zip)
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['prices']['positions'],1)
        self.assertEqual(r.json()['settings']['parameters'],3)
        self.assertEqual(storage.PRICES_FILE.read_bytes(),self.previous_prices)
        self.assertEqual(storage.SETTINGS_FILE.read_bytes(),self.previous_settings)
        self.assertFalse((tender_store.APP_DATA/'legacy_import_snapshots').exists())

    def test_import_needs_explicit_confirmation(self):
        r=self.client.post('/api/legacy/import',content=self.zip)
        self.assertEqual(r.status_code,400)
        self.assertEqual(storage.PRICES_FILE.read_bytes(),self.previous_prices)

    def test_import_both_preserves_snapshot_and_new_defaults(self):
        r=self.client.post('/api/legacy/import',content=self.zip,
            headers={'X-QX-Confirm-Legacy':'IMPORT_LEGACY_SETTINGS_AND_PRICES'})
        self.assertEqual(r.status_code,200,r.text)
        j=r.json()
        path=Path(j['snapshot'])
        self.assertEqual((path/'qx_prices.json').read_bytes(),self.previous_prices)
        self.assertEqual((path/'settings.json').read_bytes(),self.previous_settings)
        self.assertTrue((path/'manifest.json').exists())
        imported=json.loads(storage.PRICES_FILE.read_text('utf8'))
        key=next(iter(self.prices))
        self.assertEqual(imported[key]['price'],12678.12)
        self.assertGreaterEqual(len(imported),len(storage.DEFAULT_QX_PRICES))
        settings=json.loads(storage.SETTINGS_FILE.read_text('utf8'))
        self.assertEqual(settings['ui_theme'],'light')
        self.assertNotIn('unknown_secret_key',settings)

    def test_import_only_prices_never_overwrites_settings(self):
        raw=makezip({'data/qx_prices.json':json.dumps(self.prices)})
        importer.import_legacy(raw)
        self.assertEqual(storage.SETTINGS_FILE.read_bytes(),self.previous_settings)

    def test_invalid_json_and_zip_preserve_originals(self):
        for bad in (b'invalid',makezip({'data/qx_prices.json':b'{ invalid'}),
                    makezip({'data/settings.json':json.dumps({'notQx':'foo'})})):
            with self.subTest(bad=bad[:10]):
                resp=self.client.post('/api/legacy/preview',content=bad)
                self.assertEqual(resp.status_code,422)
                self.assertEqual(storage.PRICES_FILE.read_bytes(),self.previous_prices)
                self.assertEqual(storage.SETTINGS_FILE.read_bytes(),self.previous_settings)

    def test_ambiguous_and_traversal_paths_rejected(self):
        duplicate=makezip({'data/qx_prices.json':json.dumps(self.prices),
                           'other/data/qx_prices.json':json.dumps(self.prices)}, prefix='')
        # test ZIP entries with two different enclosing source folders
        repeated=makezip({'A/data/qx_prices.json':json.dumps(self.prices),
                          'B/data/qx_prices.json':json.dumps(self.prices)},prefix='')
        for archive in (repeated,makezip({'../data/settings.json':'{}'},prefix='')):
            with self.assertRaises(ValueError):
                importer.preview_legacy(archive)
        self.assertEqual(storage.PRICES_FILE.read_bytes(),self.previous_prices)

    def test_failed_second_write_rolls_back_first(self):
        actual=importer._atomic_raw
        def failing(path, data):
            if path == storage.SETTINGS_FILE:
                raise OSError('simulated disk failure')
            return actual(path,data)
        with patch.object(importer,'_atomic_raw',side_effect=failing):
            with self.assertRaises(OSError):
                importer.import_legacy(self.zip)
        self.assertEqual(storage.PRICES_FILE.read_bytes(),self.previous_prices)
        self.assertEqual(storage.SETTINGS_FILE.read_bytes(),self.previous_settings)
        # Recovery data is still available even after rollback
        backups=list((tender_store.APP_DATA/'legacy_import_snapshots').iterdir())
        self.assertEqual(len(backups),1)
        self.assertTrue((backups[0]/'manifest.json').exists())

    def test_bad_target_symlink_refused(self):
        storage.PRICES_FILE.unlink()
        storage.PRICES_FILE.symlink_to(storage.SETTINGS_FILE)
        with self.assertRaisesRegex(ValueError,'символической'):
            importer.import_legacy(self.zip)
        self.assertEqual(storage.SETTINGS_FILE.read_bytes(),self.previous_settings)

if __name__ == '__main__': unittest.main()
