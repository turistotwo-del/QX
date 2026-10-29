"""Offline acceptance for one-number card filling and safe repeatable EIS intake."""
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QX_DATA_DIR', tempfile.mkdtemp(prefix='qx_eis_sync_boot_'))
from modern import tender_store as store
from modern.eis_sync import sync_notice
from modern.eis_metadata import parse_notice_html, fetch_notice_html_metadata
from modern.eis_discovery import discover_public_documents
from modern.eis_document_download import import_official_documents, fetch_official_document

NUMBER = '0322100002526000466'
URL = 'https://zakupki.gov.ru/44fz/filestore/spec.txt'


def metadata(**values):
    notice = {'number':NUMBER, 'verified':True, 'title':'Поставка компьютеров',
              'customer':'МБУ Заказчик', 'nmck':'120000.00', 'application_due_on':'2026-11-20'}
    notice.update(values)
    notice['fields_fetched'] = [key for key in notice if key not in ('number', 'verified')]
    return {'available':True, 'notice':notice,
            'source_url':'https://zakupki.gov.ru/epz/order/notice/printForm/viewXml.html?regNumber=' + NUMBER}


class TestSync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='qx_eis_sync_')
        self.old = (store.APP_DATA, store.DB_FILE, store.DOCUMENTS, store._INITIALIZED)
        store.APP_DATA = Path(self.tmp.name)
        store.DB_FILE = store.APP_DATA/'tenders.sqlite3'
        store.DOCUMENTS = store.APP_DATA/'documents'
        store._INITIALIZED = False
        store.initialize()

    def tearDown(self):
        store.APP_DATA, store.DB_FILE, store.DOCUMENTS, store._INITIALIZED = self.old
        self.tmp.cleanup()

    @patch('modern.eis_sync.fetch_notice_metadata', return_value=metadata())
    def test_fill_and_repeat_reuses_card_and_protects_manual_fields(self, fetch):
        first = sync_notice(NUMBER, download_documents=False)
        self.assertEqual(first['tender']['customer'], 'МБУ Заказчик')
        self.assertEqual(first['tender']['nmck'], 120000)
        store.update(first['tender']['id'], {'title':'Моё название', 'contract_price':100500})
        second = sync_notice(NUMBER, download_documents=False)
        self.assertEqual(second['tender']['id'], first['tender']['id'])
        self.assertEqual(second['tender']['title'], 'Моё название')
        self.assertEqual(second['tender']['contract_price'], 100500)
        self.assertEqual([c['field'] for c in second['conflicts']], ['title'])
        self.assertEqual(len(store.listing()), 1)
        self.assertEqual(second['tender']['status'], 'Черновик')
        self.assertEqual(second['fields_applied'], [])

    @patch('modern.eis_sync.fetch_notice_metadata', return_value=metadata())
    def test_simultaneous_requests_create_one_card(self, fetch):
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda _:sync_notice(NUMBER, download_documents=False), range(3)))
        self.assertEqual(len({r['tender']['id'] for r in results}), 1)
        self.assertEqual(len(store.listing()), 1)

    def test_other_tender_rejected_before_network(self):
        item = store.create({'number':'1111111111111111111'})
        with patch('modern.eis_sync.fetch_notice_metadata') as fetch:
            with self.assertRaises(ValueError):sync_notice(NUMBER, tender_id=item['id'])
            fetch.assert_not_called()

    @patch('modern.eis_sync.fetch_notice_metadata', return_value=metadata())
    def test_ambiguous_lots_require_explicit_card(self, fetch):
        store.create({'number':NUMBER,'lot':'1'})
        chosen = store.create({'number':NUMBER,'lot':'2'})
        with self.assertRaises(ValueError):sync_notice(NUMBER)
        result = sync_notice(NUMBER,tender_id=chosen['id'],download_documents=False)
        self.assertEqual(result['tender']['lot'],'2')

    @patch('modern.eis_sync.fetch_notice_metadata', return_value={'available':False})
    @patch('modern.eis_sync.fetch_notice_html_metadata', return_value=metadata())
    def test_html_fallback_independent_of_xml(self, html, xml):
        result = sync_notice(NUMBER, download_documents=False)
        self.assertTrue(result['metadata_available'])
        html.assert_called_once()

    def test_offline_draft_is_explicitly_partial(self):
        failure = {'available':False, 'notice':None, 'message':'Недоступно'}
        docs = {'found':0,'complete':False,'documents':[],'imported':[], 'duplicates':[], 'failed_count':0}
        with patch('modern.eis_sync.fetch_notice_metadata',return_value=failure), \
             patch('modern.eis_sync.fetch_notice_html_metadata',return_value=failure), \
             patch('modern.eis_sync.discover_and_import',return_value=docs):
            result = sync_notice(NUMBER)
        self.assertFalse(result['metadata_available'])
        self.assertTrue(result['partial'])
        self.assertEqual(result['tender']['number'],NUMBER)
        self.assertEqual(result['tender']['title'],'')

    def test_documents_repeat_is_deduplicated_by_content(self):
        details = {'notice_number':NUMBER,'documents':[{'url':URL}], 'found':1,'complete':True}
        with patch('modern.eis_sync.fetch_notice_metadata',return_value=metadata()), \
             patch('modern.eis_discovery.discover_for_tender',return_value=details), \
             patch('modern.eis_document_download.fetch_official_document',return_value=('spec.txt','ТЗ: память 16 ГБ'.encode())):
            first = sync_notice(NUMBER)
            second = sync_notice(NUMBER)
        self.assertEqual(len(first['documents_result']['imported']),1)
        self.assertEqual(second['documents_result']['imported'],[])
        self.assertEqual(second['documents_result']['duplicates'],['spec.txt'])
        self.assertEqual(len(second['tender']['documents']),1)

    def test_partial_document_failure_keeps_success(self):
        item = store.create({'number':NUMBER})
        def download(url, opener=None):
            if url.endswith('bad.txt'):raise ValueError('Документ недоступен')
            return 'spec.txt', b'Memory 16 GB'
        with patch('modern.eis_document_download.fetch_official_document', side_effect=download):
            result = import_official_documents(item['id'], [URL, URL.replace('spec.txt','bad.txt')])
        self.assertEqual(result['success_count'],1)
        self.assertEqual(result['failed_count'],1)
        self.assertEqual(len(store.detail(item['id'])['documents']),1)

    def test_download_budget_stops_remaining_requests(self):
        item = store.create({'number':NUMBER})
        with patch('modern.eis_document_download.MAX_BATCH_SECONDS',0), \
             patch('modern.eis_document_download.fetch_official_document') as fetch:
            result = import_official_documents(item['id'],[URL])
        self.assertTrue(result['limit_reached'])
        self.assertEqual(result['failed_count'],1)
        fetch.assert_not_called()

    def test_source_time_is_not_attached_to_manual_other_date(self):
        item = store.create({'number':NUMBER, 'application_due_on':'2026-11-21'})
        with patch('modern.eis_sync.fetch_notice_metadata', return_value=metadata(application_due_time='12:30')):
            result = sync_notice(NUMBER,tender_id=item['id'],download_documents=False)
        self.assertEqual(result['tender']['application_due_on'],'2026-11-21')
        self.assertEqual(result['tender']['application_due_time'],'')
        self.assertIn('application_due_time',[c['field'] for c in result['conflicts']])


