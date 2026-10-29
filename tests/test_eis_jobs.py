"""Local drafts precede bounded, independent EIS work; no external requests."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
import tempfile
import unittest
from unittest.mock import patch

from modern import tender_store as store
from modern.eis_jobs import _JobManager, JobQueueFull

NUMBER = '0322100002526000466'
OTHER = '0373100104826000011'
THIRD = '0373100104826000012'


class EisJobs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='qx_job_tests_')
        self.original = (store.APP_DATA, store.DB_FILE, store.DOCUMENTS, store._INITIALIZED)
        store.APP_DATA = Path(self.tmp.name)
        store.DB_FILE = store.APP_DATA / 'tenders.sqlite3'
        store.DOCUMENTS = store.APP_DATA / 'documents'
        store._INITIALIZED = False
        store.initialize()
        self.managers = []
        self.releases = []

    def tearDown(self):
        for event in self.releases:
            event.set()
        for manager in self.managers:
            manager.close()
            for worker in manager.workers:
                worker.join(timeout=3)
        store.APP_DATA, store.DB_FILE, store.DOCUMENTS, store._INITIALIZED = self.original
        self.tmp.cleanup()

    def manager(self, **kwargs):
        manager = _JobManager(**kwargs)
        self.managers.append(manager)
        return manager

    def gate(self):
        started, release = Event(), Event()
        self.releases.append(release)
        def run(number, *, tender_id, progress, **kwargs):
            progress('metadata', 'Получаем сведения', 15)
            started.set()
            if not release.wait(3):
                raise TimeoutError('test worker was not released')
            return {'partial': False, 'message': 'Готово', 'tender': store.detail(tender_id)}
        return started, release, run

    def done(self, manager, job_id):
        with manager.condition:
            completed = manager.condition.wait_for(
                lambda: job_id not in manager.jobs or manager.jobs[job_id]['status'] not in ('queued', 'running'), timeout=4)
        self.assertTrue(completed, 'Job did not finish')
        return manager.get(job_id)

    def test_card_is_returned_before_blocked_network_and_progress_is_visible(self):
        started, release, runner = self.gate()
        manager = self.manager(runner=runner)
        result = manager.start(NUMBER)
        self.assertEqual(result['tender']['number'], NUMBER)
        self.assertEqual(len(store.listing()), 1)
        self.assertTrue(started.wait(1))
        progress = manager.get(result['job']['id'])['job']
        self.assertEqual(progress['status'], 'running')
        self.assertEqual(progress['stage'], 'metadata')
        self.assertEqual(progress['progress'], 15)
        release.set()
        self.assertEqual(self.done(manager, progress['id'])['job']['status'], 'succeeded')

    def test_exception_keeps_draft_and_never_exposes_exception_contents(self):
        def broken(*args, **kwargs):
            raise ModuleNotFoundError('private-token-and-path')
        manager = self.manager(runner=broken)
        result = manager.start(NUMBER)
        final = self.done(manager, result['job']['id'])
        self.assertEqual(final['job']['status'], 'failed')
        self.assertEqual(final['job']['error_type'], 'ModuleNotFoundError')
        self.assertNotIn('private-token-and-path', str(final))
        self.assertEqual(store.get(result['tender']['id'])['number'], NUMBER)

    def test_concurrent_requests_reuse_one_job_and_one_card(self):
        started, release, runner = self.gate()
        manager = self.manager(runner=runner)
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: manager.start(NUMBER), range(6)))
        self.assertEqual(len({item['job']['id'] for item in results}), 1)
        self.assertEqual(len(store.listing()), 1)
        self.assertEqual(len(manager.active()['jobs']), 1)
        release.set()
        self.done(manager, results[0]['job']['id'])

    def test_queue_saturation_is_bounded_but_preserves_new_local_card(self):
        started, release, runner = self.gate()
        manager = self.manager(runner=runner, max_workers=1, max_queue=1)
        first = manager.start(NUMBER)
        self.assertTrue(started.wait(1))
        second = manager.start(OTHER)
        with self.assertRaises(JobQueueFull) as failure:
            manager.start(THIRD)
        self.assertEqual(store.get(failure.exception.tender_id)['number'], THIRD)
        self.assertEqual(len(manager.active()['jobs']), 2)
        self.assertEqual(len(manager.workers), 1)
        release.set()
        self.done(manager, first['job']['id'])
        self.done(manager, second['job']['id'])

    def test_missing_job_and_deleted_card_are_distinct(self):
        manager = self.manager(runner=lambda *a, **k: {'partial': True})
        with self.assertRaises(KeyError):
            manager.get('missing')
        result = manager.start(NUMBER)
        final = self.done(manager, result['job']['id'])
        self.assertEqual(final['job']['status'], 'partial')
        store.delete_tender(result['tender']['id'])
        self.assertIsNone(manager.get(result['job']['id'])['tender'])

    def test_returned_job_descriptors_are_independent_copies(self):
        manager = self.manager(runner=lambda *a, **k: {'partial': True, 'conflicts': [{'field': 'title'}]})
        result = manager.start(NUMBER)
        final = self.done(manager, result['job']['id'])
        final['job']['result']['conflicts'].clear()
        self.assertEqual(len(manager.get(result['job']['id'])['job']['result']['conflicts']), 1)
        self.assertEqual(manager.active()['jobs'], [])

    def test_completed_history_is_bounded_and_can_expire(self):
        manager = self.manager(runner=lambda *a, **k: {'partial': False}, max_completed=1)
        first = manager.start(NUMBER)
        self.done(manager, first['job']['id'])
        second = manager.start(OTHER)
        self.done(manager, second['job']['id'])
        with self.assertRaises(KeyError):
            manager.get(first['job']['id'])
        with manager.condition:
            manager.jobs[second['job']['id']]['_finished'] -= 3601
        with self.assertRaises(KeyError):
            manager.get(second['job']['id'])

    def test_default_worker_import_failure_still_returns_saved_draft(self):
        manager = self.manager()
        # Exercise the real lazy provider import, as with a partially updated ZIP.
        with patch.dict('sys.modules', {'modern.eis_sync': None}):
            result = manager.start(NUMBER)
            final = self.done(manager, result['job']['id'])
        self.assertEqual(final['job']['status'], 'failed')
        self.assertEqual(final['job']['error_type'], 'ModuleNotFoundError')
        self.assertEqual(final['tender']['number'], NUMBER)

    def test_multiple_lots_require_explicit_card_and_do_not_make_third(self):
        a = store.create({'number': NUMBER, 'lot': '1'})
        store.create({'number': NUMBER, 'lot': '2'})
        manager = self.manager(runner=lambda *a, **k: {'partial': False})
        with self.assertRaises(ValueError):
            manager.start(NUMBER)
        self.assertEqual(len(store.listing()), 2)
        chosen = manager.start(NUMBER, tender_id=a['id'])
        self.assertEqual(chosen['tender']['id'], a['id'])
        self.done(manager, chosen['job']['id'])


if __name__ == '__main__':
    unittest.main()
