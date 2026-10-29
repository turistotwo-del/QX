"""4.0.38 regression tests: EIS discovery, deletion, data safety and new-project warning."""
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QX_DATA_DIR', tempfile.mkdtemp(prefix='qx4038_test_'))
from fastapi.testclient import TestClient
from modern import tender_store as store
from modern.server import app
from modern.eis_discovery import extract_page_links, discover_public_documents, discover_and_import

NOTICE = '0322100002526000466'
PAGE = 'https://zakupki.gov.ru/epz/order/notice/view/common-info.html?regNumber='+NOTICE
DOC_PAGE = 'https://zakupki.gov.ru/epz/order/notice/ea20/view/documents.html?regNumber='+NOTICE
FILE = 'https://zakupki.gov.ru/44fz/filestore/contract.pdf'

class Page:
    def __init__(self, text, url):
        self.body = BytesIO(text.encode('utf-8'))
        self.url = url
        self.headers = {'Content-Type': 'text/html; charset=utf-8'}
    def read(self, n=-1): return self.body.read(n)
    def geturl(self): return self.url
    def __enter__(self): return self
    def __exit__(self,*a): return False

class Pages:
    def __init__(self, mapping):self.mapping = mapping;self.calls=[]
    def open(self,request,timeout):
        url=request.full_url
        self.calls.append(url)
        return Page(self.mapping[url], url)

class TestEisDiscovery(unittest.TestCase):
    def test_discovers_only_official_file_links(self):
        contents = f'''<main>№ {NOTICE}
          <a href="/epz/order/notice/ea20/view/documents.html?regNumber={NOTICE}">Документы</a>
          <a href="https://not-zakupki.gov.ru/evil.pdf">Сторонний документ</a>
          <a href="https://127.0.0.1/private.pdf">Мой сервер</a></main>'''
        other = f'''<h1>№ {NOTICE}</h1>
           <a href="/44fz/filestore/contract.pdf">Проект контракта</a>
           <a href="/epz/order/notice/ea20/view/documents.html?regNumber=9999999999999999999">Чужая закупка</a>'''
        op = Pages({PAGE:contents, DOC_PAGE:other})
        r=discover_public_documents(NOTICE,opener=op)
        self.assertTrue(r['available'])
        self.assertEqual(len(r['documents']),1)
        self.assertEqual(r['documents'][0]['url'],FILE)
        self.assertEqual(r['checked_pages'],2)
        self.assertEqual(len(op.calls),2)
    def test_excludes_unsafe_links(self):
        body = f'''<span>{NOTICE}</span><a href="https://zakupki.gov.ru.evil.org/a.pdf">bad</a>
                  <a href="http://zakupki.gov.ru/a.docx">http</a>
                  <a href="javascript:alert(1)">JS</a>
                  <a href="/44fz/filestore/%2e%2e/secret.docx">Traversal</a>'''
        docs, _=extract_page_links(body.encode(),PAGE,NOTICE)
        self.assertEqual(docs,[])
    def test_error_or_captcha_never_fakes_documents(self):
        r=discover_public_documents(NOTICE,opener=Pages({PAGE:'<html>Captcha required</html>'}))
        self.assertFalse(r['available'])
        self.assertEqual(r['documents'],[])
    def test_exact_notice_validation(self):
        with self.assertRaises(ValueError):discover_public_documents('127.0.0.1')
        with self.assertRaises(ValueError):discover_public_documents('1'*500)
    def test_download_after_discovery_only_once(self):
        with patch('modern.eis_discovery.tender_store.get',return_value={'number':NOTICE}),patch('modern.eis_discovery.import_official_documents',return_value={'imported':['doc.pdf'],'success_count':1}) as download:
            result=discover_and_import('t1',discovered={'notice_number':NOTICE,'documents':[{'url':FILE}],'found':1})
        self.assertEqual(result['imported'],['doc.pdf'])
        download.assert_called_once_with('t1',[FILE],opener=None)
    def test_not_import_other_notice(self):
        with patch('modern.eis_discovery.tender_store.get',return_value={'number':NOTICE}):
            with self.assertRaises(ValueError):discover_and_import('t1',discovered={'notice_number':'1'*19,'documents':[{'url':FILE}]})

class TestShipmentActions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='qx_ship38_')
        cls.original=(store.APP_DATA,store.DB_FILE,store.DOCUMENTS,store._INITIALIZED)
        store.APP_DATA=Path(cls.tmp.name)
        store.DB_FILE=store.APP_DATA/'tenders.sqlite3'; store.DOCUMENTS=store.APP_DATA/'tender_documents'
        store._INITIALIZED=False;store.initialize()
        cls.client=TestClient(app)
    @classmethod
    def tearDownClass(cls):
        store.APP_DATA,store.DB_FILE,store.DOCUMENTS,store._INITIALIZED=cls.original
        cls.tmp.cleanup()
    def test_remove_only_target_stage_and_persist(self):
        tid=store.create({'title':'Поставка'})['id']
        stage1=store.add_shipment(tid,{'name':'Партия 1','quantity':12,'due_on':'2026-11-06'})
        stage2=store.add_shipment(tid,{'name':'Партия 2','quantity':20,'due_on':'2026-11-10'})
        r=self.client.delete(f'/api/tenders/{tid}/shipments/{stage1}')
        self.assertEqual(r.status_code,200)
        self.assertEqual([s['id'] for s in store.detail(tid)['shipments']],[stage2])
        self.assertEqual(len(store.detail(tid)['events'])>=1,True)
        self.assertEqual(self.client.delete(f'/api/tenders/{tid}/shipments/{stage1}').status_code,404)
        self.assertEqual(self.client.delete(f'/api/tenders/{store.create({"title":"Другой"})["id"]}/shipments/{stage2}').status_code,404)
        self.assertEqual([s['id'] for s in store.detail(tid)['shipments']],[stage2])
    def test_eis_api_uses_worker(self):
        tid=store.create({'title':'Интернет', 'number':NOTICE})['id']
        fake={'notice_number':NOTICE,'documents':[],'found':0,'message':'Нет данных'}
        with patch('modern.eis_discovery.discover_for_tender',return_value=fake) as fn:
            r=self.client.post(f'/api/tenders/{tid}/eis/discover')
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['found'],0)
        fn.assert_called_once_with(tid)
    def test_button_import_never_updates_contract(self):
        tid=store.create({'title':'Контракт','number':'1'*19,'warranty':'12 мес'})['id']
        with patch('modern.eis_discovery.discover_and_import',return_value={'imported':[]}) as fn:
            r=self.client.post(f'/api/tenders/{tid}/eis/discover-and-import')
        self.assertEqual(r.status_code,200)
        self.assertEqual(store.detail(tid)['warranty'],'12 мес')

class TestFrontEndMarkup(unittest.TestCase):
    def test_new_project_modal_and_stage_buttons_exist(self):
        js=(Path(__file__).parents[1]/'modern/web/app.js').read_text(encoding='utf-8')
        for text in ('unsaved-project','new-save-first', 'new-discard', 'tender-delete-stage', 'tender-eis-discover', 'Сначала нажми «Найти документы»'):
            self.assertIn(text,js)
        self.assertNotIn("'new': () => { if (state.reqs.length && !window.confirm",js)

if __name__=='__main__':unittest.main()
