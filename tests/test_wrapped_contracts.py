"""Contract clauses split across Word paragraphs / PDF lines are not silently lost."""
from io import BytesIO
import unittest
from unittest.mock import patch
from docx import Document
from modern import tender_analysis as ta


def make_docx(*paragraphs):
    d=Document()
    for line in paragraphs:d.add_paragraph(line)
    buffer=BytesIO();d.save(buffer);return buffer.getvalue()


class TestWrappedContracts(unittest.TestCase):
    def test_word_paragraph_deadline(self):
        doc=make_docx('Срок поставки:', '30 календарных дней с даты заключения контракта.')
        a=ta.analyze_documents([('Контракт.docx',doc)])
        fields={item['field']:item for item in a['suggested_fields']}
        self.assertEqual(fields['due_days']['value'],30)
        self.assertEqual(fields['due_unit']['value'],'calendar')
        self.assertIn('абзац 1 — абзац 2',fields['due_days']['evidence']['location'])

    def test_bios_evidence_split_across_paragraphs(self):
        doc=make_docx('Требования к BIOS:', 'Прошивка должна быть включена в реестр российского программного обеспечения.')
        a=ta.analyze_documents([('Контракт.docx',doc)])
        # Split fragments should be visible for manual review, not treated as verified actual registry status.
        self.assertEqual(a['bios']['status'],'Найдено требование к реестровому BIOS')
        self.assertIn('перенос строки',a['bios']['evidence'][0]['location'])

    def test_unrelated_paragraphs_not_joined(self):
        doc=make_docx('В составе поставки предусмотрен BIOS', 'Реестровый номер компьютера: 12345678')
        a=ta.analyze_documents([('Контракт.docx',doc)])
        self.assertNotEqual(a['bios']['status'],'Найдено требование к реестровому BIOS')

    def test_next_independent_heading_not_combined(self):
        doc=make_docx('Срок поставки:', 'Оплата: 7 рабочих дней после приёмки.')
        a=ta.analyze_documents([('Контракт.docx',doc)])
        self.assertFalse(any(x['field']=='due_days' for x in a['suggested_fields']))

    def test_pdf_page_line_source_anchors(self):
        class Page:
            def extract_text(self):return 'Срок поставки:\n20 рабочих дней с даты заключения контракта.'
        class Reader:
            def __init__(self,stream):self.pages=[Page()]
        with patch('pypdf.PdfReader',Reader):
            a=ta.analyze_documents([('Контракт.pdf',b'%PDF mock')])
        fields={x['field']:x for x in a['suggested_fields']}
        self.assertEqual(fields['due_days']['value'],20)
        self.assertIn('страница 1, строка 1 — страница 1, строка 2',fields['due_days']['evidence']['location'])

if __name__=='__main__':unittest.main()
