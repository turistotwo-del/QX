"""Version consistency and non-destructive user health diagnostics."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from modern import tender_store as store
from modern import local_ai
from modern.diagnostics import run_diagnostics
from modern.release_info import RELEASE_LABEL, SETUP_BASENAME, inno_defines
from modern.server import app, boot
import qx_entry
from windows_build.release_metadata import main as metadata_main

ROOT=Path(__file__).resolve().parents[1]

class TestReleaseAndDiagnostics(unittest.TestCase):
    def test_version_agrees_with_api_and_entrypoint(self):
        self.assertIn(RELEASE_LABEL,boot()['version'])
        from io import StringIO
        from contextlib import redirect_stdout
        out=StringIO()
        with patch('sys.argv',['qx_entry.py','--version']), redirect_stdout(out):
            self.assertEqual(qx_entry.main(),0)
        self.assertIn(RELEASE_LABEL,out.getvalue())
        self.assertIn(f'QXOutputBase "{SETUP_BASENAME}"',inno_defines())

    def test_generated_version_and_inno_recipe(self):
        self.assertEqual((ROOT/'windows_build/qx_version.iss').read_text(encoding='utf-8'),inno_defines())
        self.assertIn('#include "qx_version.iss"',(ROOT/'windows_build/QX_Setup.iss').read_text(encoding='utf-8'))

    def test_empty_data_dir_health_has_no_network_or_personal_data(self):
        with tempfile.TemporaryDirectory(prefix='qx_diag_') as tmp:
            before=(store.APP_DATA,store.DB_FILE,store.DOCUMENTS,store._INITIALIZED)
            try:
                store.APP_DATA=Path(tmp)
                store.DB_FILE=store.APP_DATA/'tenders.sqlite3'
                store.DOCUMENTS=store.APP_DATA/'tender_documents'
                store._INITIALIZED=False
                with patch.object(local_ai,'gguf_runtime_available',return_value=False), \
                     patch.object(local_ai,'gguf_model_dir',return_value=Path(tmp)/'models'):
                    with TestClient(app) as client:
                        response=client.get('/api/diagnostics')
                    self.assertEqual(response.status_code,200)
                    result=response.json()
                self.assertEqual(result['version'], RELEASE_LABEL)
                self.assertTrue(any(c['name']=='База закупок' and c['status']=='ok' for c in result['checks']))
                self.assertTrue(any(c['name']=='Папка данных' and c['status']=='ok' for c in result['checks']))
                self.assertEqual(result['overall'],'warning')
                self.assertNotIn('source_text',str(result))
            finally:
                store.APP_DATA,store.DB_FILE,store.DOCUMENTS,store._INITIALIZED=before

    def test_health_reports_missing_documents_without_opening_contents(self):
        with tempfile.TemporaryDirectory(prefix='qx_diag_') as tmp:
            before=(store.APP_DATA,store.DB_FILE,store.DOCUMENTS,store._INITIALIZED)
            try:
                store.APP_DATA=Path(tmp);store.DB_FILE=store.APP_DATA/'tenders.sqlite3'
                store.DOCUMENTS=store.APP_DATA/'tender_documents';store._INITIALIZED=False
                item=store.create({'title':'PRIVATE TENDER'})
                store.add_document(item['id'],'private-contract.txt',b'Private text', 'short text')
                with store.connection() as con:
                    file_path=con.execute('SELECT file_path FROM tender_documents LIMIT 1').fetchone()[0]
                Path(file_path).unlink()
                with patch.object(local_ai,'gguf_runtime_available',return_value=False), \
                     patch.object(local_ai,'gguf_model_dir',return_value=Path(tmp)/'models'):
                    result=run_diagnostics()
                self.assertEqual(result['overall'],'error')
                self.assertTrue(any(c['name']=='Файлы договоров' and c['status']=='error' for c in result['checks']))
                self.assertNotIn('PRIVATE TENDER',str(result))
                self.assertNotIn('Private text',str(result))
            finally:
                store.APP_DATA,store.DB_FILE,store.DOCUMENTS,store._INITIALIZED=before

if __name__=='__main__':unittest.main()
