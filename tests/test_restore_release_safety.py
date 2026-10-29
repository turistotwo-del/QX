"""Release guards: incompatible tender archive and rollback of full restore."""
from contextlib import closing
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from modern import tender_store as store
from modern import tender_backup as backup


class _RestoreFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='qx_restore_release_')
        self.old = (store.APP_DATA, store.DB_FILE, store.DOCUMENTS, store._INITIALIZED)
        store.APP_DATA = Path(self.tmp.name)
        store.DB_FILE = store.APP_DATA/'tenders.sqlite3'
        store.DOCUMENTS = store.APP_DATA/'tender_documents'
        store._INITIALIZED = False
        store.initialize()

    def tearDown(self):
        store.APP_DATA, store.DB_FILE, store.DOCUMENTS, store._INITIALIZED = self.old
        self.tmp.cleanup()



class FullRestoreSafetyTests(_RestoreFixture):
    def test_newer_database_rejected_during_preview_without_writing_files(self):
        tender = store.create({'title':'Current contract'})
        original = b'local existing document'
        store.add_document(tender['id'], 'local.txt', original)
        archive = store.backup_archive()
        with zipfile.ZipFile(BytesIO(archive)) as z:
            entries = {key:z.read(key) for key in z.namelist()}
        with tempfile.TemporaryDirectory(prefix='qx_future_db_') as tmp:
            db = Path(tmp)/'future.sqlite3'
            db.write_bytes(entries['tenders.sqlite3'])
            with closing(sqlite3.connect(str(db))) as con:
                con.execute('UPDATE schema_version SET version=?', (store.SCHEMA_VERSION + 2,))
                con.commit()
            entries['tenders.sqlite3'] = db.read_bytes()
            manifest = json.loads(entries['manifest.json'])
            manifest['db_sha256'] = sha256(entries['tenders.sqlite3']).hexdigest()
            entries['manifest.json'] = json.dumps(manifest).encode()
        stream = BytesIO()
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            for name, data in entries.items():
                z.writestr(name, data)
        with self.assertRaisesRegex(ValueError, 'новой версией'):
            backup.preview_archive(stream.getvalue())
        with self.assertRaisesRegex(ValueError, 'новой версией'):
            backup.restore_archive(stream.getvalue())
        self.assertEqual(store.get(tender['id'])['title'], 'Current contract')
        self.assertFalse((store.APP_DATA/'restore_snapshots').exists())

    def test_sqlite_failure_restores_unreferenced_document_and_current_database(self):
        original_tender = store.create({'title':'Old archive state'})
        archive_doc = b'original old contract for restored database'
        doc_id = store.add_document(original_tender['id'], 'old.txt', archive_doc)
        archive = store.backup_archive()
        path = store.DOCUMENTS/(sha256(archive_doc).hexdigest()+'.txt')
        store.remove_document(original_tender['id'], doc_id)
        # Content-addressed file from an old archive can be present in storage,
        # but not referenced in the *current* snapshot; it must be preserved.
        path.write_bytes(b'UNREFERENCED ORIGINAL DATA')
        newer = store.create({'title':'New tender must survive failed restore'})
        base_initialize = store.initialize
        thrown = [False]

        def fail_once_after_copy():
            if not store._INITIALIZED and not thrown[0]:
                thrown[0] = True
                raise RuntimeError('simulated post-backup schema failure')
            return base_initialize()

        with patch.object(store, 'initialize', side_effect=fail_once_after_copy):
            with self.assertRaisesRegex(RuntimeError, 'simulated post-backup schema failure'):
                backup.restore_archive(archive)
        self.assertTrue(thrown[0])
        self.assertEqual(store.get(newer['id'])['title'], 'New tender must survive failed restore')
        self.assertEqual(store.detail(original_tender['id'])['documents'], [])
        self.assertEqual(path.read_bytes(), b'UNREFERENCED ORIGINAL DATA')
        self.assertEqual(len(list((store.APP_DATA/'restore_snapshots').glob('*.zip'))), 1)

    def test_successful_restore_still_replaces_tenders_and_recovers_attachments(self):
        t = store.create({'title':'Prior contract'})
        contents = b'BIOS explicitly required in registry'
        store.add_document(t['id'], 'bios.txt', contents)
        archive = store.backup_archive()
        store.update(t['id'], {'title':'Changed'})
        store.create({'title':'Additional tender'})
        report = backup.preview_archive(archive)
        self.assertEqual(report['schema_version'], store.SCHEMA_VERSION)
        result = backup.restore_archive(archive)
        self.assertTrue(Path(result['snapshot']).is_file())
        self.assertEqual(len(store.listing()), 1)
        self.assertEqual(store.get(t['id'])['title'], 'Prior contract')
        row = store.detail(t['id'])['documents'][0]
        self.assertEqual(store.document_bytes(t['id'], row['id'])[1], contents)


if __name__ == '__main__':
    unittest.main()

# These tests deliberately monkeypatch file installation and snapshot
# publication. The existing database and documents must remain usable.
class InterruptedRestoreTests(_RestoreFixture):
    def test_failed_attachment_install_preserves_sqlite_and_orphan_content(self):
        import os
        from unittest.mock import patch
        tender = store.create({'title': 'Data before import'})
        body = b'previous archive PDF content'
        did = store.add_document(tender['id'], 'old.pdf', body)
        archive = store.backup_archive()
        store.remove_document(tender['id'], did)
        orphan = store.DOCUMENTS / (sha256(body).hexdigest() + '.pdf')
        orphan.write_bytes(b'KEEP UNREFERENCED FILE')
        newest = store.create({'title':'Newest preserved'})
        real_replace = os.replace
        def failing_install(src, dest):
            if '.qx-restoring-' in str(src):
                raise OSError('simulated disk error installing new document')
            return real_replace(src, dest)
        with patch.object(backup.os, 'replace', side_effect=failing_install):
            with self.assertRaisesRegex(OSError,'disk error'):
                backup.restore_archive(archive)
        self.assertEqual(orphan.read_bytes(), b'KEEP UNREFERENCED FILE')
        self.assertEqual(store.get(newest['id'])['title'], 'Newest preserved')
        self.assertTrue(list((store.APP_DATA / 'restore_snapshots').glob('*.zip')))
        self.assertEqual(list(store.DOCUMENTS.glob('*.qx-restoring-*')), [])

    def test_failed_protective_snapshot_publication_never_starts_restore(self):
        import os
        tender = store.create({'title': 'Current unchanged'})
        body = b'old contract document'
        store.add_document(tender['id'], 'old.txt', body)
        backup_bytes = store.backup_archive()
        store.update(tender['id'], {'title': 'More recent changes'})
        real_replace = os.replace
        def fail_snapshot(src, dest):
            if str(dest).endswith('.zip') and 'QX_Before_Restore_' in str(dest):
                raise OSError('disk is full')
            return real_replace(src, dest)
        with patch.object(backup.os,'replace',side_effect=fail_snapshot):
            with self.assertRaisesRegex(OSError, 'disk is full'):
                backup.restore_archive(backup_bytes)
        self.assertEqual(store.get(tender['id'])['title'], 'More recent changes')
        self.assertEqual(list((store.APP_DATA / 'restore_snapshots').glob('*.partial')), [])
        self.assertEqual(list((store.APP_DATA / 'restore_snapshots').glob('*.zip')), [])
