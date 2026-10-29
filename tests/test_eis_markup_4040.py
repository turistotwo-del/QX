"""Sourced-layout regressions and complete network-to-storage fixtures (no live EIS)."""
import html
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.parse import quote

from docx import Document
from modern import tender_store as store
from modern.eis_public import parse_notice_metadata, extract_xml_document_links, fetch_notice_metadata, official_search_url
from modern.eis_metadata import parse_notice_html, fetch_notice_html_metadata
from modern.eis_resolver import extract_notice_urls, is_notice_context
from modern.eis_discovery import discover_public_documents, discover_and_import, extract_page_links
from modern.eis_document_download import fetch_official_document, import_downloaded_document

FIXTURES=Path(__file__).parent/'fixtures/eis'
NUMBER='0325100013726000029'
CARD='https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber='+NUMBER
DOCS=CARD.replace('common-info.html','documents.html')
FILE='https://zakupki.gov.ru/44fz/filestore/public/1.0/download/priz/file.html?uid=11111111-1111-4111-8111-111111111111'
PDF='https://zakupki.gov.ru/epz/filestore/public/1.0/download/priz/file.html?uid=22222222-2222-4222-8222-222222222222'


def word():
    doc=Document();doc.add_paragraph('Память 16 ГБ. Гарантия 36 месяцев.')
    stream=BytesIO();doc.save(stream);return stream.getvalue()


class Reply:
    def __init__(self,url,payload,mime='text/html',disposition=''):
        self.url=url;self.stream=BytesIO(payload);self.headers={'Content-Type':mime}
        if disposition:self.headers['Content-Disposition']=disposition
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def geturl(self):return self.url
    def read(self,n=-1):return self.stream.read(n)


class Site:
    def __init__(self,mapping):self.mapping=mapping;self.calls=[]
    def open(self,request,timeout):
        self.calls.append(request.full_url)
        if request.full_url not in self.mapping:raise HTTPError(request.full_url,404,'Not Found',{},None)
        values=self.mapping[request.full_url]
        if isinstance(values,Exception):raise values
        return Reply(request.full_url,*values)


class RealisticMarkup(unittest.TestCase):
    def test_main_card_plain_spans_price_and_date(self):
        result=parse_notice_html((FIXTURES/'notice44_card.html').read_bytes(),NUMBER)
        self.assertEqual(result['title'],'Поставка компьютерного оборудования')
        self.assertEqual(result['customer'],'Тестовый заказчик')
        self.assertEqual(result['nmck'],'120000.00')
        self.assertEqual(result['application_due_on'],'2026-11-20')
        self.assertNotIn('application_due_time',result) # explicit zone cannot fit naive schema

    def test_search_exact_number_and_shared_opener_follow_typed_documents(self):
        site=Site({official_search_url(NUMBER):((FIXTURES/'search_card.html').read_bytes(),),
                   CARD:((FIXTURES/'notice44_card.html').read_bytes(),),
                   DOCS:((FIXTURES/'documents44.html').read_bytes(),)})
        result=discover_public_documents(NUMBER,opener=site)
        self.assertEqual(site.calls,[official_search_url(NUMBER),CARD,DOCS])
        self.assertEqual([item['url'] for item in result['documents']],[FILE,PDF])
        self.assertTrue(result['complete'])
        self.assertEqual(result['errors'],[])

    def test_metadata_uses_same_resolved_card_for_injected_session(self):
        site=Site({official_search_url(NUMBER):((FIXTURES/'search_card.html').read_bytes(),),
                   CARD:((FIXTURES/'notice44_card.html').read_bytes(),)})
        result=fetch_notice_html_metadata(NUMBER,opener=site)
        self.assertTrue(result['available'])
        self.assertEqual(result['source_url'],CARD)

    def test_id_link_needs_exact_number_search_card_binding(self):
        url='https://zakupki.gov.ru/223/purchase/public/purchase/info/common-info.html?noticeInfoId=12345'
        markup=f'<div class="search-registry-entry-block">№32612345678<a href="{url}">Подробнее</a></div>'.encode()
        self.assertEqual(extract_notice_urls(markup,'https://zakupki.gov.ru/','32612345678'),[url])
        self.assertFalse(is_notice_context(url,'32612345678'))
        self.assertTrue(is_notice_context(url,'32612345678',bound_urls=[url]))
        self.assertEqual(extract_notice_urls(markup,'https://zakupki.gov.ru/','32612345679'),[])

    def test_explicit_download_attribute_is_safe_and_not_executed(self):
        data=f'<button data-download-url="{FILE}">ТЗ.docx</button><button data-url="https://127.0.0.1/a.pdf">bad</button>'.encode()
        records,_=extract_page_links(data,CARD,NUMBER)
        self.assertEqual([r['url'] for r in records],[FILE])

    def test_real_223_schema_fields_and_source_attachment_links(self):
        xml=(FIXTURES/'notice223.xml').read_bytes()
        info=parse_notice_metadata(xml,'32612345678')
        self.assertEqual(info['customer'],'Тестовый заказчик 223-ФЗ')
        self.assertEqual(info['title'],'Поставка оборудования: тестовая карточка')
        docs=extract_xml_document_links(xml,'32612345678')
        self.assertEqual(len(docs),1)
        self.assertEqual(docs[0]['url'],'https://zakupki.gov.ru/223/purchase/public/download/download.html?id=12345678')
        with self.assertRaises(ValueError):extract_xml_document_links(xml,'32612345679')

    def test_xml_html_pre_wrapper_and_fetch_returns_attachments(self):
        xml=(f'<n><purchaseNumber>{NUMBER}</purchaseNumber><purchaseName>Тест</purchaseName>'
             f'<attachments><attachment><fileName>ТЗ.docx</fileName><url>{FILE}</url></attachment></attachments></n>')
        wrapped=('<html><body><pre>'+html.escape(xml)+'</pre></body></html>').encode()
        url='https://zakupki.gov.ru/epz/order/notice/printForm/viewXml.html?regNumber='+NUMBER
        result=fetch_notice_metadata(NUMBER,opener=Site({url:(wrapped,'text/html')}))
        self.assertTrue(result['available'])
        self.assertEqual(result['documents'][0]['url'],FILE)

    def test_http_status_survives_failed_resolution(self):
        search=official_search_url(NUMBER)
        result=fetch_notice_html_metadata(NUMBER,opener=Site({search:HTTPError(search,403,'Forbidden',{},None)}))
        self.assertFalse(result['available'])
        self.assertIn('HTTP403',result['errors'])


