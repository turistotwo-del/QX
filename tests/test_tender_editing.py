"""Tests for editing and removal of locally stored tender content."""
import os
from pathlib import Path
import tempfile
import unittest

# Set before importing the store, so tests can never touch a real DB.
DIR = tempfile.TemporaryDirectory(prefix='qx_edit_test_')
os.environ['QX_DATA_DIR'] = DIR.name
from modern import tender_store as db
from fastapi.testclient import TestClient
from modern.server import app

class TenderEditing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old=(db.APP_DATA,db.DB_FILE,db.DOCUMENTS,db._INITIALIZED)
        db.APP_DATA=Path(DIR.name)
        db.DB_FILE=db.APP_DATA/'tenders.sqlite3'
        db.DOCUMENTS=db.APP_DATA/'tender_documents'
        db._INITIALIZED=False
        db.initialize()
        cls.client=TestClient(app)

    @classmethod
    def tearDownClass(cls):
        db.APP_DATA,db.DB_FILE,db.DOCUMENTS,db._INITIALIZED=cls.old
        DIR.cleanup()

    def test_edit_comment_and_history(self):
        tender=db.create({'title':'Комментарий'})
        db.add_comment(tender['id'],'Старый текст')
        cid=db.detail(tender['id'])['comments'][0]['id']
        self.assertEqual(self.client.patch(f'/api/tenders/{tender["id"]}/comments/{cid}',json={'body':'Новый текст'}).status_code,200)
        self.assertEqual(db.detail(tender['id'])['comments'][0]['body'],'Новый текст')
        self.assertTrue(any('Старый текст' in e['label'] for e in db.detail(tender['id'])['events']))
        r=self.client.patch(f'/api/tenders/{tender["id"]}/comments/{cid}',json={'body':' '})
        self.assertEqual(r.status_code,400)
        self.assertEqual(db.detail(tender['id'])['comments'][0]['body'],'Новый текст')

    def test_delete_comment_and_history(self):
        tender=db.create({'title':'Удаление'})
        db.add_comment(tender['id'],'Контрольный комментарий')
        cid=db.detail(tender['id'])['comments'][0]['id']
        self.assertEqual(self.client.delete(f'/api/tenders/{tender["id"]}/comments/{cid}').status_code,200)
        self.assertFalse(db.detail(tender['id'])['comments'])
        self.assertTrue(any('Удалён комментарий' in e['label'] for e in db.detail(tender['id'])['events']))
        self.assertEqual(self.client.delete(f'/api/tenders/{tender["id"]}/comments/{cid}').status_code,404)

    def test_shared_blob_survives_first_unlink(self):
        a=db.create({'title':'Первый'})
        b=db.create({'title':'Второй'})
        data=b'contract terms for both'
        aid=db.add_document(a['id'],'contract.txt',data)
        bid=db.add_document(b['id'],'contract.txt',data)
        self.assertEqual(self.client.delete(f'/api/tenders/{a["id"]}/documents/{aid}').status_code,200)
        self.assertEqual(db.document_bytes(b['id'],bid)[1],data)
        self.assertEqual(self.client.delete(f'/api/tenders/{b["id"]}/documents/{bid}').status_code,200)
        self.assertEqual(len(list(db.DOCUMENTS.glob('*'))),0)

if __name__=='__main__':unittest.main()
