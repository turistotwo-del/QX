"""Regression: scan late pages/rows before sampling down to UI evidence budget."""
from io import BytesIO
import unittest
from unittest.mock import patch
from docx import Document
from modern.tender_analysis import analyze_documents, document_segments, MAX_SCAN_SEGMENTS


def make_docx(lines):
    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    fp = BytesIO()
    doc.save(fp)
    return fp.getvalue()


class LongContractTests(unittest.TestCase):
    def test_single_negation_between_many_bios_statements_stays_visible(self):
        # A one-in-thousands contrary clause MUST force manual review.
        lines=['Требуется реестровый BIOS российского производства.']*9100
        lines[4781]='Реестровый BIOS не требуется для данной позиции закупки.'
        result=analyze_documents([('Изменения.txt','\n'.join(lines).encode())])
        self.assertEqual(result['bios']['status'],'Требуется уточнение')
        self.assertTrue(any('строка 4782'==item['location'] for item in result['bios']['evidence']))

    def test_late_bios_requirement_not_lost(self):
        blob = ('Безусловное требование к обычной упаковке.\n'*4900 +
                'BIOS должен быть включён в реестр российского программного обеспечения.\n').encode()
        result = analyze_documents([('Контракт.txt', blob)])
        self.assertEqual(result['bios']['status'], 'Найдено требование к реестровому BIOS')
        self.assertEqual(result['bios']['evidence'][0]['location'], 'строка 4901')

    def test_wrapped_delivery_deadline_at_end(self):
        blob = ('Техническая информация.\n'*4500 +
                'Срок поставки:\n30 календарных дней с даты заключения контракта.\n').encode()
        result = analyze_documents([('Договор.txt', blob)])
        field = {x['field']:x for x in result['suggested_fields']}
        self.assertEqual(field['due_days']['value'], 30)
        self.assertIn('строка 4501 — строка 4502', field['due_days']['evidence']['location'])

    def test_late_bios_in_real_docx(self):
        lines = ['Условия контракта.']*3800 + ['Обязателен российский BIOS с записью в реестре российского ПО']
        result = analyze_documents([('ТЗ.docx', make_docx(lines))])
        self.assertIn('Найдено требование',result['bios']['status'])
        self.assertEqual(result['bios']['evidence'][0]['location'],'абзац 3801')

    def test_reestr_equipment_in_separate_table_cell_is_not_bios(self):
        lines = ['BIOS версии 1.5 | Реестровый номер готового компьютера 12345678']
        result = analyze_documents([('ТЗ.txt', '\n'.join(lines).encode())])
        self.assertNotIn('Найдено требование',result['bios']['status'])

    def test_reestr_equipment_in_separate_sentence_is_not_bios(self):
        blob = 'BIOS версии 1.5. Реестровый номер готового компьютера 12345678'.encode()
        result=analyze_documents([('Контракт.txt',blob)])
        self.assertNotIn('Найдено требование',result['bios']['status'])

    def test_pdf_end_pages_and_oversized_explicit_error(self):
        class Page:
            def __init__(self, i): self.i=i
            def extract_text(self):
                return 'Реестровый BIOS обязателен' if self.i == 80 else 'Сведения\n'*58
        class Reader:
            def __init__(self, stream): self.pages=[Page(i) for i in range(81)]
        with patch('pypdf.PdfReader', Reader):
            result=analyze_documents([('Контракт.pdf',b'%PDF mock')])
        self.assertIn('Найдено требование',result['bios']['status'])
        self.assertEqual(result['bios']['evidence'][0]['location'],'страница 81, строка 1')
        class HugeReader:
            def __init__(self, stream): self.pages=[Page(i) for i in range(251)]
        with patch('pypdf.PdfReader', HugeReader):
            result=analyze_documents([('Длинный.pdf',b'%PDF mock')])
        self.assertTrue(result['errors'])
        self.assertIn('Требуется уточнение',result['bios']['status'])
        self.assertEqual(result['files_analyzed'],0)

    def test_scanned_pdf_is_saved_but_not_declared_analyzed(self):
        class BlankPage:
            def extract_text(self): return ''
        class Reader:
            def __init__(self, stream): self.pages=[BlankPage()]
        with patch('pypdf.PdfReader', Reader):
            result=analyze_documents([('Скан контракта.pdf',b'%PDF mock')])
        self.assertEqual(result['files_analyzed'],0)
        self.assertEqual(len(result['errors']),1)
        self.assertIn('Требуется уточнение',result['bios']['status'])

    def test_scan_cap_explicit_error(self):
        blob=('Раздел\n'*(MAX_SCAN_SEGMENTS+1)).encode()
        result=analyze_documents([('Большой.txt',blob)])
        self.assertTrue(result['errors'])
        self.assertNotEqual(result['bios']['status'],'Требование не обнаружено в загруженных файлах')

if __name__=='__main__': unittest.main()
