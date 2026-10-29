"""Failure-injection tests: QX must NEVER risk contracts on schema upgrades."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from modern import tender_store as store


class TestTenderSchemaMigration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='qx_migrate_')
        self.folder = Path(self.tmp.name)
        self.old = (store.APP_DATA, store.DB_FILE, store.DOCUMENTS, store._INITIALIZED)
        store.APP_DATA = self.folder
        store.DB_FILE = self.folder / 'tenders.sqlite3'
        store.DOCUMENTS = self.folder / 'tender_documents'
        store._INITIALIZED = False

    def tearDown(self):
        store.APP_DATA, store.DB_FILE, store.DOCUMENTS, store._INITIALIZED = self.old
        self.tmp.cleanup()

    def legacy_db(self, version=1):
        c=sqlite3.connect(store.DB_FILE)
        c.execute('CREATE TABLE schema_version(version INTEGER NOT NULL)')
        c.execute('INSERT INTO schema_version VALUES (?)',(version,))
        c.execute('''CREATE TABLE tenders(
          id TEXT PRIMARY KEY, number TEXT DEFAULT '', lot TEXT DEFAULT '',
          organization_id TEXT, title TEXT NOT NULL DEFAULT '', created_at TEXT, updated_at TEXT)''')
        c.execute('INSERT INTO tenders(id,number,lot,title,created_at,updated_at) VALUES (?,?,?,?,?,?)',
                  ('retained-1','0322100002526000466','','Реальный контракт','2026-10-01','2026-10-01'))
        c.commit()
        return c

    def snapshots(self):
        return list((self.folder/'migration_snapshots').glob('*.sqlite3'))

    def test_fresh_install_does_not_create_unnecessary_backup(self):
        store.initialize()
        self.assertEqual([], self.snapshots())
        with store.connection() as c:
            self.assertEqual(c.execute('SELECT version FROM schema_version').fetchone()[0],store.SCHEMA_VERSION)
        self.assertEqual(0,len(list(self.folder.glob('*.partial'))))

    def test_old_contract_survives_and_snapshot_is_restorable(self):
        with closing(self.legacy_db()):
            pass
        store.initialize()
        copies = self.snapshots()
        self.assertEqual(len(copies),1)
        with closing(sqlite3.connect(copies[0])) as old:
            self.assertEqual(old.execute('SELECT version FROM schema_version').fetchone()[0],1)
            self.assertEqual(old.execute('SELECT title FROM tenders WHERE id="retained-1"').fetchone()[0],
                             'Реальный контракт')
        with store.connection() as upgraded:
            self.assertEqual(upgraded.execute('SELECT version FROM schema_version').fetchone()[0],store.SCHEMA_VERSION)
            self.assertEqual(upgraded.execute('SELECT title FROM tenders WHERE id="retained-1"').fetchone()[0],
                             'Реальный контракт')
            self.assertTrue({'application_due_on','auction_on','payment_due_on'} <=
                            {c[1] for c in upgraded.execute('PRAGMA table_info(tenders)')})
        store._INITIALIZED=False
        store.initialize()
        self.assertEqual(len(self.snapshots()),1,'Repeated launch must not create redundant backups')

    def test_wal_committed_rows_are_in_snapshot(self):
        with closing(self.legacy_db()) as con:
            con.execute('PRAGMA journal_mode=WAL')
            con.execute('PRAGMA wal_autocheckpoint=0')
            con.execute('INSERT INTO tenders(id,title) VALUES (?,?)',('wal-2','Вторая закупка в WAL'))
            con.commit()
            # Keep source connection alive to ensure WAL has not been checkpointed.
            store.initialize()
            copy=self.snapshots()[0]
            with closing(sqlite3.connect(copy)) as old:
                self.assertEqual(old.execute('SELECT title FROM tenders WHERE id="wal-2"').fetchone()[0],
                                 'Вторая закупка в WAL')

    def test_failed_migration_rolls_back_partial_column_changes(self):
        with closing(self.legacy_db()):
            pass
        def fail_after_first_ddl(con):
            con.execute("ALTER TABLE tenders ADD COLUMN application_due_on TEXT DEFAULT ''")
            raise RuntimeError('simulate power loss / migration error')
        with patch.object(store,'_apply_schema',side_effect=fail_after_first_ddl):
            with self.assertRaisesRegex(RuntimeError,'simulate'):
                store.initialize()
        self.assertFalse(store._INITIALIZED)
        self.assertEqual(len(self.snapshots()),1)
        with closing(sqlite3.connect(store.DB_FILE)) as db:
            self.assertEqual(db.execute('SELECT version FROM schema_version').fetchone()[0],1)
            self.assertNotIn('application_due_on',{c[1] for c in db.execute('PRAGMA table_info(tenders)')})
            self.assertEqual(db.execute('SELECT title FROM tenders').fetchone()[0],'Реальный контракт')
        store.initialize()
        with store.connection() as db:
            self.assertEqual(db.execute('SELECT version FROM schema_version').fetchone()[0],store.SCHEMA_VERSION)

    def test_snapshot_creation_failure_prevents_migration(self):
        with closing(self.legacy_db()):
            pass
        with patch.object(store,'_write_migration_snapshot',side_effect=OSError('no disk space')):
            with self.assertRaisesRegex(OSError,'no disk space'):
                store.initialize()
        with closing(sqlite3.connect(store.DB_FILE)) as db:
            self.assertEqual(db.execute('SELECT version FROM schema_version').fetchone()[0],1)
            self.assertNotIn('application_due_on',{c[1] for c in db.execute('PRAGMA table_info(tenders)')})

    def test_partial_current_schema_is_snapshotted_before_repair(self):
        store.initialize()
        with store.transaction() as db:
            db.execute('DROP TABLE tender_notified')
        store._INITIALIZED=False
        store.initialize()
        self.assertEqual(len(self.snapshots()),1)
        with closing(sqlite3.connect(self.snapshots()[0])) as old:
            self.assertNotIn('tender_notified', {r[0] for r in old.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")})
        with store.connection() as db:
            self.assertIn('tender_notified', {r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")})

    def test_downgrade_from_future_version_is_refused(self):
        with closing(self.legacy_db(version=99)):
            pass
        with self.assertRaisesRegex(RuntimeError,'более новой версией'):
            store.initialize()
        self.assertEqual(self.snapshots(),[])
        with closing(sqlite3.connect(store.DB_FILE)) as db:
            self.assertEqual(db.execute('SELECT version FROM schema_version').fetchone()[0],99)

    def test_corrupt_database_is_not_overwritten(self):
        corruption=b'garbage sqlite database without valid header'
        store.DB_FILE.write_bytes(corruption)
        with self.assertRaises((sqlite3.DatabaseError,RuntimeError)):
            store.initialize()
        self.assertEqual(store.DB_FILE.read_bytes(),corruption)
        self.assertEqual(self.snapshots(),[])


if __name__=='__main__':
    unittest.main()
