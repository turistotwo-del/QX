"""One purchase-number action: verified facts, idempotent card, public attachments."""
from __future__ import annotations

from contextlib import contextmanager
from threading import Lock

from modern import tender_store as store
from modern.eis_public import fetch_notice_metadata, official_search_url, validate_notice
from modern.eis_metadata import fetch_notice_html_metadata
from modern.eis_discovery import discover_and_import

_locks_guard = Lock()
_locks = {}
FACT_FIELDS = ('title', 'customer', 'nmck', 'law', 'application_due_on', 'application_due_time',
               'auction_on', 'auction_time', 'results_on', 'results_time', 'supply_address',
               'payment_terms', 'warranty')


@contextmanager
def _notice_lock(number):
    with _locks_guard:
        entry = _locks.setdefault(number, [Lock(), 0])
        entry[1] += 1
    try:
        with entry[0]:
            yield
    finally:
        with _locks_guard:
            entry[1] -= 1
            if not entry[1]:
                del _locks[number]


def _merge_empty_fields(tender_id, notice, source_url):
    """Read + conditional fill in one SQLite transaction, preserving manual edits."""
    if not notice or not notice.get('verified'):
        return [], []
    candidates = {key:notice[key] for key in FACT_FIELDS if notice.get(key) not in ('', None)}
    validated = store._validate(candidates)
    applied, conflicts = [], []
    with store.transaction() as conn:
        current = conn.execute('SELECT * FROM tenders WHERE id=?', (tender_id,)).fetchone()
        if current is None:
            raise KeyError('Закупка не найдена')
        for field, value in validated.items():
            previous = current[field]
            if field.endswith('_time'):
                day_field = field[:-5] + '_on'
                if current[day_field] and current[day_field] != validated.get(day_field):
                    conflicts.append({'field':field, 'current':previous, 'received':value,
                                      'reason':'В карточке сохранена другая дата события'})
                    continue
            if previous in ('', None) or (field == 'nmck' and previous == 0):
                conn.execute(f'UPDATE tenders SET {field}=?, updated_at=? WHERE id=?',
                             (value, store.now(), tender_id))
                applied.append(field)
            elif str(previous) != str(value):
                conflicts.append({'field':field, 'current':previous, 'received':value})
        if applied:
            conn.execute('INSERT INTO tender_events(tender_id,label,created_at) VALUES(?,?,?)',
                         (tender_id, 'ЕИС: заполнены пустые поля ' + ', '.join(applied) +
                          '; источник: ' + source_url[:500], store.now()))
    return applied, conflicts


def sync_notice(number: str, *, download_documents=True, tender_id='', opener=None) -> dict:
    """Network I/O belongs in a worker thread. No contract status or price guesses.

    The HTML fallback and downloads are independent of XML availability. A saved
    draft remains useful if EIS is offline; partial/failure outcomes stay explicit.
    """
    number = validate_notice(number)
    if type(download_documents) is not bool:
        raise ValueError('Параметр загрузки документов должен быть Да/Нет')
    with _notice_lock(number):
        if tender_id:
            item = store.get(tender_id)
            if not item:
                raise KeyError('Закупка не найдена')
            if item.get('number') != number:
                raise ValueError('Номер не совпадает с выбранной карточкой закупки')
        else:
            matches = [item for item in store.listing() if item.get('number') == number]
            if len(matches) > 1:
                raise ValueError('Есть несколько карточек этого номера. Откройте нужную карточку и повторите получение данных.')
            item = matches[0] if matches else store.create({'number':number})
            tender_id = item['id']
        metadata = fetch_notice_metadata(number, opener=opener)
        if not metadata.get('available') or not (metadata.get('notice') or {}).get('fields_fetched'):
            metadata = fetch_notice_html_metadata(number, opener=opener)
        notice = metadata.get('notice') or {}
        if notice and notice.get('number') != number:
            raise ValueError('Получены данные другого извещения')
        fields_applied, conflicts = _merge_empty_fields(tender_id, notice, metadata.get('source_url') or '')
        document_result = None
        if download_documents:
            document_result = discover_and_import(tender_id, opener=opener)
        metadata_available = bool(metadata.get('available') and notice.get('verified') and notice.get('fields_fetched'))
        docs_complete = bool(document_result and document_result.get('found') and document_result.get('complete') and
                             not document_result.get('failed_count') and not document_result.get('ignored'))
        partial = not metadata_available or bool(download_documents and not docs_complete)
        messages = [metadata.get('message') or 'Поля ЕИС не получены.']
        if fields_applied:
            messages.append('Заполнено пустых полей: ' + str(len(fields_applied)) + '.')
        if conflicts:
            messages.append('Существующие значения сохранены; отличий от ЕИС: ' + str(len(conflicts)) + '.')
        if document_result:
            messages.append('Новых документов: ' + str(len(document_result.get('imported') or [])) +
                            '; уже были: ' + str(len(document_result.get('duplicates') or [])) +
                            '; ошибок: ' + str(document_result.get('failed_count') or 0) + '.')
            if not document_result.get('found'):
                messages.append('Открытые ссылки на документы не найдены. Это не означает, что у закупки нет документов.')
            if document_result.get('limit_reached'):
                messages.append('Достигнут лимит поиска или загрузки; полный комплект не подтверждён.')
            if document_result.get('ignored'):
                messages.append('Пропущено неподдерживаемых или нечитаемых файлов: ' + str(len(document_result['ignored'])) + '.')
            messages.append('Поиск охватывает открытые ссылки на проверенных страницах; полный комплект ЕИС не гарантируется.')
        return {'tender':store.detail(tender_id), 'notice':notice or None,
                'metadata_available':metadata_available, 'source_url':metadata.get('source_url'),
                'search_url':official_search_url(number), 'fields_applied':fields_applied,
                'conflicts':conflicts, 'documents_result':document_result,
                'missing_fields':[key for key in FACT_FIELDS if not notice.get(key)],
                'metadata_error_type':metadata.get('error_type'), 'metadata_errors':metadata.get('errors', []),
                'partial':partial, 'message':' '.join(messages)}