class TestHtmlFacts(unittest.TestCase):
    def html(self, number=NUMBER):
        return (f'<h1>Закупка {number}</h1>'
                '<section class="blockInfo__section"><span class="section__title">Наименование объекта закупки</span><div class="section__info">Поставка ПК</div></section>'
                '<section class="blockInfo__section"><span class="section__title">Заказчик</span><div class="section__info">МБУ Школа</div></section>'
                '<section class="blockInfo__section"><span class="section__title">Начальная (максимальная) цена контракта</span><div class="section__info">120 000,50 ₽</div></section>'
                '<section class="blockInfo__section"><span class="section__title">Дата и время окончания срока подачи заявок</span><div class="section__info">20.11.2026 09:30 (МСК)</div></section>').encode()

    def test_explicit_fields_and_number(self):
        result = parse_notice_html(self.html(),NUMBER)
        self.assertEqual(result['nmck'],'120000.50')
        self.assertEqual(result['customer'],'МБУ Школа')
        self.assertEqual(result['application_due_on'],'2026-11-20')
        self.assertNotIn('application_due_time',result)
        self.assertNotIn('contract_price',result)
        self.assertNotIn('status',result)

    def test_hidden_number_and_wrong_number_fail(self):
        for page in (self.html('9999999999999999999'),self.html('9999999999999999999') + ('<script>'+NUMBER+'</script>').encode()):
            with self.assertRaises(ValueError):parse_notice_html(page,NUMBER)

    def test_223_number_is_supported_by_labelled_html(self):
        result = parse_notice_html(self.html('32612345678'),'32612345678')
        self.assertEqual(result['number'],'32612345678')

    def test_time_without_zone_is_retained(self):
        result = parse_notice_html(self.html().replace('(МСК)'.encode(),b''),NUMBER)
        self.assertEqual(result['application_due_time'],'09:30')

    def test_resolver_uses_exact_existing_typed_url(self):
        from modern.eis_resolver import extract_notice_urls
        typed = 'https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=' + NUMBER
        content = (f'<a href="{typed}">Закупка</a><a href="{typed}0">Другой номер</a>'
                   f'<a href="https://evil.test/a?regNumber={NUMBER}">Чужой сайт</a>').encode()
        self.assertEqual(extract_notice_urls(content,'https://zakupki.gov.ru/',NUMBER),[typed])

    def test_xml_multiple_notice_numbers_are_not_merged(self):
        from modern.eis_public import parse_notice_metadata
        xml = (f'<export><purchaseNumber>{NUMBER}</purchaseNumber>'
               '<purchaseNumber>9999999999999999999</purchaseNumber><purchaseName>Поставка</purchaseName></export>').encode()
        with self.assertRaises(ValueError):parse_notice_metadata(xml,NUMBER)

    def test_xml_bad_clock_does_not_break_valid_date(self):
        from modern.eis_public import parse_notice_metadata
        xml = (f'<notice><purchaseNumber>{NUMBER}</purchaseNumber>'
               '<endDate>2026-11-20T25:90:00</endDate></notice>').encode()
        result = parse_notice_metadata(xml,NUMBER)
        self.assertEqual(result['application_due_on'],'2026-11-20')
        self.assertEqual(result['application_due_time'],'')


if __name__ == '__main__':unittest.main()
