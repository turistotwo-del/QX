"""Tests for deadline alerts and notification idempotence (no Windows toast necessary)."""
from datetime import date
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient
from modern import tender_store as store
from modern import reminders as rem
from modern.server import app

class ReminderSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='qx_reminders_')
        cls.old = (store.APP_DATA, store.DB_FILE, store.DOCUMENTS, store._INITIALIZED)
        store.APP_DATA = Path(cls.temp.name)
        store.DB_FILE = store.APP_DATA / 'tenders.sqlite3'
        store.DOCUMENTS = store.APP_DATA / 'docs'
        store._INITIALIZED = False
        store.initialize()
        cls.client=TestClient(app)

    @classmethod
    def tearDownClass(cls):
        store.APP_DATA,store.DB_FILE,store.DOCUMENTS,store._INITIALIZED=cls.old
        cls.temp.cleanup()

    def test_01_settings_default_optin(self):
        self.assertFalse(rem.preferences()['enabled'])
        self.assertEqual(rem.preferences()['advance_days'],7)
        with self.assertRaises(ValueError): rem.set_preferences(advance_days=100)

    def test_02_application_due_and_submission(self):
        x=store.create({'title':'Монитор','application_due_on':'2026-10-23','status':'Подготовка заявки'})
        events=rem.reminders(date(2026,10,21))
        self.assertEqual(len([a for a in events if a['tender_id']==x['id']]),1)
        store.update(x['id'],{'status':'Заявка подана'})
        self.assertFalse(any(a['tender_id']==x['id'] for a in rem.reminders(date(2026,10,21))))

    def test_03_contract_due_only_after_signing(self):
        x=store.create({'title':'Компьютеры','due_on':'2026-10-22','status':'Черновик'})
        self.assertFalse(any(a['tender_id']==x['id'] for a in rem.reminders(date(2026,10,21))))
        store.update(x['id'],{'signed_on':'2026-10-19','status':'Контракт подписан'})
        self.assertTrue(any(a['type']=='delivery' and a['tender_id']==x['id'] for a in rem.reminders(date(2026,10,21))))
        store.update(x['id'],{'is_delivered':True})
        self.assertFalse(any(a['type']=='delivery' and a['tender_id']==x['id'] for a in rem.reminders(date(2026,10,21))))

    def test_04_payment_only_if_unpaid(self):
        x=store.create({'title':'Клавиатуры','contract_price':100000,'paid_amount':30000,'payment_due_on':'2026-10-24','status':'Контракт подписан'})
        self.assertTrue(any(a['type']=='payment' and a['tender_id']==x['id'] for a in rem.reminders(date(2026,10,21))))
        store.update(x['id'],{'paid_amount':100000})
        self.assertFalse(any(a['type']=='payment' and a['tender_id']==x['id'] for a in rem.reminders(date(2026,10,21))))

    def test_05_shipment_completion(self):
        x=store.create({'title':'Моноблоки','status':'Отгружено'})
        sid=store.add_shipment(x['id'],{'name':'1-я партия','due_on':'2026-10-20','quantity':59})
        self.assertTrue(any(a['type']=='shipment' and a['days']==-1 for a in rem.reminders(date(2026,10,21))))
        store.update_shipment(x['id'],sid,{'delivered_on':'2026-10-21'})
        self.assertFalse(any(a['type']=='shipment' and a['tender_id']==x['id'] for a in rem.reminders(date(2026,10,21))))

    def test_06_delivery_once_with_fake_provider(self):
        store.create({'title':'Срочная заявка','status':'Подготовка заявки','application_due_on':'2026-10-23'})
        rem.set_preferences(enabled=True,advance_days=7)
        outputs=[]
        def fake(title,msg,icon): outputs.append((title,msg));return True
        r=rem.dispatch(today=date(2026,10,21),emit=fake)
        self.assertGreaterEqual(r['sent'],1)
        r2=rem.dispatch(today=date(2026,10,21),emit=fake)
        self.assertEqual(r2['sent'],0)
        self.assertEqual(len(outputs),r['sent'])
        rem.set_preferences(enabled=False)
        self.assertFalse(rem.dispatch(today=date(2026,10,21),emit=fake)['enabled'])

    def test_07_api_get_and_update(self):
        r=self.client.get('/api/tenders/reminders')
        self.assertEqual(r.status_code,200)
        self.assertIn('items',r.json())
        r=self.client.post('/api/tenders/reminders/settings',json={'enabled':True,'advance_days':3})
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['settings']['advance_days'],3)
        self.assertEqual(self.client.post('/api/tenders/reminders/settings',json={'advance_days':-1}).status_code,400)

    def test_08_no_phantom_deadlines(self):
        x=store.create({'title':'Без дат'})
        self.assertFalse(any(a['tender_id']==x['id'] for a in rem.reminders(date(2026,10,21))))

if __name__=='__main__': unittest.main()
