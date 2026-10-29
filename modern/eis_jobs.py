"""Bounded background EIS jobs; local card creation never waits for a provider.

Only safe local job state is retained in memory. User cards and original files
remain in the ordinary SQLite store even if this process or a provider fails.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from threading import Condition, Thread
from time import monotonic
from uuid import uuid4

from modern import tender_store as store


class JobQueueFull(ValueError):
    def __init__(self, tender_id: str):
        super().__init__('Очередь получения данных занята. Карточка сохранена; повторите запрос позже.')
        self.tender_id = tender_id


def _timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _run_sync(number, *, download_documents, tender_id, progress):
    # Missing XML/HTML dependencies must fail a job, never local card creation.
    from modern.eis_sync import sync_notice
    return sync_notice(number, download_documents=download_documents,
                       tender_id=tender_id, progress=progress)


def _ensure_card(number: str, tender_id: str):
    if tender_id:
        item = store.get(tender_id)
        if not item:
            raise KeyError('Закупка не найдена')
        if item.get('number') != number:
            raise ValueError('Номер не совпадает с выбранной карточкой закупки')
        return item
    matches = [item for item in store.listing() if item.get('number') == number]
    if len(matches) > 1:
        raise ValueError('Есть несколько карточек этого номера. Откройте нужную карточку и повторите получение данных.')
    return matches[0] if matches else store.create({'number': number})


class _JobManager:
    """Small fixed pool with bounded queue and bounded completed-result history."""
    def __init__(self, *, runner=None, max_workers=2, max_queue=12,
                 max_completed=64, completed_ttl=3600):
        self.runner = runner or _run_sync
        self.max_workers = max(1, int(max_workers))
        self.max_queue = max(1, int(max_queue))
        self.max_completed = max(1, int(max_completed))
        self.completed_ttl = max(0, float(completed_ttl))
        self.condition = Condition()
        self.jobs = {}
        self.active_by_card = {}
        self.pending = deque()
        self.workers = []
        self.closed = False

    def _clean_locked(self):
        completed = sorted((row for row in self.jobs.values() if '_finished' in row),
                           key=lambda row: row['_finished'])
        expiry = monotonic() - self.completed_ttl
        excess = max(0, len(completed) - self.max_completed)
        for index, row in enumerate(completed):
            if index < excess or row['_finished'] < expiry:
                self.jobs.pop(row['id'], None)

    @staticmethod
    def _descriptor(row):
        return deepcopy({key: value for key, value in row.items() if not key.startswith('_')})

    def start(self, number, *, download_documents=True, tender_id=''):
        from modern.notice_number import normalize_notice
        number = normalize_notice(number)
        if type(download_documents) is not bool:
            raise ValueError('Параметр загрузки документов должен быть Да/Нет')
        if not isinstance(tender_id, str):
            raise ValueError('Неверный идентификатор карточки')
        with self.condition:
            if self.closed:
                raise RuntimeError('Получение данных остановлено')
            self._clean_locked()
            # This lock serializes only local bookkeeping/SQLite, never network.
            item = _ensure_card(number, tender_id)
            card_id = item['id']
            existing = self.active_by_card.get(card_id)
            if existing:
                descriptor = self._descriptor(self.jobs[existing])
            else:
                if len(self.pending) >= self.max_queue:
                    raise JobQueueFull(card_id)
                job_id = str(uuid4())
                stamp = _timestamp()
                row = {'id': job_id, 'number': number, 'tender_id': card_id,
                       'status': 'queued', 'stage': 'queued', 'progress': 0,
                       'message': 'Карточка сохранена. Ожидает получения данных ЕИС.',
                       'created_at': stamp, 'updated_at': stamp,
                       '_download_documents': download_documents}
                self.jobs[job_id] = row
                self.active_by_card[card_id] = job_id
                self.pending.append(job_id)
                while len(self.workers) < self.max_workers:
                    worker = Thread(target=self._worker, name='QX-EIS-' + str(len(self.workers) + 1), daemon=True)
                    self.workers.append(worker)
                    worker.start()
                descriptor = self._descriptor(row)
                self.condition.notify_all()
        return {'job': descriptor, 'tender': store.detail(card_id)}

    def get(self, job_id):
        with self.condition:
            self._clean_locked()
            row = self.jobs.get(job_id)
            if row is None:
                raise KeyError('Задача получения данных не найдена; обновите реестр закупок.')
            descriptor = self._descriptor(row)
        try:
            tender = store.detail(descriptor['tender_id'])
        except KeyError:
            tender = None  # A user may deliberately delete a card during a job.
        return {'job': descriptor, 'tender': tender}

    def active(self):
        with self.condition:
            self._clean_locked()
            return {'jobs': [self._descriptor(row) for row in self.jobs.values()
                             if row['status'] in ('queued', 'running')]}

    def _progress(self, job_id, stage, message, progress=None):
        with self.condition:
            row = self.jobs[job_id]
            row['stage'] = str(stage)[:80]
            row['message'] = str(message)[:500]
            if isinstance(progress, (int, float)) and not isinstance(progress, bool):
                row['progress'] = min(99, max(row['progress'], int(progress)))
            row['updated_at'] = _timestamp()

    def _worker(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.pending or self.closed)
                if self.closed and not self.pending:
                    return
                job_id = self.pending.popleft()
                row = self.jobs[job_id]
                row.update(status='running', stage='connecting', progress=1,
                           message='Карточка сохранена. Получаем сведения ЕИС.', updated_at=_timestamp())
                number, card_id = row['number'], row['tender_id']
                download_documents = row['_download_documents']
            try:
                result = self.runner(number, download_documents=download_documents,
                                     tender_id=card_id,
                                     progress=lambda stage, message, progress=None, _job_id=job_id: self._progress(_job_id, stage, message, progress))
                with self.condition:
                    row.update(status='partial' if result.get('partial') else 'succeeded',
                               stage='complete', progress=100, result=result,
                               message=str(result.get('message') or 'Получение данных завершено.')[:1000])
            except Exception as error:
                # Never expose exception text: it may contain credentials, URLs or paths.
                with self.condition:
                    row.update(status='failed', stage='failed', error_type=type(error).__name__,
                               message='Не удалось завершить получение данных. Карточка сохранена; заполните её вручную или повторите запрос.')
                    if isinstance(error, (ImportError, ModuleNotFoundError)):
                        row['message'] = 'Не установлен компонент получения данных. Карточка сохранена. Закройте QX и запустите ЗАПУСТИТЬ_QX.cmd: загрузчик проверит и восстановит библиотеки.'
            finally:
                with self.condition:
                    row['updated_at'] = _timestamp()
                    row['_finished'] = monotonic()
                    if self.active_by_card.get(card_id) == job_id:
                        self.active_by_card.pop(card_id, None)
                    self._clean_locked()
                    self.condition.notify_all()

    def close(self):
        """Test/service shutdown: queued work drains, workers stay daemon threads."""
        with self.condition:
            self.closed = True
            self.condition.notify_all()


_MANAGER = _JobManager()


def start_job(number, *, download_documents=True, tender_id=''):
    return _MANAGER.start(number, download_documents=download_documents, tender_id=tender_id)


def get_job(job_id):
    return _MANAGER.get(job_id)


def active_jobs():
    return _MANAGER.active()
