"""Cross-source orchestration with real parsing, attachment bytes and SQLite.

The procurement number is the user's failing example. HTML and DOCX below are
controlled fixtures, not captures or claims about that live procurement.
"""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from docx import Document
from modern import tender_store as store
from modern.eis_sync import sync_notice

NUMBER = '0325100013726000029'
PAGE = 'https://zakupki.kontur.ru/' + NUMBER
FILE = 'https://files.zakupki.kontur.ru/public/fixture.docx'


class Reply(BytesIO):
    def __init__(self, url, data, mime):
        super().__init__(data)
        self.url = url
        self.headers = {'Content-Type': mime}
    def geturl(self): return self.url


class Session:
    def __init__(self):
        document = Document()
        document.add_paragraph('Техническое задание: 10 компьютеров. Количество 10 шт.')
        output = BytesIO()
        document.save(output)
        self.document = output.getvalue()
        self.calls = []
    def open(self, request, timeout):
        self.calls.append(request.full_url)
        if request.full_url == PAGE:
            html = f'<main><h1>Закупка № {NUMBER}</h1><dl><dt>Предмет закупки</dt><dd>Поставка компьютеров</dd><dt>Заказчик</dt><dd>Контрольный заказчик</dd><dt>НМЦК</dt><dd>100000,00 ₽</dd></dl><a href="{FILE}">Техническое задание</a></main>'
            return Reply(PAGE, html.encode(), 'text/html; charset=utf-8')
        if request.full_url == FILE:
            return Reply(FILE, self.document, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        raise AssertionError('Unplanned external request')


class SecondaryPipeline(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in {'APP_DATA': root, 'DB_FILE': root/'tenders.sqlite3',
                            'DOCUMENTS': root/'documents', '_INITIALIZED': False}.items():
            patcher = patch.object(store, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        store.initialize()
        self.session = Session()
        for target, value in [
            ('modern.eis_sync.fetch_notice_metadata', {'available':False,'notice':None,'message':'HTTP 403'}),
            ('modern.eis_sync.fetch_notice_html_metadata', {'available':False,'notice':None,'message':'HTTP 403'}),
            ('modern.eis_sync.discover_and_import', {'found':0,'imported':[],'failed_count':0,'discovery_errors':['HTTP403']}),
            ('modern.eis_sync.create_secondary_session', SimpleNamespace(page=self.session, documents=self.session)),
        ]:
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_actual_number_falls_back_to_public_card_and_keeps_exact_doc_bytes(self):
        stages = []
        result = sync_notice(NUMBER, progress=lambda *stage: stages.append(stage[0]))
        self.assertEqual(result['tender']['number'], NUMBER)
        self.assertEqual(result['tender']['title'], 'Поставка компьютеров')
        self.assertIn('Контур', result['metadata_source'])
        self.assertFalse(result['partial'])
        self.assertEqual(len(result['tender']['documents']), 1)
        document = result['tender']['documents'][0]
        self.assertEqual(store.document_bytes(result['tender']['id'], document['id'])[1], self.session.document)
        self.assertEqual(self.session.calls, [PAGE, FILE])
        self.assertIn('fallback', stages)
        self.assertTrue(any('Контур' in event['label'] for event in result['tender']['events']))
        repeated = sync_notice(NUMBER)
        self.assertEqual(repeated['tender']['id'], result['tender']['id'])
        self.assertEqual(len(store.listing()), 1)
        self.assertEqual(len(repeated['tender']['documents']), 1)

    def test_secondary_never_overwrites_manual_fields(self):
        card = store.create({'number':NUMBER, 'customer':'Мой заказчик', 'nmck':500})
        result = sync_notice(NUMBER, tender_id=card['id'])
        self.assertEqual(result['tender']['customer'], 'Мой заказчик')
        self.assertEqual(result['tender']['nmck'], 500)
        self.assertIn('customer', {row['field'] for row in result['conflicts']})

    def test_metadata_only_never_fetches_secondary_attachment(self):
        result = sync_notice(NUMBER, download_documents=False)
        self.assertTrue(result['metadata_available'])
        self.assertIsNone(result['documents_result'])
        self.assertEqual(self.session.calls, [PAGE])
