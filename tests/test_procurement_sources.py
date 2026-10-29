"""Secondary page parser contracts; markup fixtures are not live-service evidence."""
from io import BytesIO
import unittest
from pathlib import Path
import tempfile
import os
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from modern.procurement_sources import (
    MAX_PAGE_BYTES, _KonturRedirects, kontur_page_url, lookup_secondary,
    parse_secondary_page, public_document_url,
    import_secondary_documents,
)

NUMBER = '0325100013726000029'
OTHER = '0325100013726000030'


def card(body='', number=NUMBER):
    return (f'''<!doctype html><html lang="ru"><head><meta property="og:title"
        content="Закупка №{number}: Поставка оборудования — Контур.Закупки"></head><body>
        <main><h1>Поставка оборудования</h1><div>Номер закупки: {number}</div>{body}</main>
        </body></html>''').encode()


class Response:
    def __init__(self, payload, url=None, mime='text/html; charset=utf-8'):
        self.payload = BytesIO(payload)
        self.url = url or kontur_page_url(NUMBER)
        self.headers = {'Content-Type':mime}
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def geturl(self): return self.url
    def read(self, limit): return self.payload.read(limit)


class Opener:
    def __init__(self, response=None, error=None):
        self.response, self.error = response, error
        self.calls = []
    def open(self, request, timeout):
        self.calls.append((request.full_url, timeout))
        if self.error: raise self.error
        return self.response


os.environ.setdefault('QX_DATA_DIR', tempfile.mkdtemp(prefix='qx_secondary_boot_'))

