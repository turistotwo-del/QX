"""On-demand full integrity scan, including corrupted and reused documents."""
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from modern import tender_store as store
from modern.attachment_integrity import audit_attachments, CorruptAttachment
from modern.server import app


class AttachmentIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='qx_integrity_')
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

    def new_document(self, body=b'An original document about registry BIOS.'):
        tender=store.create({'title':'PRIVATE QX CONTRACT'})
        document_id=store.add_document(tender['id'],'secret.docx',body)
        return tender['id'],document_id,store.DOCUMENTS/(sha256(body).hexdigest()+'.docx')

    def test_audit_full_beyond_200_and_preserves_privacy(self):
        tid,did,path=self.new_document()
        with store.transaction() as con:
            # More than 200 references to one content blob: hashing is deduplicated.
            for i in range(230):
                con.execute('INSERT INTO tender_documents(id,tender_id,filename,sha256,file_path,text_excerpt,created_at) VALUES(?,?,?,?,?,?,?)',
                            (f'duplicate-{i}',tid,'PRIVATE DOCUMENT TITLE',path.stem,str(path),'SECRET CONTENT','2026-01-01'))
        r=self.client.get('/api/diagnostics/attachments')
        self.assertEqual(r.status_code,200)
        report=r.json()
        self.assertEqual(report['status'],'ok')
        self.assertEqual(report['linked'],231)
        self.assertEqual(report['unique'],1)
        self.assertEqual(report['valid'],1)
        self.assertNotIn('PRIVATE',str(report))
        self.assertNotIn('SECRET',str(report))
        self.assertNotIn(str(path),str(report))

    def test_content_modified_is_rejected_for_download_and_backup(self):
        tid,did,path=self.new_document()
        path.write_bytes(b'ATTACK: NOT THE ORIGINAL CONTRACT')
        result=self.client.get('/api/diagnostics/attachments').json()
        self.assertEqual(result['modified'],1)
        self.assertEqual(result['status'],'error')
        r=self.client.get(f'/api/tenders/{tid}/documents/{did}')
        self.assertEqual(r.status_code,409)
        self.assertNotIn('ATTACK:',r.text)
        with self.assertRaisesRegex(CorruptAttachment,'SHA-256'):
            store.backup_archive()

    def test_missing_attachment_is_reported_and_not_backed_up(self):
        tid,did,path=self.new_document()
        path.unlink()
        report=audit_attachments()
        self.assertEqual(report['missing'],1)
        self.assertEqual(report['valid'],0)
        with self.assertRaisesRegex(CorruptAttachment,'отсутствует'):
            store.document_bytes(tid,did)
        with self.assertRaises(CorruptAttachment):
            store.backup_archive()

    def test_symlink_must_not_read_external_documents(self):
        tid,did,path=self.new_document()
        outside=Path(self.tmp.name)/'private-outside.txt'
        outside.write_bytes(path.read_bytes())
        path.unlink()
        try:
            path.symlink_to(outside)
        except (NotImplementedError, OSError):
            self.skipTest('No symlink support')
        report=audit_attachments()
        self.assertEqual(report['unsafe'],1)
        with self.assertRaises(CorruptAttachment):
            store.document_bytes(tid,did)

    def test_oversized_attachment_is_refused_before_loading_in_memory(self):
        tid,did,path=self.new_document()
        with path.open('r+b') as f:
            f.truncate(30*1024*1024+1)
        self.assertEqual(audit_attachments()['oversized'],1)
        with self.assertRaisesRegex(CorruptAttachment,'размер'):
            store.document_bytes(tid,did)

    def test_reupload_does_not_silently_reuse_modified_blob(self):
        tid,did,path=self.new_document()
        body=b'An original document about registry BIOS.'
        path.write_bytes(b'CORRUPTED DOCUMENT')
        another=store.create({'title':'second tender'})
        with self.assertRaisesRegex(CorruptAttachment,'SHA-256'):
            store.add_document(another['id'],'secret.docx',body)
        with self.assertRaises(CorruptAttachment):
            store.add_documents_batch(another['id'],[('secret.docx',body,'')])
        self.assertEqual(len(store.detail(another['id'])['documents']),0)
        self.assertEqual(path.read_bytes(),b'CORRUPTED DOCUMENT')

    def test_clean_backup_roundtrip_remains_compatible(self):
        tid,did,path=self.new_document()
        payload=store.backup_archive()
        from modern.tender_backup import preview_archive
        report=preview_archive(payload)
        self.assertEqual(report['documents'],1)
        self.assertEqual(store.document_bytes(tid,did)[1],path.read_bytes())


if __name__=='__main__': unittest.main()
