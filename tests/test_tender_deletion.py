"""Regression tests for irreversible procurement card deletion (isolated data)."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from modern import tender_store as s
from modern.server import app


class TenderDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix='qx_tender_delete_')
        self.base = Path(self.temp.name)
        self.before = (s.APP_DATA, s.DB_FILE, s.DOCUMENTS, s._INITIALIZED)
        s.APP_DATA, s.DB_FILE, s.DOCUMENTS, s._INITIALIZED = (
            self.base, self.base/'tenders.sqlite3', self.base/'tender_documents', False
        )
        s.initialize()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        s.APP_DATA, s.DB_FILE, s.DOCUMENTS, s._INITIALIZED = self.before
        self.temp.cleanup()

    def test_delete_through_api_cascades_and_persists(self):
        company = s.add_org('ООО тест')
        doomed = s.create({'title':'Черновик для удаления','organization_id':company, 'contract_price':120000})
        protected = s.create({'title':'Другая закупка','organization_id':company})
        tid=doomed['id']
        s.add_comment(tid,'Срочное сообщение')
        s.add_shipment(tid, {'name':'Этап 1','quantity':8,'due_on':'2026-12-14'})
        s.update(tid, {'status':'Выиграли'})
        p=s.link_project('project-to-delete', 'Тестовый проект','', '',[{'title':'ЭВМ'}],1500)
        # link_project without project_key assignment can't link to the doomed card.
        with s.transaction() as c:
            c.execute('UPDATE tender_projects SET tender_id=? WHERE project_key=?',(tid,'project-to-delete'))
        bid=s.add_document(tid,'Приложение.txt',b'Only for doomed tender')
        saved_path = s.DOCUMENTS/(s.detail(tid)['documents'][0]['sha256']+'.txt')
        self.assertTrue(saved_path.is_file())
        result=self.client.delete(f'/api/tenders/{tid}')
        self.assertEqual(result.status_code,200,result.text)
        self.assertTrue(result.json()['deleted'])
        self.assertIsNone(s.get(tid))
        self.assertFalse(saved_path.exists())
        with s.connection() as c:
            for table in ('tender_projects','tender_comments','tender_documents','tender_shipments','tender_events'):
                self.assertEqual(c.execute(f'SELECT count(*) FROM {table} WHERE tender_id=?',(tid,)).fetchone()[0],0,table)
        self.assertEqual(s.get(protected['id'])['title'],'Другая закупка')
        self.assertEqual(s.organizations()[0]['id'],company)
        self.assertEqual(self.client.get(f'/api/tenders/{tid}').status_code,404)
        self.assertEqual(self.client.delete(f'/api/tenders/{tid}').status_code,404)
        s._INITIALIZED=False
        s.initialize()
        self.assertEqual({x['id'] for x in s.listing()}, {protected['id'],p['tender_id']})
        self.assertEqual(self.client.get('/api/tenders').json()['summary']['total'],2)

    def test_removed_link_is_not_auto_recreated(self):
        linked=s.link_project('stable-project-uuid', 'Системные блоки',
                              '0388888888888888888.docx', '', [], 5000)
        tid=linked['tender_id']
        self.assertEqual(self.client.delete('/api/tenders/'+tid).status_code, 200)
        with s.connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM deleted_tender_project_keys WHERE project_key=?',
                                       ('stable-project-uuid',)).fetchone()[0], 1)
        data={'project_key':'stable-project-uuid','project_name':'Системные блоки',
              'source_name':'0388888888888888888.docx','positions':[],'cost':5000}
        response=self.client.post('/api/tenders/link-project',json=data)
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()['suppressed'])
        self.assertEqual(s.listing(),[])
        s._INITIALIZED=False
        s.initialize()
        self.assertTrue(self.client.post('/api/tenders/link-project',json=data).json()['suppressed'])
        restored=self.client.post('/api/tenders/link-project',json={**data,'manual':True})
        self.assertEqual(restored.status_code,200,restored.text)
        self.assertTrue(restored.json()['tender_id'])
        self.assertNotEqual(restored.json()['tender_id'],tid)
        self.assertEqual(len(s.listing()),1)
        self.assertFalse(self.client.post('/api/tenders/link-project',json=data).json().get('suppressed'))

    def test_shared_documents_not_destroyed(self):
        a=s.create({'title':'A'})
        b=s.create({'title':'B'})
        contents=b'shared document data'
        a_id=s.add_document(a['id'],'Agreement.pdf',contents)
        b_id=s.add_document(b['id'],'Agreement.pdf',contents)
        self.assertNotEqual(a_id,b_id)
        path=s.DOCUMENTS/(s.detail(a['id'])['documents'][0]['sha256']+'.pdf')
        self.assertTrue(path.exists())
        self.assertEqual(self.client.delete('/api/tenders/'+a['id']).status_code,200)
        self.assertTrue(path.exists())
        self.assertEqual(s.document_bytes(b['id'],b_id)[1], contents)
        self.assertEqual(self.client.delete('/api/tenders/'+b['id']).status_code,200)
        self.assertFalse(path.exists())

    def test_deletion_failure_rolls_back_and_keeps_blob(self):
        t=s.create({'title':'transaction rollback test'})
        s.add_document(t['id'],'Note.txt',b'keep this file')
        path=s.DOCUMENTS/(s.detail(t['id'])['documents'][0]['sha256']+'.txt')
        real=s.transaction
        # Failure before commit must keep the row and file.
        with patch.object(s,'transaction',side_effect=RuntimeError('simulated disk error')):
            with self.assertRaisesRegex(RuntimeError,'simulated disk error'):
                s.delete_tender(t['id'])
        self.assertTrue(s.get(t['id']))
        self.assertTrue(path.is_file())

    def test_external_paths_are_never_deleted(self):
        item=s.create({'title':'external doc'})
        external=self.base/'private-document.txt'
        external.write_text('not QX-managed',encoding='utf8')
        with s.transaction() as c:
            c.execute('INSERT INTO tender_documents VALUES(?,?,?,?,?,?,?)',
                      ('external',item['id'],'File.txt','a'*64,str(external),'',s.now()))
        s.delete_tender(item['id'])
        self.assertTrue(external.exists())


if __name__=='__main__':
    unittest.main()