class SecondaryProcurementSources(unittest.TestCase):
    def test_labelled_card_metadata_and_explicit_provenance(self):
        parsed = parse_secondary_page(card('''
          <dl><dt>Заказчик</dt><dd>Тестовый заказчик</dd>
              <dt>НМЦК</dt><dd>1 250 000,50 ₽</dd>
              <dt>Приём заявок до</dt><dd>12.11.2026 10:30</dd>
              <dt>Закон</dt><dd>44-ФЗ</dd></dl>'''), NUMBER)
        self.assertTrue(parsed['available'])
        self.assertEqual(parsed['notice']['customer'], 'Тестовый заказчик')
        self.assertEqual(parsed['notice']['nmck'], '1250000.50')
        self.assertEqual(parsed['notice']['application_due_on'], '2026-11-12')
        self.assertEqual(parsed['notice']['application_due_time'], '10:30')
        self.assertEqual(parsed['notice']['law'], '44-ФЗ')
        self.assertEqual(parsed['notice']['verification'], 'exact_number_secondary')
        self.assertEqual(parsed['source_kind'], 'secondary')
        self.assertIn('вторичный', parsed['source_name'])

    def test_table_and_sibling_label_layouts(self):
        parsed = parse_secondary_page(card('''<table><tr><th>Заказчик:</th><td>Организация</td></tr></table>
          <section><div><span>Место поставки</span><span>Тестовый адрес поставки</span></div></section>'''), NUMBER)
        self.assertEqual(parsed['notice']['customer'], 'Организация')
        self.assertEqual(parsed['notice']['supply_address'], 'Тестовый адрес поставки')

    def test_source_identity_and_number_must_both_match(self):
        with self.assertRaises(ValueError): parse_secondary_page(card(number=OTHER), NUMBER)
        for url in ['https://zakupki.kontur.ru/' + OTHER,
                    'https://zakupki.kontur.ru/login', 'https://evil.test/' + NUMBER]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                parse_secondary_page(card(), NUMBER, url)

    def test_longer_similar_number_does_not_match(self):
        with self.assertRaises(ValueError):
            parse_secondary_page(card(number=NUMBER + '1'), NUMBER)

    def test_script_only_number_cannot_prove_card(self):
        payload = f'<h1>Вход</h1><script>const number="{NUMBER}";</script>'.encode()
        with self.assertRaises(ValueError): parse_secondary_page(payload, NUMBER)

    def test_ambiguous_customer_price_omitted_and_organizer_not_customer(self):
        parsed = parse_secondary_page(card('''
          <dl><dt>Заказчик</dt><dd>Первый</dd><dt>Заказчик</dt><dd>Второй</dd>
              <dt>НМЦК</dt><dd>100</dd><dt>НМЦК</dt><dd>200</dd>
              <dt>Организатор</dt><dd>Не заказчик</dd></dl>'''), NUMBER)
        self.assertNotIn('customer', parsed['notice'])
        self.assertNotIn('nmck', parsed['notice'])

    def test_currency_and_zone_not_silently_reinterpreted(self):
        parsed = parse_secondary_page(card('''<dl><dt>НМЦК</dt><dd>100 USD</dd>
          <dt>Приём заявок до</dt><dd>12.11.2026 10:30 (МСК+2)</dd></dl>'''), NUMBER)
        self.assertNotIn('nmck', parsed['notice'])
        self.assertEqual(parsed['notice']['application_due_on'], '2026-11-12')
        self.assertNotIn('application_due_time', parsed['notice'])

    def test_only_actual_public_supported_document_links_returned(self):
        parsed = parse_secondary_page(card('''
          <a href="https://zakupki.gov.ru/44fz/filestore/public/1.0/download/priz/file.docx">ТЗ</a>
          <a href="/files/contract.pdf">Контракт</a>
          <a href="https://files.zakupki.kontur.ru/public/uuid" download="Приложение.docx">Приложение</a>
          <a href="/files/contract.pdf">Повтор</a>
          <a href="https://zakupki.kontur.ru.evil.test/file.pdf">Посторонний сайт</a>
          <a href="http://127.0.0.1/internal.pdf">Локальный файл</a>
          <a href="https://example.org/file.pdf">Зеркало</a>
          <a href="/login">Вход</a>'''), NUMBER)
        self.assertEqual(len(parsed['documents']), 3)
        self.assertTrue(all(doc['source_page'] == kontur_page_url(NUMBER) for doc in parsed['documents']))
        self.assertEqual(parsed['documents'][1]['url'], 'https://zakupki.kontur.ru/files/contract.pdf')

    def test_document_url_guards(self):
        for url in ['https://zakupki.kontur.ru.evil.test/file.pdf',
                    'https://user:pass@zakupki.kontur.ru/file.pdf',
                    'https://files.zakupki.kontur.ru/%2e%2e/private.pdf',
                    'https://files.zakupki.kontur.ru:444/file.pdf',
                    'http://files.zakupki.kontur.ru/file.pdf']:
            with self.subTest(url=url), self.assertRaises(ValueError): public_document_url(url)

    def test_attachment_cap_is_reported(self):
        parsed = parse_secondary_page(card(''.join(f'<a href="/files/{i}.pdf">{i}</a>' for i in range(41))), NUMBER)
        self.assertEqual(len(parsed['documents']), 40)
        self.assertEqual(parsed['found'], 41)
        self.assertTrue(parsed['limit_reached'])

    def test_empty_or_oversized_rejected(self):
        for payload in [b'', b'x' * (MAX_PAGE_BYTES + 1)]:
            with self.assertRaises(ValueError): parse_secondary_page(payload, NUMBER)

    def test_soft_not_found_or_login_never_fakes_subject(self):
        payload = f'<h1>Страница не найдена</h1><span>{NUMBER}</span>'.encode()
        parsed = parse_secondary_page(payload, NUMBER)
        self.assertFalse(parsed['available'])
        self.assertIsNone(parsed['notice'])

    def test_fetch_contract_success_and_single_bounded_request(self):
        opener = Opener(Response(card()))
        fetched = lookup_secondary(NUMBER, opener=opener)
        self.assertTrue(fetched['available'])
        self.assertIn('вторичного', fetched['message'])
        self.assertEqual(opener.calls, [(kontur_page_url(NUMBER), 8)])

    def test_fetch_failures_are_explicit_without_leaking_error_content(self):
        for error in [HTTPError(kontur_page_url(NUMBER), 403, 'closed', {}, None),
                      URLError('private proxy token secret'), TimeoutError('secret')]:
            with self.subTest(error=type(error).__name__):
                fetched = lookup_secondary(NUMBER, opener=Opener(error=error))
                self.assertFalse(fetched['available'])
                self.assertEqual(fetched['documents'], [])
                self.assertEqual(fetched['error_type'], type(error).__name__)
                self.assertNotIn('secret', str(fetched))

    def test_fetch_rejects_final_login_wrong_notice_or_binary(self):
        for response in [Response(card(), 'https://zakupki.kontur.ru/login'),
                         Response(card(), kontur_page_url(OTHER)), Response(card(), mime='application/pdf')]:
            with self.subTest(url=response.url):
                self.assertFalse(lookup_secondary(NUMBER, opener=Opener(response))['available'])

    def test_redirect_handler_never_visits_login_or_other_purchase(self):
        from urllib.request import Request
        handler = _KonturRedirects(NUMBER)
        for url in ['https://zakupki.kontur.ru/login', kontur_page_url(OTHER), 'https://evil.test/doc']:
            with self.assertRaises(ValueError):
                handler.redirect_request(Request(kontur_page_url(NUMBER)), None, 302, 'redirect', {}, url)

    def test_public_json_ld_requires_own_exact_identifier(self):
        import json
        data = {'@context':'https://schema.org', '@type':'Product', 'identifier':NUMBER,
                'name':'Поставка компьютеров', 'offers':{'price':'100000.50','priceCurrency':'RUB'},
                'additionalProperty':[{'@type':'PropertyValue','name':'НМЦК','value':'100000.50 RUB'}],
                'associatedMedia':[{'name':'Техническое задание', 'contentUrl':'https://files.zakupki.kontur.ru/public/specification.docx'}]}
        payload = ('<h1>Поставка компьютеров</h1><script type="application/ld+json">' + json.dumps(data) + '</script>').encode()
        parsed = parse_secondary_page(payload, NUMBER)
        self.assertEqual(parsed['notice']['title'], 'Поставка компьютеров')
        self.assertEqual(parsed['notice']['nmck'], '100000.50')
        self.assertEqual(len(parsed['documents']), 1)
        data['identifier'] = OTHER
        payload = ('<script type="application/ld+json">' + json.dumps(data) + '</script>').encode()
        with self.assertRaises(ValueError): parse_secondary_page(payload, NUMBER)

    def test_json_ld_other_currency_does_not_become_rubles(self):
        import json
        data = {'@type':'Product', 'identifier':NUMBER, 'name':'Поставка компьютеров',
                'offers':{'price':100, 'priceCurrency':'USD'}, 'seller':{'name':'Это не заказчик'}}
        parsed = parse_secondary_page(('<script type="application/ld+json">' + json.dumps(data) + '</script>').encode(), NUMBER)
        self.assertNotIn('nmck', parsed['notice'])
        self.assertNotIn('customer', parsed['notice'])
        data['offers']['priceCurrency'] = 'RUB'
        parsed = parse_secondary_page(('<script type="application/ld+json">' + json.dumps(data) + '</script>').encode(), NUMBER)
        self.assertNotIn('nmck', parsed['notice'])


