from __future__ import annotations
from datetime import date,datetime
from pathlib import Path
from io import BytesIO
import tempfile, unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from docx import Document
from modern import tender_store as store, reminders
from modern.contract_autofill import extract, blank_fields
from modern.server import app
from core.project_io import dump_project


def make_doc(*paragraphs):
    d=Document()
    for line in paragraphs:d.add_paragraph(line)
    stream=BytesIO();d.save(stream);return stream.getvalue()

class ContractTests4036(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='qx4036_')
        self.old=(store.APP_DATA,store.DB_FILE,store.DOCUMENTS,store._INITIALIZED)
        store.APP_DATA=Path(self.tmp.name)
        store.DB_FILE=store.APP_DATA/'tenders.sqlite3'
        store.DOCUMENTS=store.APP_DATA/'docs'
        store._INITIALIZED=False
        store.initialize()
        self.client=TestClient(app)
    def tearDown(self):
        store.APP_DATA,store.DB_FILE,store.DOCUMENTS,store._INITIALIZED=self.old
        self.tmp.cleanup()

    def test_project_file_import_does_not_require_open_workspace(self):
        t=store.create({'title':'Моноблоки','status':'Выиграли'})
        raw=dump_project(reqs=[{'quantity':3,'item_name':'Моноблок'}],
                plans=[{'req':{'quantity':3,'item_name':'Моноблок'},
                        'rows':[{'qty':1,'price':35000},{'qty':2,'price':2000}]}],
                project_meta={'name':'Складской расчёт'})
        path='/api/tenders/'+t['id']+'/projects/import'
        a=self.client.post(path,content=raw,headers={'X-File-Name':'test.qxproj'})
        self.assertEqual(a.status_code,200,a.text)
        self.assertEqual(a.json()['purchase_cost'],117000)
        self.assertEqual(store.get(t['id'])['purchase_cost'],117000)
        self.assertEqual(len(store.detail(t['id'])['projects']),1)
        self.assertEqual(len(store.detail(t['id'])['documents']),1)
        b=self.client.post(path,content=raw,headers={'X-File-Name':'test.qxproj'})
        self.assertEqual(b.status_code,200,b.text)
        self.assertEqual(store.get(t['id'])['purchase_cost'],117000)
        self.assertEqual(len(store.detail(t['id'])['projects']),1)
        self.assertEqual(self.client.post(path,content=b'{}',headers={'X-File-Name':'bad.qxproj'}).status_code,400)
        from modern.tender_backup import preview_archive
        archive=self.client.get('/api/tenders/backup')
        self.assertEqual(archive.status_code,200)
        inspected=preview_archive(archive.content)
        self.assertEqual(inspected['documents'],1)
        from modern.attachment_integrity import audit_attachments
        self.assertEqual(audit_attachments()['valid'],1)

    def test_contract_autofill_verified_blanks_only(self):
        t=store.create({'title':'Контракт','status':'Контракт подписан','warranty':'48 месяцев'})
        doc=make_doc('Срок поставки: в течение 25 рабочих дней со дня заключения Контракта.',
                     'Место поставки: Нижегородская область, г. Нижний Новгород, ул. Ленина, д. 5.',
                     'Гарантийный срок: 24 месяца с даты подписания акта приёмки.',
                     'Оплата в течение 7 рабочих дней после подписания документа о приёмке.')
        store.add_document(t['id'],'Контракт.docx',doc)
        with patch('modern.local_ai._lite_available',return_value=False):
            r=self.client.post('/api/tenders/'+t['id']+'/analyze-and-fill')
        self.assertEqual(r.status_code,200,r.text)
        data=r.json()
        self.assertIn('due_days',data['applied'])
        self.assertIn('supply_address',data['applied'])
        self.assertNotIn('warranty',data['applied'])
        current=store.get(t['id'])
        self.assertEqual(current['due_days'],25)
        self.assertEqual(current['due_unit'],'work')
        self.assertEqual(current['warranty'],'48 месяцев')
        self.assertIn('Нижний Новгород',current['supply_address'])
        with patch('modern.local_ai._lite_available',return_value=False):
            other=self.client.post('/api/tenders/'+t['id']+'/analyze-and-fill')
        self.assertEqual(other.json()['applied'],[])

    def test_conflicting_contracts_no_guess(self):
        a=make_doc('Гарантийный срок: 24 месяца.')
        b=make_doc('Гарантийный срок: 36 месяцев.')
        outcome=extract([('Договор 1.docx',a),('Договор 2.docx',b)])
        self.assertIn('warranty',outcome['disputed'])
        self.assertNotIn('warranty',[p['field'] for p in outcome['verified']])

    def test_auction_time_validation_and_milestones(self):
        t=store.create({'title':'Аукцион','status':'Подготовка заявки','auction_on':'2026-10-29','auction_time':'12:00'})
        self.assertEqual(store.get(t['id'])['auction_time'],'12:00')
        with self.assertRaises(ValueError):store.update(t['id'],{'auction_time':'27:99'})
        reminders.set_preferences(enabled=True)
        alerts=reminders.notification_candidates(now_at=datetime(2026,10,29,11,10))
        upcoming=[r for r in alerts if r['tender_id']==t['id'] and r['type']=='auction']
        self.assertEqual(len(upcoming),1)
        self.assertIn(':60m',upcoming[0]['id'])
        late=[r for r in reminders.notification_candidates(now_at=datetime(2026,10,29,11,50)) if r['tender_id']==t['id'] and r['type']=='auction']
        self.assertEqual(len(late),1)
        self.assertIn(':15m',late[0]['id'])
        past=[r for r in reminders.notification_candidates(now_at=datetime(2026,10,29,12,1)) if r['tender_id']==t['id'] and r['type']=='auction']
        self.assertEqual(past,[])

    def test_source_label_address_in_contract(self):
        doc=make_doc('Поставка товара осуществляется по адресу: Нижегородская область, г. Арзамас, ул. Карла Маркса, д. 12')
        outcome=extract([('Договор.docx',doc)])
        self.assertTrue(any(i['field']=='supply_address' for i in outcome['verified']))

    def test_ai_can_only_quote_an_existing_source(self):
        blob=make_doc('Гарантийный срок: 24 месяца. Место поставки: Нижегородская область, г. Арзамас.')
        # Artificial model claims a different city; must be rejected, not applied.
        fake='{"items":[{"field":"supply_address","line":0,"value":"Москва, Красная площадь, 1"}]}'
        with patch('modern.local_ai._lite_available',return_value=True),\
             patch('modern.local_ai._lite_answer',return_value=fake):
            found=extract([('Договор.docx',blob)],use_local_ai=True)
        self.assertFalse(any(x['value']=='Москва, Красная площадь, 1' for x in found['verified']))

    def test_manual_auction_status_not_changed_by_ai(self):
        d=extract([('Контракт.docx',make_doc('Срок поставки: в течение 15 календарных дней со дня заключения Контракта.'))])
        updates=blank_fields({'status':'Выиграли','due_unit':'calendar','due_days':0},d['verified'])
        self.assertEqual(updates['due_days'],15)
        self.assertNotIn('status',updates)
