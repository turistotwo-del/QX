"""Round-trip tender backups and reject corrupt/unsafe archives without data loss."""
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from io import BytesIO

from fastapi.testclient import TestClient
from modern import tender_store as store
from modern import tender_backup as backup
from modern.server import app

class BackupRestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='qx_backup_test_')
        self.old=(store.APP_DATA,store.DB_FILE,store.DOCUMENTS,store._INITIALIZED)
        store.APP_DATA=Path(self.tmp.name)
        store.DB_FILE=store.APP_DATA/'tenders.sqlite3'
        store.DOCUMENTS=store.APP_DATA/'tender_documents'
        store._INITIALIZED=False
        store.initialize()
        self.client=TestClient(app)

    def tearDown(self):
        store.APP_DATA,store.DB_FILE,store.DOCUMENTS,store._INITIALIZED=self.old
        self.tmp.cleanup()

    def _data(self):
        t=store.create({'title':'Моноблоки для города','status':'Просчёт','number':'0322100002526000466'})
        store.add_comment(t['id'],'Проверить реестровый BIOS и дату')
        store.add_document(t['id'],'tender.txt',b'BIOS in registry. 30 days.', 'BIOS in registry')
        return t

    def test_round_trip_document_and_comment(self):
        t=self._data()
        original_id=t['id']
        arc=store.backup_archive()
        with zipfile.ZipFile(BytesIO(arc)) as z:
            self.assertIn('manifest.json',z.namelist())
        info=backup.preview_archive(arc)
        self.assertEqual(info['tenders'],1)
        self.assertEqual(info['documents'],1)
        store.update(original_id,{'title':'Испорченная карточка','status':'Выиграли'})
        store.create({'title':'Лишняя закупка'})
        restored=backup.restore_archive(arc)
        self.assertEqual(restored['restored']['tenders'],1)
        self.assertEqual(store.get(original_id)['title'],'Моноблоки для города')
        self.assertEqual(store.get(original_id)['status'],'Просчёт')
        self.assertEqual(len(store.listing()),1)
        detail=store.detail(original_id)
        self.assertEqual(detail['comments'][0]['body'],'Проверить реестровый BIOS и дату')
        self.assertEqual(store.document_bytes(original_id,detail['documents'][0]['id'])[1],b'BIOS in registry. 30 days.')
        self.assertTrue(Path(restored['snapshot']).is_file())
        with zipfile.ZipFile(restored['snapshot']) as z:
            self.assertIn('tenders.sqlite3',z.namelist())

    def test_corrupted_archive_does_not_modify_database(self):
        t=self._data()
        arc=store.backup_archive()
        store.update(t['id'],{'title':'Должно остаться'})
        with zipfile.ZipFile(BytesIO(arc)) as z:
            entries={n:z.read(n) for n in z.namelist()}
        # Replace a document with other bytes and rezip without tampering with db.
        doc=next(n for n in entries if n.startswith('documents/'))
        entries[doc]=b'FAKE CONTENT'
        dest=BytesIO()
        with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for name,raw in entries.items():z.writestr(name,raw)
        with self.assertRaisesRegex(ValueError,'документа'):
            backup.restore_archive(dest.getvalue())
        self.assertEqual(store.get(t['id'])['title'],'Должно остаться')
        self.assertFalse((store.APP_DATA/'restore_snapshots').exists())

    def test_unsafe_zip_rejected_before_read(self):
        stream=BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            z.writestr('../attack.txt','BAD')
            z.writestr('tenders.sqlite3','garbage')
        with self.assertRaisesRegex(ValueError,'Небезопасные'):
            backup.preview_archive(stream.getvalue())
        self.assertFalse((store.APP_DATA/'attack.txt').exists())

    def test_api_preview_confirmation_and_restore(self):
        row=self._data(); data=store.backup_archive()
        preview=self.client.post('/api/tenders/backup/preview',content=data)
        self.assertEqual(preview.status_code,200)
        self.assertEqual(preview.json()['preview']['documents'],1)
        denied=self.client.post('/api/tenders/backup/restore',content=data)
        self.assertEqual(denied.status_code,400)
        store.update(row['id'],{'title':'Изменено'})
        result=self.client.post('/api/tenders/backup/restore',content=data,headers={'X-QX-Confirm-Restore':'REPLACE_EXISTING_TENDERS'})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(store.get(row['id'])['title'],'Моноблоки для города')

    def test_older_backups_without_manifest(self):
        t=self._data(); arc=store.backup_archive()
        old=BytesIO()
        with zipfile.ZipFile(BytesIO(arc)) as src, zipfile.ZipFile(old,'w') as z:
            for name in src.namelist():
                if name!='manifest.json':z.writestr(name,src.read(name))
        self.assertEqual(backup.preview_archive(old.getvalue())['tenders'],1)

if __name__=='__main__':unittest.main()