class SecondaryDocumentIntake(unittest.TestCase):
    def setUp(self):
        from modern import tender_store as store
        self.store = store
        self.directory = tempfile.TemporaryDirectory(prefix='qx_secondary_docs_')
        self.previous = (store.APP_DATA, store.DB_FILE, store.DOCUMENTS, store._INITIALIZED)
        store.APP_DATA = Path(self.directory.name)
        store.DB_FILE = store.APP_DATA / 'tenders.sqlite3'
        store.DOCUMENTS = store.APP_DATA / 'documents'
        store._INITIALIZED = False
        self.tender = store.create({'number':NUMBER})
        self.tid = self.tender['id']
        from docx import Document
        doc = Document()
        doc.add_paragraph('Техническое задание: требуется 10 компьютеров.')
        output = BytesIO()
        doc.save(output)
        self.payload = output.getvalue()

    def tearDown(self):
        self.store.APP_DATA, self.store.DB_FILE, self.store.DOCUMENTS, self.store._INITIALIZED = self.previous
        self.directory.cleanup()

    def item(self, url='https://files.zakupki.kontur.ru/public/document.docx'):
        return {'url':url, 'source_page':kontur_page_url(NUMBER), 'title':'ТЗ'}

    def response(self, url, payload=None, mime='application/octet-stream', headers=None):
        result = Response(payload if payload is not None else self.payload, url, mime)
        if headers: result.headers.update(headers)
        return result

    def test_actual_docx_storage_duplicate_and_source_audit(self):
        item = self.item('https://files.zakupki.kontur.ru/public/document.docx?token=do-not-log')
        first = import_secondary_documents(self.tid, [item], Opener(self.response(item['url'])))
        second = import_secondary_documents(self.tid, [item], Opener(self.response(item['url'])))
        self.assertEqual(first['imported'], ['document.docx'])
        self.assertEqual(second['imported'], [])
        self.assertEqual(second['duplicates'], ['document.docx'])
        documents = self.store.detail(self.tid)['documents']
        self.assertEqual(len(documents), 1)
        self.assertEqual(self.store.document_bytes(self.tid, documents[0]['id'])[1], self.payload)
        events = self.store.detail(self.tid)['events']
        self.assertTrue(any('Контур.Закупки' in row['label'] for row in events))
        self.assertNotIn('do-not-log', str(events))

    def test_opaque_download_name_inferred_from_genuine_office_container(self):
        item = self.item('https://files.zakupki.kontur.ru/public/uuid')
        result = import_secondary_documents(self.tid, [item], Opener(self.response(item['url'])))
        self.assertEqual(result['success_count'], 1)
        self.assertTrue(result['imported'][0].endswith('.docx'))

    def test_rfc5987_response_filename_preserved(self):
        item = self.item('https://files.zakupki.kontur.ru/public/uuid')
        response = self.response(item['url'], headers={'Content-Disposition':"attachment; filename=generic.bin; filename*=UTF-8''%D0%A2%D0%97.docx"})
        result = import_secondary_documents(self.tid, [item], Opener(response))
        self.assertEqual(result['imported'], ['ТЗ.docx'])

    def test_later_failure_retains_earlier_file_and_never_logs_signed_urls(self):
        good = self.item()
        bad = self.item('https://files.zakupki.kontur.ru/public/denied.docx?secret=keep-private')
        class Mixed:
            def open(inner, request, timeout):
                if 'denied' in request.full_url:
                    raise URLError(request.full_url)
                return self.response(good['url'])
        result = import_secondary_documents(self.tid, [good, bad], Mixed())
        self.assertEqual(result['success_count'], 1)
        self.assertEqual(result['failed_count'], 1)
        self.assertEqual(len(self.store.detail(self.tid)['documents']), 1)
        self.assertNotIn('keep-private', str(result))
        self.assertFalse(result['complete'])

    def test_login_html_disguised_or_executable_rejected(self):
        item = self.item()
        for data, mime in [(b'<html>Login</html>', 'application/octet-stream'),
                           (b'<html>Login</html>', 'text/html'),
                           (b'MZ' + b'x' * 512, 'application/octet-stream')]:
            result = import_secondary_documents(self.tid, [item], Opener(self.response(item['url'], data, mime)))
            self.assertEqual(result['failed_count'], 1)
        self.assertEqual(self.store.detail(self.tid)['documents'], [])

    def test_source_page_identity_and_destination_guard_before_network(self):
        invalid = [self.item('https://127.0.0.1/private.docx'),
                   {**self.item(), 'source_page':kontur_page_url(OTHER)},
                   {**self.item(), 'source_page':'https://evil.test/' + NUMBER}]
        opener = Opener()
        result = import_secondary_documents(self.tid, invalid, opener)
        self.assertEqual(result['failed_count'], 3)
        self.assertEqual(opener.calls, [])

    def test_redirect_to_other_host_and_oversized_file_rejected(self):
        item = self.item()
        for response in [self.response('https://evil.test/file.docx'),
                         self.response(item['url'], headers={'Content-Length':str(31 * 1024 * 1024)})]:
            result = import_secondary_documents(self.tid, [item], Opener(response))
            self.assertEqual(result['failed_count'], 1)
        self.assertEqual(self.store.detail(self.tid)['documents'], [])

    def test_aggregate_byte_and_time_limits_explicit(self):
        item = self.item()
        with patch('modern.procurement_sources.MAX_TOTAL_BYTES', 5):
            result = import_secondary_documents(self.tid, [item], Opener(self.response(item['url'])))
            self.assertTrue(result['limit_reached'])
            self.assertEqual(result['failed_count'], 1)
        with patch('modern.procurement_sources.MAX_DOWNLOAD_SECONDS', 0):
            opener = Opener()
            result = import_secondary_documents(self.tid, [item], opener)
            self.assertTrue(result['limit_reached'])
            self.assertEqual(opener.calls, [])

    def test_eis_link_discovered_by_secondary_uses_official_fetch_and_provenance(self):
        item = self.item('https://zakupki.gov.ru/44fz/filestore/specification.docx')
        result = import_secondary_documents(self.tid, [item], Opener(self.response(item['url'])))
        self.assertEqual(result['success_count'], 1)
        self.assertTrue(any('ссылка на файл ЕИС' in row['label'] for row in self.store.detail(self.tid)['events']))


if __name__ == '__main__':
    unittest.main()
