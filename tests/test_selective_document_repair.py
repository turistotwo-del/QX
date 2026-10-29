"""Recover damaged QX attachments without rolling back more recent tender activity."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient
from modern import tender_store as store
from modern import tender_backup as backup
from modern.server import app


class SelectiveRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='qx_selective_repair_')
        self.old = (store.APP_DATA, store.DB_FILE, store.DOCUMENTS, store._INITIALIZED)
        store.APP_DATA = Path(self.tmp.name)
        store.DB_FILE = store.APP_DATA/'tenders.sqlite3'
        store.DOCUMENTS = store.APP_DATA/'tender_documents'
        store._INITIALIZED = False
        store.initialize()
        self.client = TestClient(app)
        self.tender = store.create({'title':'Original contract'})
        self.original = b'Original registry BIOS requirement in contract'
        self.doc_id = store.add_document(self.tender['id'], 'terms.docx', self.original)
        self.path = store.DOCUMENTS/(sha256(self.original).hexdigest()+'.docx')
        self.archive = store.backup_archive()

    def tearDown(self):
        store.APP_DATA, store.DB_FILE, store.DOCUMENTS, store._INITIALIZED = self.old
        self.tmp.cleanup()

    def test_preview_is_read_only_and_does_not_revert_recent_changes(self):
        store.update(self.tender['id'], {'title':'Newer title from today'})
        store.add_comment(self.tender['id'], 'New note after archive')
        self.path.write_bytes(b'DAMAGED, NOT EXPECTED')
        before=self.path.read_bytes()
        r=self.client.post('/api/tenders/backup/repair-preview',content=self.archive)
        self.assertEqual(r.status_code,200,r.text)
        p=r.json()['preview']
        self.assertEqual((p['repairable'],p['intact'],p['total']),(1,0,1))
        self.assertFalse(p['changes_to_database'])
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(store.get(self.tender['id'])['title'],'Newer title from today')
        self.assertFalse((store.APP_DATA/'repair_snapshots').exists())

    def test_repair_requires_confirmation_and_keeps_recent_tenders(self):
        store.update(self.tender['id'],{'title':'Latest title'})
        store.add_comment(self.tender['id'],'Fresh comment')
        recent=store.create({'title':'Added after backup'})
        self.path.write_bytes(b'CORRUPT')
        r=self.client.post('/api/tenders/backup/repair',content=self.archive)
        self.assertEqual(r.status_code,400)
        self.assertEqual(self.path.read_bytes(),b'CORRUPT')
        r=self.client.post('/api/tenders/backup/repair',content=self.archive,
                           headers={'X-QX-Confirm-Repair':'REPAIR_DAMAGED_ATTACHMENTS_ONLY'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['repaired'],1)
        self.assertTrue(r.json()['database_unchanged'])
        self.assertEqual(store.document_bytes(self.tender['id'],self.doc_id)[1],self.original)
        self.assertEqual(store.get(self.tender['id'])['title'],'Latest title')
        self.assertEqual(store.get(recent['id'])['title'],'Added after backup')
        self.assertIn('Fresh comment', [c['body'] for c in store.detail(self.tender['id'])['comments']])
        originals=list((store.APP_DATA/'repair_snapshots').glob('*/0'))
        self.assertEqual(len(originals),1)
        self.assertEqual(originals[0].read_bytes(),b'CORRUPT')
        self.assertEqual(backup.preview_document_repair(self.archive)['repairable'],0)

    def test_missing_files_repair_and_shared_references(self):
        other=store.create({'title':'Second tender'})
        second_id=store.add_document(other['id'],'terms.docx',self.original)
        self.path.unlink()
        self.assertEqual(backup.preview_document_repair(self.archive)['repairable'],1)
        result=backup.repair_documents(self.archive)
        self.assertEqual(result['repaired'],1)
        self.assertEqual(store.document_bytes(other['id'],second_id)[1],self.original)
        self.assertEqual(store.document_bytes(self.tender['id'],self.doc_id)[1],self.original)
        self.assertEqual(backup.repair_documents(self.archive)['repaired'],0)

    def test_document_not_in_older_backup_is_not_touched(self):
        more=b'New requirement saved after backup'
        did=store.add_document(self.tender['id'],'new.txt',more)
        new_path=store.DOCUMENTS/(sha256(more).hexdigest()+'.txt')
        self.path.write_bytes(b'bad')
        new_path.write_bytes(b'more bad')
        report=backup.preview_document_repair(self.archive)
        self.assertEqual(report['repairable'],1)
        self.assertEqual(report['not_in_backup'],1)
        backup.repair_documents(self.archive)
        self.assertEqual(new_path.read_bytes(),b'more bad')
        self.assertEqual(store.get(self.tender['id'])['title'],'Original contract')

    def test_windows_file_picker_supports_zip_repair(self):
        from modern.native_bridge import QXNativeBridge
        from unittest.mock import patch
        archived=store.APP_DATA/'backup.zip'
        archived.write_bytes(self.archive)
        with patch('modern.native_bridge.file_dialog',return_value=str(archived)):
            result=QXNativeBridge().choose_file('tender_repair')
        self.assertEqual(result['name'],'backup.zip')
        import base64
        self.assertEqual(base64.b64decode(result['base64']),self.archive)

    def test_repair_preview_does_not_disclose_contract_identifiers(self):
        self.path.write_bytes(b'corrupt')
        report=self.client.post('/api/tenders/backup/repair-preview',content=self.archive).json()
        self.assertNotIn(self.tender['id'],str(report))
        self.assertNotIn(str(self.path),str(report))
        self.assertNotIn('Original contract',str(report))

    def test_unsafe_symlink_is_not_touched(self):
        ext=store.APP_DATA/'outside-private.txt'
        ext.write_bytes(self.original)
        self.path.unlink()
        try:
            self.path.symlink_to(ext)
        except (OSError,NotImplementedError):
            self.skipTest('No symlink support')
        result=backup.preview_document_repair(self.archive)
        self.assertEqual(result['unsafe'],1)
        self.assertEqual(result['repairable'],0)
        self.assertEqual(backup.repair_documents(self.archive)['repaired'],0)
        self.assertEqual(ext.read_bytes(),self.original)

    def test_tampered_archive_must_not_change_current_files(self):
        self.path.write_bytes(b'bad')
        with zipfile.ZipFile(BytesIO(self.archive)) as original:
            contents={name: original.read(name) for name in original.namelist()}
        target=next(k for k in contents if k.startswith('documents/'))
        contents[target]=b'MALICIOUS_CONTENT'
        output=BytesIO()
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for name,data in contents.items():z.writestr(name,data)
        with self.assertRaisesRegex(ValueError,'документа'):
            backup.repair_documents(output.getvalue())
        self.assertEqual(self.path.read_bytes(),b'bad')

    def test_full_restore_failure_does_not_replace_even_one_document(self):
        # A full restore requires a protective snapshot. Previously it copied
        # incoming documents BEFORE checking that a snapshot could be made.
        self.path.write_bytes(b'CORRUPT')
        with self.assertRaises(Exception):
            backup.restore_archive(self.archive)
        self.assertEqual(self.path.read_bytes(),b'CORRUPT')
        self.assertEqual(store.get(self.tender['id'])['title'],'Original contract')

    def test_write_failure_rolls_back_previously_repaired_file(self):
        content2=b'Another independent attachment'
        store.add_document(self.tender['id'],'extra.txt',content2)
        archive=store.backup_archive()
        second_path=store.DOCUMENTS/(sha256(content2).hexdigest()+'.txt')
        self.path.write_bytes(b'broken1')
        second_path.write_bytes(b'broken2')
        import os
        native_replace=os.replace
        count={'n':0}
        def fail_second(src,dst):
            if '.qxrepair-' in str(src):
                count['n']+=1
                if count['n']==2:raise OSError('simulated interrupted disk write')
            return native_replace(src,dst)
        with patch.object(backup.os,'replace',side_effect=fail_second):
            with self.assertRaisesRegex(OSError,'interrupted'):
                backup.repair_documents(archive)
        self.assertEqual(self.path.read_bytes(),b'broken1')
        self.assertEqual(second_path.read_bytes(),b'broken2')


if __name__=='__main__': unittest.main()
