"""Keep common legacy EIS originals through import, audit, backup and restore."""
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

os.environ.setdefault('QX_DATA_DIR',tempfile.mkdtemp(prefix='qx_legacy_boot_'))
from modern import tender_store as store
from modern.attachment_formats import OLE_SIGNATURE, validate_raw_document
from modern.attachment_integrity import audit_attachments
from modern.eis_document_download import fetch_official_document, import_official_document
from modern.tender_package import import_package
from modern.tender_backup import preview_archive, restore_archive
from modern.tender_analysis import analyze_documents

FILES = {'ТЗ.doc':OLE_SIGNATURE + b'\0'*504 + b'DOC-original',
         'Смета.xls':OLE_SIGNATURE + b'\0'*504 + b'XLS-original',
         'Контракт.rtf':b'{\\rtf1\\ansi Contract original}'}


class Reply:
    def __init__(self,name,data,mime='application/octet-stream'):
        self.url='https://zakupki.gov.ru/files/' + name
        self.stream=BytesIO(data)
        self.headers={'Content-Type':mime,'Content-Disposition':f'attachment; filename="{name}"'}
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def geturl(self):return self.url
    def read(self,n=-1):return self.stream.read(n)


class Opener:
    def __init__(self,name,data,mime='application/octet-stream'):self.args=(name,data,mime)
    def open(self,*a,**k):return Reply(*self.args)


class LegacyOriginals(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='qx_legacy_originals_')
        self.old=(store.APP_DATA,store.DB_FILE,store.DOCUMENTS,store._INITIALIZED)
        store.APP_DATA=Path(self.tmp.name);store.DB_FILE=store.APP_DATA/'tenders.sqlite3'
        store.DOCUMENTS=store.APP_DATA/'documents';store._INITIALIZED=False;store.initialize()
        self.tid=store.create({'number':'0322100002526000466'})['id']

    def tearDown(self):
        store.APP_DATA,store.DB_FILE,store.DOCUMENTS,store._INITIALIZED=self.old
        self.tmp.cleanup()

    def test_direct_imports_keep_exact_bytes_and_warn_no_analysis(self):
        for name,data in FILES.items():
            with self.subTest(name=name):
                result=import_official_document(self.tid,'https://zakupki.gov.ru/files/document' + Path(name).suffix,
                                                opener=Opener(name,data))
                self.assertEqual(result['imported'],[name])
                self.assertIn('автоматический анализ',result['warnings'][0]['reason'])
                self.assertEqual(store.document_bytes(self.tid,result['document_id']),(name,data))
        self.assertEqual(audit_attachments()['valid'],3)

    def test_fake_legacy_payloads_rejected_before_storage(self):
        for suffix in ('.doc','.xls','.rtf'):
            for data in (b'<html>login</html>',b'<!DOCTYPE html>captcha',b'MZ' + b'x'*600,b'junk'):
                with self.subTest(suffix=suffix,data=data[:20]),self.assertRaises(ValueError):
                    import_official_document(self.tid,'https://zakupki.gov.ru/files/fake' + suffix,
                                             opener=Opener('fake' + suffix,data))
        self.assertEqual(store.detail(self.tid)['documents'],[])

    def test_zip_legacy_roundtrip_backup_restore_and_delete(self):
        payload=BytesIO()
        with ZipFile(payload,'w',compression=ZIP_DEFLATED) as archive:
            for name,data in FILES.items():archive.writestr('Приложения/' + name,data)
        result=import_package(self.tid,payload.getvalue())
        self.assertEqual(len(result['imported']),3)
        self.assertEqual(len(result['warnings']),3)
        self.assertEqual(result['ignored'],[])
        backup=store.backup_archive()
        self.assertEqual(preview_archive(backup)['documents'],3)
        store.delete_tender(self.tid)
        self.assertEqual(list(store.DOCUMENTS.iterdir()),[])
        restore_archive(backup)
        for document in store.detail(self.tid)['documents']:
            self.assertEqual(store.document_bytes(self.tid,document['id'])[1],FILES[document['filename']])
        self.assertEqual(audit_attachments()['valid'],3)
        store.delete_tender(self.tid)
        self.assertEqual(list(store.DOCUMENTS.iterdir()),[])

    def test_zip_malformed_legacy_is_reported_ignored(self):
        payload=BytesIO()
        with ZipFile(payload,'w',compression=ZIP_DEFLATED) as archive:
            archive.writestr('good.txt','Техническое задание')
            archive.writestr('fake.doc',b'<html>login</html>')
        result=import_package(self.tid,payload.getvalue())
        self.assertEqual([x['filename'] for x in result['imported']],['good.txt'])
        self.assertEqual(result['ignored'][0]['name'],'fake.doc')

    def test_raw_originals_do_not_produce_fake_analysis(self):
        result=analyze_documents(list(FILES.items()))
        self.assertEqual(len(result['errors']),3)
        self.assertTrue(all('автоматический анализ' in item['error'] for item in result['errors']))

    def test_api_upload_download_preserves_original(self):
        from fastapi.testclient import TestClient
        from modern.server import app
        from urllib.parse import quote
        client=TestClient(app)
        for name,data in FILES.items():
            uploaded=client.post(f'/api/tenders/{self.tid}/documents',content=data,
                                 headers={'x-file-name':quote(name)})
            self.assertEqual(uploaded.status_code,200,uploaded.text)
            result=uploaded.json()
            self.assertIn('автоматический анализ',result['warnings'][0])
            response=client.get(f'/api/tenders/{self.tid}/documents/' + result['document_id'])
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.content,data)
            self.assertIn('attachment;',response.headers['content-disposition'])
        malformed=client.post(f'/api/tenders/{self.tid}/documents',content=b'<html>login</html>',
                              headers={'x-file-name':'fake.doc'})
        self.assertEqual(malformed.status_code,400)


if __name__=='__main__':unittest.main()