class DownloadHeaders(unittest.TestCase):
    def test_opaque_archive_endpoints_keep_original_type(self):
        from modern.attachment_formats import RAR_SIGNATURES, SEVEN_Z_SIGNATURE
        for signature,suffix,padding in [(RAR_SIGNATURES[0],'.rar',24),(SEVEN_Z_SIGNATURE,'.7z',26)]:
            payload=signature+b'\0'*padding
            name,data=fetch_official_document(FILE,Site({FILE:(payload,'application/octet-stream')}))
            self.assertTrue(name.endswith(suffix))
            self.assertEqual(data,payload)

    def test_rfc5987_filename_takes_precedence(self):
        disposition='attachment; filename="download"; filename*=UTF-8\'\''+quote('Описание закупки.docx')
        name,data=fetch_official_document(FILE,Site({FILE:(word(),'application/octet-stream',disposition)}))
        self.assertEqual(name,'Описание закупки.docx')
        self.assertTrue(data.startswith(b'PK'))

    def test_mojibake_utf8_latin1_header(self):
        filename='Техническое задание.docx'.encode('utf-8').decode('latin-1')
        name,_=fetch_official_document(FILE,Site({FILE:(word(),'application/octet-stream','attachment; filename="'+filename+'"')}))
        self.assertEqual(name,'Техническое задание.docx')

    def test_opaque_endpoint_without_filename_uses_verified_content(self):
        name,data=fetch_official_document(FILE,Site({FILE:(word(),'application/octet-stream')}))
        self.assertTrue(name.endswith('.docx'))
        self.assertTrue(data.startswith(b'PK'))
        pdfname,pdf=fetch_official_document(PDF,Site({PDF:(b'%PDF-1.4\n%%EOF','application/octet-stream')}))
        self.assertTrue(pdfname.endswith('.pdf'))

    def test_opaque_login_page_is_rejected_even_with_pdf_mime(self):
        with self.assertRaisesRegex(ValueError,'страницу'):
            fetch_official_document(PDF,Site({PDF:(b'<html>Login</html>','application/pdf')}))


class FullDiscoveryStorage(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='qx_markup_')
        self.old=(store.APP_DATA,store.DB_FILE,store.DOCUMENTS,store._INITIALIZED)
        store.APP_DATA=Path(self.tmp.name);store.DB_FILE=store.APP_DATA/'tenders.sqlite3'
        store.DOCUMENTS=store.APP_DATA/'documents';store._INITIALIZED=False;store.initialize()
        self.tid=store.create({'number':NUMBER})['id']
    def tearDown(self):
        store.APP_DATA,store.DB_FILE,store.DOCUMENTS,store._INITIALIZED=self.old
        self.tmp.cleanup()

    def test_search_to_typed_documents_to_file_bytes_and_provenance(self):
        # The PDF failure is deliberate: successful DOCX survives and result stays partial.
        site=Site({official_search_url(NUMBER):((FIXTURES/'search_card.html').read_bytes(),),
                   CARD:((FIXTURES/'notice44_card.html').read_bytes(),),
                   DOCS:((FIXTURES/'documents44.html').read_bytes(),),
                   FILE:(word(),'application/octet-stream','attachment; filename="ТЗ.docx"')})
        result=discover_and_import(self.tid,opener=site)
        self.assertEqual(result['imported'],['ТЗ.docx'])
        self.assertEqual(result['failed_count'],1)
        self.assertFalse(result['complete'])
        doc=store.detail(self.tid)['documents'][0]
        self.assertTrue(store.document_bytes(self.tid,doc['id'])[1].startswith(b'PK'))
        self.assertTrue(any('автопоиск по номеру' in e['label'] for e in store.detail(self.tid)['events']))

    def test_secondary_adapter_storage_preserves_source_and_rejects_html(self):
        result=import_downloaded_document(self.tid,'ТЗ.docx',word(),source_label='Вторичный источник: тест')
        self.assertEqual(result['source'],'Вторичный источник: тест')
        with self.assertRaises(ValueError):
            import_downloaded_document(self.tid,'fake.docx',b'<html>error</html>',source_label='Вторичный источник: тест')


if __name__=='__main__':unittest.main()
