"""No model guesses or automatic contract edits; evidence-backed opt-in fills only."""
import tempfile
from pathlib import Path
import unittest
from io import BytesIO
from docx import Document
from fastapi.testclient import TestClient
from modern import tender_store as store
from modern.tender_analysis import analyze_documents,extract_suggestions
from modern.server import app

def doc(*parts):
    d=Document()
    for p in parts:d.add_paragraph(p)
    b=BytesIO();d.save(b);return b.getvalue()

class SuggestedFieldsSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='qx_analysis_')
        cls.old=(store.APP_DATA,store.DB_FILE,store.DOCUMENTS,store._INITIALIZED)
        store.APP_DATA=Path(cls.temp.name);store.DB_FILE=store.APP_DATA/'tenders.sqlite3'
        store.DOCUMENTS=store.APP_DATA/'docs';store._INITIALIZED=False;store.initialize()
        cls.client=TestClient(app)
    @classmethod
    def tearDownClass(cls):
        store.APP_DATA,store.DB_FILE,store.DOCUMENTS,store._INITIALIZED=cls.old
        cls.temp.cleanup()

    def test_01_source_backed_proposal(self):
        d=doc('Срок поставки: 30 календарных дней с даты заключения контракта.',
              'Место поставки: г. Нижний Новгород, ул. Обухова, 11',
              'Оплата в течение 7 рабочих дней после приёмки.')
        a=analyze_documents([('Контракт.docx',d)])
        values={x['field']:x['value'] for x in a['suggested_fields']}
        self.assertEqual(values['due_days'],30)
        self.assertEqual(values['due_unit'],'calendar')
        self.assertIn('Нижний Новгород',values['supply_address'])
        self.assertIn('Оплата',values['payment_terms'])
        self.assertTrue(all(x['evidence']['file']=='Контракт.docx' for x in a['suggested_fields']))

    def test_02_conflicting_term_not_proposed(self):
        a=analyze_documents([('Основной.docx',doc('Срок поставки: 30 календарных дней с даты заключения контракта.')),
                              ('Изменение.docx',doc('Срок поставки: 15 календарных дней с даты заключения контракта.'))])
        fields=[x['field'] for x in a['suggested_fields']]
        self.assertNotIn('due_days',fields)

    def test_03_unknown_term_not_guessed(self):
        a=analyze_documents([('ТЗ.docx',doc('Поставка согласно календарному плану.'))])
        self.assertFalse(a['suggested_fields'])

    def test_04_user_approval_not_overwrite(self):
        t=store.create({'title':'Тест','supply_address':'Склад пользователя'})
        docbuf=doc('Срок поставки: 20 рабочих дней с даты заключения контракта.',
                   'Место поставки: г. Москва, ул. Примерная, 1')
        store.add_document(t['id'],'Условия.docx',docbuf)
        before=store.get(t['id'])
        self.assertEqual(before['due_days'],0)
        # Analysis alone must not silently mutate the tender.
        a=self.client.post(f'/api/tenders/{t["id"]}/analyze',json={})
        self.assertEqual(a.status_code,200)
        self.assertEqual(store.get(t['id'])['due_days'],0)
        r=self.client.post(f'/api/tenders/{t["id"]}/apply-suggestions',json={'fields':['due_days','due_unit','supply_address']})
        self.assertEqual(r.status_code,200,r.text)
        after=store.get(t['id'])
        self.assertEqual(after['due_days'],20)
        self.assertEqual(after['due_unit'],'work')
        self.assertEqual(after['supply_address'],'Склад пользователя')
        self.assertIn('supply_address',r.json()['skipped'])
        r=self.client.post(f'/api/tenders/{t["id"]}/apply-suggestions',json={'fields':['contract_price']})
        self.assertEqual(r.status_code,400)

if __name__=='__main__':unittest.main()
