"""End-to-end EIS URL-to-document tests without contacting the real portal."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os
import tempfile
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

os.environ.setdefault('QX_DATA_DIR', tempfile.mkdtemp(prefix='qx_eis_import_boot_'))
from docx import Document
from fastapi.testclient import TestClient
from modern import tender_store as store
from modern.server import app
from modern.eis_document_download import (
    validate_document_url, fetch_official_document, import_official_document,
    OfficialRedirects,
)

EIS = 'https://zakupki.gov.ru/44fz/filestore/public/attachment.docx'


class FakeResponse:
    def __init__(self, content, url=EIS, content_type='application/octet-stream', disposition='', content_length=None):
        self.stream=BytesIO(content)
        self.url=url
        self.headers={'Content-Type': content_type}
        if disposition: self.headers['Content-Disposition']=disposition
        if content_length is not None: self.headers['Content-Length']=str(content_length)
    def __enter__(self):return self
    def __exit__(self, *args):return False
    def read(self, n=-1):return self.stream.read(n)
    def geturl(self):return self.url

class FakeOpener:
    def __init__(self, reply):self.reply=reply
    def open(self, request, timeout):
        assert request.full_url.startswith('https://zakupki.gov.ru/')
        assert timeout <= 15
        return self.reply


def word(text):
    d=Document();d.add_paragraph(text);b=BytesIO();d.save(b);return b.getvalue()


def bundle(name, content):
    b=BytesIO()
    with ZipFile(b,'w',compression=ZIP_DEFLATED) as z:z.writestr(name,content)
    return b.getvalue()


class TestEisFileSafety(unittest.TestCase):
    def test_official_host_only(self):
        bad = ['http://zakupki.gov.ru/a.pdf','https://zakupki.gov.ru.evil.org/a.pdf',
               'https://evil.org/a.pdf','https://127.0.0.1/secret.pdf',
               'file:///etc/passwd','https://zakupki.gov.ru@evil.org/a.pdf',
               'https://zakupki.gov.ru:8443/abc.pdf','https://zakupki.gov.ru/a/../x.pdf',
               'https://zakupki.gov.ru/a/%2e%2e/x.pdf', 'https://zakupki.gov.ru/a.pdf#frag']
        for u in bad:
            with self.subTest(url=u),self.assertRaises(ValueError): validate_document_url(u)
        self.assertEqual(validate_document_url(EIS),EIS)
    def test_foreign_redirect_rejected(self):
        from urllib.request import Request
        with self.assertRaises(ValueError):
            OfficialRedirects().redirect_request(Request(EIS),None,302,'Moved',{},'https://evil.org/a.pdf')
    def test_fake_html_or_captcha_never_imported(self):
        with self.assertRaisesRegex(ValueError,'страницу'):
            fetch_official_document(EIS,FakeOpener(FakeResponse(b'<html>captcha</html>',content_type='text/html')))
    def test_file_size_cap(self):
        with self.assertRaisesRegex(ValueError,'слишком большой'):
            fetch_official_document(EIS,FakeOpener(FakeResponse(b'a',content_length=100_000_000)))
    def test_pdf_magic(self):
        with self.assertRaisesRegex(ValueError,'PDF'):
            fetch_official_document(EIS.replace('.docx','.pdf'),FakeOpener(FakeResponse(b'<html>error</html>',url=EIS.replace('.docx','.pdf'))))
    def test_filename_header_and_real_office(self):
        data=word('Реестровый BIOS: обязательно')
        result=fetch_official_document(EIS,FakeOpener(FakeResponse(data,disposition='attachment; filename="ТЗ.docx"')))
        self.assertEqual(result[0],'ТЗ.docx');self.assertEqual(result[1],data)


class TestEisFileImport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory(prefix='qx_eis_import_test_')
        cls.original=(store.APP_DATA,store.DB_FILE,store.DOCUMENTS,store._INITIALIZED)
        store.APP_DATA=Path(cls.tmp.name)
        store.DB_FILE=store.APP_DATA/'tenders.sqlite3'
        store.DOCUMENTS=store.APP_DATA/'tender_documents'
        store._INITIALIZED=False
        store.initialize()
        cls.client=TestClient(app)

    @classmethod
    def tearDownClass(cls):
        store.APP_DATA,store.DB_FILE,store.DOCUMENTS,store._INITIALIZED=cls.original
        cls.tmp.cleanup()

    def test_document_import_and_contract_analysis(self):
        tid=store.create({'title':'ЕИС импорт'})['id']
        reply=FakeResponse(word('Реестровый BIOS должен присутствовать в составе комплекта оборудования.'))
        result=import_official_document(tid,EIS,opener=FakeOpener(reply))
        self.assertEqual(len(result['documents']),1)
        self.assertEqual(result['source'],'zakupki.gov.ru (ссылка пользователя)')
        self.assertEqual(store.document_bytes(tid,result['document_id'])[1][:2], b'PK')

    def test_zip_import(self):
        tid=store.create({'title':'ЕИС пакет'})['id']
        u=EIS.replace('.docx','.zip')
        zipdata=bundle('tech-requirements.txt','Реестровый BIOS необходим'.encode('utf-8'))
        result=import_official_document(tid,u,opener=FakeOpener(FakeResponse(zipdata,url=u)))
        self.assertEqual(len(result['documents']),1)
        self.assertEqual(len(result['imported']),1)

    def test_api_rejects_untrusted_link(self):
        tid=store.create({'title':'ЕИС ссылка'})['id']
        response=self.client.post(f'/api/tenders/{tid}/eis/document-from-url',json={'url':'http://127.0.0.1/private'})
        self.assertEqual(response.status_code,422)
        self.assertEqual(store.detail(tid)['documents'],[])

    def test_api_uses_worker_and_keeps_contract_unmodified(self):
        tid=store.create({'title':'ЕИС ссылка','status':'Черновик'})['id']
        fake={'imported':['ТЗ.docx'],'message':'Добавлено'}
        with patch('modern.eis_document_download.import_official_document',return_value=fake) as m:
            response=self.client.post(f'/api/tenders/{tid}/eis/document-from-url',json={'url':EIS})
        self.assertEqual(response.status_code,200)
        self.assertEqual(m.call_args.args,(tid,EIS))
        self.assertEqual(store.get(tid)['status'],'Черновик')

if __name__=='__main__':unittest.main()
