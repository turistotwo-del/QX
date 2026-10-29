"""2026-10-23: QX tender opt-in, public XML, deadline, rebinding regression."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from modern import tender_store as db
from modern.eis_public import parse_notice_metadata, fetch_notice_metadata, validate_notice

NUM1='0322100002526000466'
NUM2='0373100104826000011'

class TenderWorkflows4034(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=(db.APP_DATA,db.DB_FILE,db.DOCUMENTS,db._INITIALIZED)
        db.APP_DATA=Path(self.tmp.name)
        db.DB_FILE=db.APP_DATA/'tenders.sqlite3'
        db.DOCUMENTS=db.APP_DATA/'documents'
        db._INITIALIZED=False
        db.initialize()
    def tearDown(self):
        db.APP_DATA,db.DB_FILE,db.DOCUMENTS,db._INITIALIZED=self.old
        self.tmp.cleanup()
    def test_11_digits_and_long_notices_can_link(self):
        for num in ('32500001234',NUM1):
            out=db.link_project('project-'+num, 'Пример', notice_number_override=num,cost=140)
            self.assertEqual(db.get(out['tender_id'])['number'],num)
        self.assertEqual(db.dashboard()['total'],2)
    def test_same_notice_does_not_duplicate_card(self):
        a=db.link_project('one','First',notice_number_override=NUM1,cost=100)
        b=db.link_project('two','Second',notice_number_override=NUM1,cost=150)
        self.assertEqual(a['tender_id'],b['tender_id'])
        self.assertEqual(db.get(a['tender_id'])['purchase_cost'],250)
    def test_switch_notice_recalculates_old_purchase(self):
        a=db.link_project('one','First',notice_number_override=NUM1,cost=500)
        db.link_project('two','Second',notice_number_override=NUM1,cost=300)
        b=db.link_project('one','First',notice_number_override=NUM2,cost=400)
        self.assertNotEqual(a['tender_id'],b['tender_id'])
        self.assertEqual(db.get(a['tender_id'])['purchase_cost'],300)
        self.assertEqual(db.get(b['tender_id'])['purchase_cost'],400)
    def test_deadline_time_and_rollback_on_invalid_input(self):
        t=db.create({'number':NUM1,'title':'Contract','application_due_on':'2026-11-12','application_due_time':'13:45'})
        self.assertEqual(db.get(t['id'])['application_due_time'],'13:45')
        with self.assertRaises(ValueError):
            db.update(t['id'],{'application_due_time':'25:00'})
        self.assertEqual(db.get(t['id'])['application_due_time'],'13:45')

class PublicEis4034(unittest.TestCase):
    def test_exact_notice_xml_and_unambiguous_fields(self):
        xml=('''<epNotice><purchaseNumber>0322100002526000466</purchaseNumber><purchaseName>Поставка моноблоков</purchaseName><customer><fullName>МБУ Заказчик</fullName></customer><maxPrice>100000.00</maxPrice><endDate>2026-10-30T12:30:00</endDate></epNotice>''').encode()
        info=parse_notice_metadata(xml,NUM1)
        self.assertEqual(info['customer'],'МБУ Заказчик')
        self.assertEqual(info['application_due_time'],'12:30')
        self.assertEqual(info['application_due_on'],'2026-10-30')
        self.assertEqual(info['nmck'],'100000.00')
        self.assertEqual(info['law'],'') # No false 44-FZ assertion
        with self.assertRaises(ValueError):
            parse_notice_metadata(xml,NUM2)
    def test_ambiguous_price_is_not_inferred(self):
        xml=f'<notice><purchaseNumber>{NUM1}</purchaseNumber><maxPrice>100</maxPrice><maxPrice>200</maxPrice></notice>'.encode()
        self.assertEqual(parse_notice_metadata(xml,NUM1)['nmck'],'')
    def test_bad_xml_and_invalid_notice_fail_closed(self):
        with self.assertRaises(ValueError):
            validate_notice('123')
        from io import BytesIO
        class Reply:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,n): return b'<html>denied</html>'
        class Opener:
            def open(self,*args,**kwargs): return Reply()
        r=fetch_notice_metadata(NUM1,opener=Opener())
        self.assertFalse(r['available'])
        self.assertIsNone(r['notice'])

if __name__=='__main__':unittest.main()
